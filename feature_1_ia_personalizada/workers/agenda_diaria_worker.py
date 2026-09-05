"""
feature_1_ia_personalizada/workers/agenda_diaria_worker.py
===========================================================
Envia, toda manhã, a agenda do dia para cada advogado.

Uma task por escritório (`enviar_agenda_diaria`) e um disparador
(`disparar_agendas_diarias`) que o beat aciona e que enfileira uma task por
escritório ativo. Assim um escritório com carteira grande não segura os demais,
e uma falha isolada não derruba a rodada inteira.

Idempotência: a trava do notificador é por advogado **e dia**, então um
reprocessamento (retry do Celery, beat disparado duas vezes) não gera mensagem
duplicada.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import redis.asyncio as redis_async
import structlog
from celery import shared_task
from sqlalchemy import select

from shared.config.settings import settings
from shared.database.connection import create_worker_session_factory
from shared.models.escritorio import Escritorio
from shared.models.usuario import Usuario

logger = structlog.get_logger(__name__)


@shared_task(bind=True, name="workers.relacionamento.disparar_agendas_diarias")
def disparar_agendas_diarias(self: Any) -> dict[str, Any]:
    """Enfileira uma task de agenda para cada escritório ativo."""
    import asyncio

    async def _listar() -> list[int]:
        factory, engine = create_worker_session_factory()
        try:
            async with factory() as db:
                linhas = await db.execute(select(Escritorio.id).where(Escritorio.ativo.is_(True)))
                return [linha[0] for linha in linhas.all()]
        finally:
            await engine.dispose()

    escritorios = asyncio.run(_listar())
    for escritorio_id in escritorios:
        enviar_agenda_diaria.delay(escritorio_id)

    logger.info("agenda_diaria.disparada", escritorios=len(escritorios))
    return {"escritorios": len(escritorios)}


@shared_task(bind=True, name="workers.relacionamento.enviar_agenda_diaria", max_retries=1)
def enviar_agenda_diaria(self: Any, escritorio_id: int) -> dict[str, Any]:
    """Monta e envia a agenda do dia para os advogados de um escritório."""
    import asyncio

    from feature_1_ia_personalizada.services.relacionamento.agenda_diaria import (
        montar_agenda_do_escritorio,
        montar_mensagem,
    )
    from feature_1_ia_personalizada.services.relacionamento.notificador import (
        chave_agenda_diaria,
        notificar_advogado,
    )

    log = logger.bind(escritorio_id=escritorio_id)

    async def _run() -> dict[str, Any]:
        factory, engine = create_worker_session_factory()
        redis_client = redis_async.from_url(settings.REDIS_URL, decode_responses=True)
        enviadas = 0
        try:
            async with factory() as db:
                escritorio = (
                    (await db.execute(select(Escritorio).where(Escritorio.id == escritorio_id)))
                    .scalars()
                    .first()
                )
                if escritorio is None:
                    return {"enviadas": 0, "motivo": "escritorio_inexistente"}

                tz = escritorio.timezone or "America/Sao_Paulo"
                try:
                    hoje = datetime.now(ZoneInfo(tz)).date()
                except Exception:
                    hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date()

                agendas = await montar_agenda_do_escritorio(
                    db, escritorio_id, hoje=hoje, timezone_escritorio=tz
                )
                if not agendas:
                    return {"enviadas": 0, "motivo": "nada_para_hoje"}

                advogados = {
                    u.id: u
                    for u in (
                        await db.execute(select(Usuario).where(Usuario.id.in_(list(agendas))))
                    )
                    .scalars()
                    .all()
                }

                # Nomes dos clientes citados, em uma query só.
                from shared.models.cliente import Cliente

                ids_clientes = {
                    cid
                    for item in agendas.values()
                    for cid in (
                        [p.cliente_id for p in item.prazos]
                        + [r.cliente_id for r in item.reunioes]
                        + [c.id for c in item.clientes_em_risco]
                    )
                }
                nomes = dict(
                    (
                        await db.execute(
                            select(Cliente.id, Cliente.nome).where(
                                Cliente.id.in_(ids_clientes or {0})
                            )
                        )
                    ).all()
                )

                for advogado_id, item in agendas.items():
                    advogado = advogados.get(advogado_id)
                    if advogado is None:
                        continue
                    texto = montar_mensagem(advogado.nome, item, hoje, nomes)
                    if await notificar_advogado(
                        advogado,
                        escritorio.webhook_whatsapp_instance,
                        texto,
                        redis=redis_client,
                        chave_trava=chave_agenda_diaria(advogado_id, hoje.isoformat()),
                        janela_segundos=20 * 3600,  # cobre o dia sem vazar para o seguinte
                    ):
                        enviadas += 1

            return {"enviadas": enviadas, "advogados": len(agendas)}
        finally:
            await redis_client.aclose()
            await engine.dispose()

    try:
        resultado = asyncio.run(_run())
    except Exception as exc:
        log.error("agenda_diaria.falhou", erro=str(exc))
        raise

    log.info("agenda_diaria.concluida", **resultado)
    return resultado
