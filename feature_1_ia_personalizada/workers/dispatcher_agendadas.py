"""
feature_1_ia_personalizada/workers/dispatcher_agendadas.py
============================================================
Worker Celery Beat que processa mensagens WhatsApp agendadas.

Roda a cada 5 minutos via beat_schedule e envia todas as linhas
da tabela mensagens_agendadas onde:
  - status = 'pendente'
  - enviar_em <= agora

Garante idempotência usando SELECT ... FOR UPDATE SKIP LOCKED,
então múltiplos workers podem rodar sem double-send.

Política de retentativas:
  - Máximo de 3 tentativas por mensagem
  - Após a 3ª falha, status → 'falha' (sem novos reenvios)
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import structlog
from celery import shared_task
from sqlalchemy import select, update

from feature_1_ia_personalizada.services.messaging.evolution_client import EvolutionClient
from feature_1_ia_personalizada.services.messaging.whatsapp import SQLWhatsAppRepository
from feature_1_ia_personalizada.workers.celery_app import DLQTask
from shared.config.settings import settings
from shared.database.connection import async_session_factory
from shared.models.mensagem_agendada import MensagemAgendada

logger = structlog.get_logger(__name__)

MAX_TENTATIVAS = 3
LOTE_MAXIMO = 50  # linhas por execução do beat para evitar tasks longas


@shared_task(
    name="feature_1_ia_personalizada.workers.dispatcher_agendadas.despachar_mensagens_agendadas",
    base=DLQTask,
    max_retries=0,  # a task em si não reintenta — cada mensagem tem sua própria contagem
    queue="notificacoes",
)
def despachar_mensagens_agendadas() -> dict:
    """
    Busca e envia até LOTE_MAXIMO mensagens pendentes cujo enviar_em já passou.
    """
    enviadas, falhas = asyncio.run(_processar_lote())
    logger.info(
        "dispatcher_agendadas.concluido",
        enviadas=enviadas,
        falhas=falhas,
    )
    return {"enviadas": enviadas, "falhas": falhas}


async def _processar_lote() -> tuple[int, int]:
    agora = datetime.now(tz=UTC)
    enviadas = 0
    falhas = 0

    async with async_session_factory() as session:
        # SELECT ... FOR UPDATE SKIP LOCKED — garante que workers paralelos
        # não peguem a mesma linha
        stmt = (
            select(MensagemAgendada)
            .where(
                MensagemAgendada.status == "pendente",
                MensagemAgendada.enviar_em <= agora,
            )
            .order_by(MensagemAgendada.enviar_em)
            .limit(LOTE_MAXIMO)
            .with_for_update(skip_locked=True)
        )
        result = await session.execute(stmt)
        mensagens = result.scalars().all()

    if not mensagens:
        return 0, 0

    # Obtém instância do WhatsApp e envia cada mensagem fora da transação principal
    # (cada envio tem seu próprio try/except para não abortar o lote inteiro)
    repo = SQLWhatsAppRepository()
    assert settings.EVOLUTION_API_URL and settings.EVOLUTION_API_KEY
    evolution = EvolutionClient(settings.EVOLUTION_API_URL, settings.EVOLUTION_API_KEY)

    try:
        for msg in mensagens:
            try:
                instancia = await repo.obter_instancia_por_escritorio(msg.escritorio_id)
                numero = await repo.obter_numero_cliente(msg.cliente_id)
                await evolution.enviar_texto(instancia, numero, msg.texto)

                async with async_session_factory() as session:
                    await session.execute(
                        update(MensagemAgendada)
                        .where(MensagemAgendada.id == msg.id)
                        .values(
                            status="enviada",
                            enviada_em=datetime.now(tz=UTC),
                            tentativas=msg.tentativas + 1,
                        )
                    )
                    await session.commit()

                logger.info(
                    "dispatcher_agendadas.enviada",
                    mensagem_id=msg.id,
                    cliente_id=msg.cliente_id,
                    motivo=msg.motivo,
                )
                enviadas += 1

            except Exception as exc:
                novas_tentativas = msg.tentativas + 1
                novo_status = "falha" if novas_tentativas >= MAX_TENTATIVAS else "pendente"

                async with async_session_factory() as session:
                    await session.execute(
                        update(MensagemAgendada)
                        .where(MensagemAgendada.id == msg.id)
                        .values(
                            tentativas=novas_tentativas,
                            status=novo_status,
                        )
                    )
                    await session.commit()

                logger.warning(
                    "dispatcher_agendadas.falha_envio",
                    mensagem_id=msg.id,
                    cliente_id=msg.cliente_id,
                    tentativas=novas_tentativas,
                    status=novo_status,
                    erro=str(exc),
                )
                if novo_status == "falha":
                    falhas += 1
    finally:
        await evolution.close()

    return enviadas, falhas
