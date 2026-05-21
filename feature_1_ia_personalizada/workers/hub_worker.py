"""
feature_1_ia_personalizada/workers/hub_worker.py
=================================================
Task Celery para análise de petição via Claude Opus (modo assíncrono).

Fluxo:
  1. Rota POST /hub/analisar-peticao extrai o texto do PDF de forma síncrona
     (validação rápida) e despacha esta task retornando 202 + job_id.
  2. Esta task executa a chamada Claude (15–60 s) fora do ciclo HTTP.
  3. Resultado e status são gravados em Redis na chave hub:job:{job_id} (TTL 1 h).
  4. Frontend faz polling em GET /hub/jobs/{job_id} até status != "processando".
"""

from __future__ import annotations

import asyncio
import dataclasses
import json

import redis
import structlog

from feature_1_ia_personalizada.services.ai.escalation_client import (
    EscalacaoClient,
    TipoAnalise,
)
from shared.config.settings import settings
from shared.database.session import get_session_factory
from shared.models.sessao_advogado import SessaoAdvogado

from .celery_app import DLQTask, celery_app

logger = structlog.get_logger(__name__)

_JOB_TTL = 3600  # 1 hora


def _redis() -> redis.Redis:
    return redis.from_url(settings.REDIS_URL, decode_responses=True)


def _set_job(r: redis.Redis, job_id: str, payload: dict) -> None:
    r.setex(f"hub:job:{job_id}", _JOB_TTL, json.dumps(payload))


@celery_app.task(
    name="feature_1_ia_personalizada.workers.hub_worker.hub_analisar_peticao_task",
    base=DLQTask,
    max_retries=1,
    queue="ia",
)
def hub_analisar_peticao_task(
    job_id: str,
    conteudo_texto: str,
    texto_truncado: bool,
    percentual_analisado: float,
    filename: str,
    escritorio_id: int,
    advogado_id: int,
) -> None:
    log = logger.bind(job_id=job_id, escritorio_id=escritorio_id, advogado_id=advogado_id)
    log.info("hub_worker.analisar_peticao.iniciando")
    r = _redis()

    async def _run():
        client = EscalacaoClient()
        analise = await client.analisar_peca(
            conteudo_peca=conteudo_texto,
            tipo_analise=TipoAnalise.ANALISE_COMPLETA,
            contexto_processo="Análise solicitada via API REST.",
        )

        # Salvar sessão no DB
        factory = get_session_factory()
        async with factory() as db:
            sessao = SessaoAdvogado(
                escritorio_id=escritorio_id,
                usuario_id=advogado_id,
                mensagem_advogado=f"[PDF] {filename}",
                resposta_hub=str(dataclasses.asdict(analise)),
                intencao="analise_peticao",
                modelo_ia="claude_opus",
                tokens_input=analise.tokens_input,
                tokens_output=analise.tokens_output,
                custo_estimado=analise.custo_estimado,
                metadata_json={
                    "filename": filename,
                    "texto_truncado": texto_truncado,
                    "job_id": job_id,
                },
            )
            db.add(sessao)
            await db.commit()

        return analise

    try:
        analise = asyncio.run(_run())
        d = dataclasses.asdict(analise)
        d["custo_estimado"] = str(d["custo_estimado"])  # Decimal → str
        resultado = {**d, "texto_truncado": texto_truncado, "percentual_analisado": percentual_analisado}
        _set_job(r, job_id, {"status": "concluido", "resultado": resultado, "erro": None})
        log.info("hub_worker.analisar_peticao.concluido")
    except Exception as exc:
        log.error("hub_worker.analisar_peticao.falhou", erro=str(exc))
        _set_job(r, job_id, {"status": "erro", "resultado": None, "erro": str(exc)})
        raise
