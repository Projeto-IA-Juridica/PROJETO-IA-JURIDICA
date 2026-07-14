"""
Worker da conversa da Clara: o fio que liga tudo em runtime.

responder_conversa (task) → ConversaClara.processar → se quente, handoff.

Roda na fila do Celery existente. Usa a factory de sessão de worker (NullPool)
como todos os workers do projeto, pelo mesmo motivo de event loop.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import structlog
from celery import shared_task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from feature_vendas import config as vconfig
from feature_vendas.models.alvo_vendas import AlvoVendas
from feature_vendas.services.conversa_clara import ConversaClara
from feature_vendas.services.handoff import HandoffService, Socio, escolher_socio, montar_briefing
from feature_vendas.services.humanizacao.evolution_humano import EvolutionHumano
from feature_vendas.services.lead_scoring import Qualificacao
from shared.config.settings import settings

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def _sessao() -> AsyncGenerator[AsyncSession, None]:
    from shared.database.connection import worker_session_factory

    async with worker_session_factory() as s:
        yield s


def _redis():  # noqa: ANN202
    import redis.asyncio as aioredis

    return aioredis.from_url(settings.REDIS_URL, decode_responses=True)


def _evolution() -> EvolutionHumano:
    assert settings.EVOLUTION_API_URL and vconfig.VENDAS_EVOLUTION_API_KEY
    return EvolutionHumano(settings.EVOLUTION_API_URL, vconfig.VENDAS_EVOLUTION_API_KEY)


def _socios() -> list[Socio]:
    """Sócios que recebem handoff. Lê de env VENDAS_SOCIOS='Gabriel:5599...:1,Sócia:5599...:2'."""
    import os

    raw = os.getenv("VENDAS_SOCIOS", "")
    socios: list[Socio] = []
    for item in raw.split(","):
        partes = item.split(":")
        if len(partes) == 3 and partes[1].strip():
            socios.append(Socio(partes[0].strip(), partes[1].strip(), int(partes[2])))
    return socios


async def _processar(alvo_id: int, numero: str, texto: str, message_id: str | None) -> None:
    from feature_1_ia_personalizada.services.ai.claude_client import ClaudeClient
    from feature_1_ia_personalizada.services.ai.memory import ConversationMemory

    redis = _redis()
    evo = _evolution()
    conversa = ConversaClara(
        redis=redis,
        claude=ClaudeClient(settings.ANTHROPIC_API_KEY),
        memory=ConversationMemory(redis),
        evolution=evo,
        instancia=vconfig.instancia_disparo(),
        tenant_id=vconfig.tenant_id(),
    )

    resultado = await conversa.processar(
        lead_ref=alvo_id, numero=numero, texto=texto, message_id=message_id
    )
    if resultado is None:
        return  # outra invocação da rajada assumiu

    if not resultado["quente"]:
        return

    # Handoff: marca o alvo e notifica um sócio.
    async with _sessao() as db:
        alvo = (
            await db.execute(select(AlvoVendas).where(AlvoVendas.id == alvo_id))
        ).scalar_one_or_none()
        if alvo is None or alvo.status == "quente":
            return  # já promovido (idempotência do handoff)

        socios = _socios()
        if not socios:
            logger.warning("handoff_sem_socios_configurados", alvo_id=alvo_id)
            alvo.status = "quente"
            await db.commit()
            return

        # Round-robin persistido em Redis (contador global de vendas).
        rr = int(await redis.incr("vendas:handoff:rr")) - 1
        socio = escolher_socio(socios, alvo.origem, rr)

        q = resultado["qualificacao"]
        briefing = montar_briefing(
            nome_escritorio=alvo.nome_escritorio,
            nome_contato=alvo.nome_contato,
            cidade=alvo.cidade,
            gatilho=resultado["gatilho"],
            qualificacao=Qualificacao(q["num_advogados"], q["area"], q["quem_responde"]),
            trilhas_testadas=[],
        )
        await HandoffService(evo, vconfig.instancia_disparo()).notificar_socio(socio, briefing)

        alvo.status = "quente"
        alvo.respondeu_em = alvo.respondeu_em or datetime.now(UTC)
        alvo.metadados = {
            **(alvo.metadados or {}),
            "gatilho_handoff": resultado["gatilho"],
            "socio_responsavel": socio.nome,
        }
        await db.commit()
        logger.info("handoff_concluido", alvo_id=alvo_id, socio=socio.nome)


@shared_task(name="vendas.responder_conversa")
def responder_conversa(
    alvo_id: int, numero: str, texto: str, message_id: str | None = None
) -> None:
    asyncio.run(_processar(alvo_id, numero, texto, message_id))
