"""
feature_1_ia_personalizada/workers/crm_worker.py
==================================================
Tasks Celery para análise CRM:

- crm_analisar_cliente   → analisa um cliente (fila "ia")
- crm_analisar_escritorio → dispara análise de todos os clientes ativos (fila "ia")

Debounce via Redis key `crm_debounce:{cliente_id}` TTL 1h —
não re-dispara se já foi disparado na última hora.
"""

from __future__ import annotations

import asyncio
from typing import Any

import redis
import structlog
from celery import chord
from sqlalchemy import select

from feature_1_ia_personalizada.services.ai.claude_client import ClaudeClient
from feature_1_ia_personalizada.services.crm.analyzer import CRMAnalyzer
from shared.config.settings import settings
from shared.database.connection import create_worker_session_factory
from shared.models.cliente import Cliente

from .celery_app import DLQTask, celery_app

logger = structlog.get_logger(__name__)

_DEBOUNCE_TTL_SEGUNDOS = 10  # 10 segundos (reduzido para testes/MVP)
_MAX_SIMULTANEAS = 10  # máx análises paralelas por escritório (chord)


def _redis_client() -> redis.Redis:
    return redis.from_url(settings.REDIS_URL, decode_responses=True)  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# Task 1 — análise de um único cliente
# ---------------------------------------------------------------------------


@celery_app.task(
    name="feature_1_ia_personalizada.workers.crm_worker.crm_analisar_cliente",
    base=DLQTask,
    max_retries=2,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    queue="ia",
)
def crm_analisar_cliente(cliente_id: int, escritorio_id: int) -> dict[str, Any]:
    log = logger.bind(cliente_id=cliente_id, escritorio_id=escritorio_id)
    log.info("crm_worker.analisar_cliente.iniciando")

    async def _run() -> dict[str, Any]:
        # Factory/engine dedicados a este asyncio.run() — get_session_factory()
        # reaproveitaria conexões pooled de um event loop diferente a cada task
        # e trava silenciosamente em vez de lançar exceção (create_worker_session_factory).
        factory, db_engine = create_worker_session_factory()
        try:
            async with factory() as db:
                claude = ClaudeClient(api_key=settings.ANTHROPIC_API_KEY)
                analyzer = CRMAnalyzer(claude_client=claude, db=db)
                result = await analyzer.analisar_cliente(cliente_id, escritorio_id)

                # Classificar não bastava: até aqui o nível de risco ficava só
                # no banco esperando alguém abrir o painel. Um cliente prestes a
                # sair vira aviso no WhatsApp do advogado responsável.
                # Não alerta em cache_hit — a classificação não mudou.
                alertado = False
                if not result.cache_hit:
                    import redis.asyncio as redis_async

                    from feature_1_ia_personalizada.services.relacionamento.alerta_risco import (
                        alertar_se_em_risco,
                    )

                    redis_client = redis_async.from_url(settings.REDIS_URL, decode_responses=True)
                    try:
                        alertado = await alertar_se_em_risco(
                            db,
                            cliente_id,
                            escritorio_id,
                            result.nivel,
                            result.score,
                            redis=redis_client,
                        )
                    finally:
                        await redis_client.aclose()

                return {
                    "cliente_id": cliente_id,
                    "nivel": result.nivel,
                    "score": result.score,
                    "cache_hit": result.cache_hit,
                    "alerta_enviado": alertado,
                    "tokens_input": result.tokens_input,
                    "tokens_output": result.tokens_output,
                }
        finally:
            await db_engine.dispose()

    try:
        resultado = asyncio.run(_run())
    except Exception as exc:
        # Graceful degradation: log e re-raise para o retry/DLQ
        log.error("crm_worker.analisar_cliente.falhou", erro=str(exc))
        raise

    # Emite contador por nível — permite ver distribuição de risco da carteira no Prometheus
    try:
        from feature_1_ia_personalizada.api.routes.metrics import clientes_crm_analisados_total

        clientes_crm_analisados_total.labels(
            escritorio_id=str(escritorio_id),
            nivel=resultado.get("nivel", "desconhecido"),
        ).inc()
    except Exception:
        pass  # métricas nunca bloqueiam a task

    return resultado


# ---------------------------------------------------------------------------
# Task 2 — análise de todos os clientes ativos de um escritório
# ---------------------------------------------------------------------------


@celery_app.task(
    name="feature_1_ia_personalizada.workers.crm_worker.crm_analisar_escritorio",
    base=DLQTask,
    max_retries=1,
    queue="ia",
)
def crm_analisar_escritorio(escritorio_id: int) -> dict[str, Any]:
    log = logger.bind(escritorio_id=escritorio_id)
    log.info("crm_worker.analisar_escritorio.iniciando")

    async def _buscar_clientes() -> list[int]:
        factory, db_engine = create_worker_session_factory()
        try:
            async with factory() as db:
                stmt = select(Cliente.id).where(
                    Cliente.escritorio_id == escritorio_id,
                    Cliente.ativo.is_(True),
                )
                rows = (await db.execute(stmt)).all()
                return [r.id for r in rows]
        finally:
            await db_engine.dispose()

    cliente_ids = asyncio.run(_buscar_clientes())
    total = len(cliente_ids)
    log.info("crm_worker.analisar_escritorio.clientes_encontrados", total=total)

    if not cliente_ids:
        return {"total_clientes": 0, "job_ids": []}

    # Enfileira em lotes de _MAX_SIMULTANEAS usando chord para controlar paralelismo
    job_ids: list[str] = []
    for i in range(0, total, _MAX_SIMULTANEAS):
        lote = cliente_ids[i : i + _MAX_SIMULTANEAS]
        tasks = [
            crm_analisar_cliente.signature(
                args=(cid, escritorio_id),
                queue="ia",
                immutable=True,
            )
            for cid in lote
        ]
        resultado = chord(tasks)(celery_app.signature("celery.chord_unlock", queue="ia"))
        job_ids.append(str(resultado.id) if resultado else f"lote_{i}")

    return {"total_clientes": total, "job_ids": job_ids}


# ---------------------------------------------------------------------------
# Função utilitária — debounce para trigger do webhook
# ---------------------------------------------------------------------------


def disparar_analise_com_debounce(cliente_id: int, escritorio_id: int) -> bool:
    """
    Dispara crm_analisar_cliente apenas se não houver análise recente.
    Usa Redis key `crm_debounce:{cliente_id}` com TTL de 1 hora.

    Returns:
        True se disparou, False se estava no debounce.
    """
    r = _redis_client()
    chave = f"crm_debounce_v2:{cliente_id}"

    # SET NX — só seta se a chave não existir (atômico)
    setado = r.set(chave, "1", ex=_DEBOUNCE_TTL_SEGUNDOS, nx=True)
    if not setado:
        logger.debug("crm_worker.debounce.skip", cliente_id=cliente_id)
        return False

    crm_analisar_cliente.delay(cliente_id, escritorio_id)
    logger.info("crm_worker.debounce.disparado", cliente_id=cliente_id)
    return True
