"""
Workers Celery do Agendamento Inteligente (Fase 4).

| Task                              | Trigger                       | O que faz                                                 |
|-----------------------------------|-------------------------------|-----------------------------------------------------------|
| processar_resposta_advogado_wpp   | Webhook incoming (advogado)   | Confirma/recusa via WhatsApp com lock Redis               |
| expirar_propostas                 | Cron a cada hora              | aguardando_cliente com expira_em vencido → expirado       |
| enviar_lembretes                  | Cron diário às 8h             | Lembrete 24h antes — cliente E advogado                   |
| enviar_confirmacao_pre_reuniao    | Cron a cada hora              | Confirmação 3h antes ao cliente (flag de idempotência)    |
| verificar_conflitos_prazos        | Hook pós-andamento + cron 7h30| Reuniões confirmadas vs. novos prazos → alerta o advogado |

Todas as tasks rodam na fila `ia` (mesma infraestrutura Celery existente).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import structlog
from celery import shared_task
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from feature_1_ia_personalizada.workers.celery_app import DLQTask
from shared.config.settings import settings
from shared.models.agendamento import Agendamento
from shared.models.escritorio import Escritorio

logger = structlog.get_logger(__name__)

_LEMBRETE_DEDUP_TTL_S = 2 * 24 * 60 * 60  # 2 dias
_CONFLITO_DEDUP_TTL_S = 7 * 24 * 60 * 60  # 7 dias


def _criar_evolution() -> Any:
    from feature_1_ia_personalizada.services.messaging.evolution_client import EvolutionClient

    assert settings.EVOLUTION_API_URL and settings.EVOLUTION_API_KEY
    return EvolutionClient(settings.EVOLUTION_API_URL, settings.EVOLUTION_API_KEY)


def _criar_redis() -> Any:
    import redis.asyncio as aioredis

    return aioredis.from_url(settings.REDIS_URL, decode_responses=True)


@asynccontextmanager
async def _sessao_worker() -> AsyncGenerator[AsyncSession, None]:
    """
    Sessão async segura para Celery: asyncio.run() cria um event loop novo a
    cada task, e conexões asyncpg não podem cruzar loops. A factory global de
    worker usa NullPool — nenhuma conexão sobrevive entre usos, sem precisar
    de engine/dispose por task.
    """
    from shared.database.connection import worker_session_factory

    async with worker_session_factory() as session:
        yield session


# ---------------------------------------------------------------------------
# Resposta do advogado via WhatsApp (webhook → aqui)
# ---------------------------------------------------------------------------


@shared_task(
    bind=True,
    name="workers.agendamento.processar_resposta_advogado_wpp",
    base=DLQTask,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=3,
)
def processar_resposta_advogado_wpp(self: Any, escritorio_id: int, texto: str) -> dict[str, Any]:
    """Interpreta 1/sim/2/não (regex; Claude como fallback) e confirma/recusa."""

    async def _run() -> dict[str, Any]:
        from feature_1_ia_personalizada.services.agendamento.notifier import AgendamentoNotifier
        from feature_1_ia_personalizada.services.ai.claude_client import ClaudeClient

        evolution = _criar_evolution()
        redis_client = _criar_redis()
        claude = ClaudeClient(api_key=settings.ANTHROPIC_API_KEY)
        try:
            async with _sessao_worker() as session:
                notifier = AgendamentoNotifier(
                    session=session,
                    evolution=evolution,
                    redis=redis_client,
                    claude=claude,
                )
                return await notifier.processar_resposta_advogado(texto, escritorio_id)
        finally:
            await evolution.close()
            await redis_client.aclose()

    resultado = asyncio.run(_run())
    logger.info(
        "agendamento_resposta_advogado_processada",
        escritorio_id=escritorio_id,
        resultado=resultado.get("status"),
    )
    return resultado


# ---------------------------------------------------------------------------
# Mensagens pós-ação do Hub (confirmar / sugerir / cancelar)
# ---------------------------------------------------------------------------


@shared_task(
    bind=True,
    name="workers.agendamento.enviar_mensagens_pos_acao",
    base=DLQTask,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=3,
)
def enviar_mensagens_pos_acao(self: Any, agendamento_id: int, acao: str) -> dict[str, Any]:
    """
    Envia o WhatsApp correspondente a uma ação feita no Hub, fora do ciclo HTTP.

    acao:
      confirmado → confirmação ao cliente (flag whatsapp_confirmacao_cliente_enviado)
      proposta   → novas opções ao cliente (flag whatsapp_proposta_cliente_enviado)
      cancelado  → aviso de cancelamento (dedup via Redis — não há flag no modelo)
    """

    async def _run() -> str:
        from feature_1_ia_personalizada.services.agendamento.google_calendar import (
            remover_evento_agendamento,
            sincronizar_confirmacao,
        )
        from feature_1_ia_personalizada.services.agendamento.notifier import AgendamentoNotifier

        evolution = _criar_evolution()
        redis_client = _criar_redis()
        try:
            async with _sessao_worker() as session:
                ag = await session.get(Agendamento, agendamento_id)
                if ag is None:
                    return "nao_encontrado"

                notifier = AgendamentoNotifier(session=session, evolution=evolution)

                if acao == "confirmado":
                    if ag.status != "confirmado":
                        return f"status_divergente:{ag.status}"
                    enviado = await notifier.enviar_confirmacao_cliente(ag)
                    # Google Calendar: evento na agenda do escritório (best-effort)
                    await sincronizar_confirmacao(session, ag)
                    return "enviado" if enviado else "ja_enviado_ou_falha"

                if acao == "proposta":
                    if ag.status != "aguardando_cliente":
                        return f"status_divergente:{ag.status}"
                    # Remarcação: o evento antigo sai da agenda externa
                    await remover_evento_agendamento(session, ag)
                    enviado = await notifier.enviar_proposta_cliente(ag, reproposta=True)
                    return "enviado" if enviado else "ja_enviado_ou_falha"

                if acao == "cancelado":
                    if ag.status != "cancelado":
                        return f"status_divergente:{ag.status}"
                    await remover_evento_agendamento(session, ag)
                    dedup = f"agendamento_cancelamento_enviado:{ag.id}"
                    if not await redis_client.set(dedup, "1", ex=_LEMBRETE_DEDUP_TTL_S, nx=True):
                        return "ja_enviado"
                    enviado = await notifier.enviar_cancelamento(ag)
                    return "enviado" if enviado else "falha"

                return f"acao_desconhecida:{acao}"
        finally:
            await evolution.close()
            await redis_client.aclose()

    resultado = asyncio.run(_run())
    logger.info(
        "agendamento_pos_acao_processada",
        agendamento_id=agendamento_id,
        acao=acao,
        resultado=resultado,
    )
    return {"resultado": resultado}


# ---------------------------------------------------------------------------
# Expiração de propostas (48h sem resposta do cliente)
# ---------------------------------------------------------------------------


@shared_task(bind=True, name="workers.agendamento.expirar_propostas")
def expirar_propostas(self: Any) -> dict[str, Any]:
    """Marca como `expirado` propostas aguardando_cliente vencidas (índice expira_em)."""

    async def _run() -> list[tuple[int, int]]:
        async with _sessao_worker() as session:
            result = await session.execute(
                update(Agendamento)
                .where(
                    Agendamento.status == "aguardando_cliente",
                    Agendamento.expira_em.isnot(None),
                    Agendamento.expira_em < datetime.now(UTC),
                )
                .values(status="expirado")
                .returning(Agendamento.id, Agendamento.escritorio_id)
            )
            expirados = [(row[0], row[1]) for row in result.fetchall()]
            await session.commit()
            return expirados

    expirados = asyncio.run(_run())

    # Tempo real: avisa os escritórios afetados (cards/agenda atualizam na hora)
    if expirados:

        async def _publicar() -> None:
            from feature_1_ia_personalizada.services.agendamento.eventos import (
                publicar_evento_agendamento,
            )

            redis_client = _criar_redis()
            try:
                for eid in {e for _, e in expirados}:
                    await publicar_evento_agendamento(redis_client, eid)
            finally:
                await redis_client.aclose()

        asyncio.run(_publicar())

    try:
        from feature_1_ia_personalizada.api.routes.metrics import agendamentos_expirados_total

        for _, escritorio_id in expirados:
            agendamentos_expirados_total.labels(escritorio_id=str(escritorio_id)).inc()
    except Exception:
        pass

    if expirados:
        logger.info("agendamento_propostas_expiradas", total=len(expirados))
    return {"expirados": len(expirados)}


# ---------------------------------------------------------------------------
# Lembrete 24h antes (cliente + advogado)
# ---------------------------------------------------------------------------


@shared_task(bind=True, name="workers.agendamento.enviar_lembretes")
def enviar_lembretes(self: Any) -> dict[str, Any]:
    """Reuniões confirmadas com data local == amanhã (fuso do escritório)."""

    async def _run() -> int:
        from feature_1_ia_personalizada.services.agendamento.notifier import AgendamentoNotifier

        agora = datetime.now(UTC)
        evolution = _criar_evolution()
        redis_client = _criar_redis()
        enviados = 0
        try:
            async with _sessao_worker() as session:
                rows = (
                    (
                        await session.execute(
                            select(Agendamento).where(
                                Agendamento.status == "confirmado",
                                Agendamento.data_hora_inicio.isnot(None),
                                Agendamento.data_hora_inicio >= agora,
                                Agendamento.data_hora_inicio <= agora + timedelta(days=2),
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                notifier = AgendamentoNotifier(session=session, evolution=evolution)

                for ag in rows:
                    escritorio = await session.get(Escritorio, ag.escritorio_id)
                    if not escritorio:
                        continue
                    tz = ZoneInfo(escritorio.timezone or "America/Sao_Paulo")
                    hoje_local = agora.astimezone(tz).date()
                    inicio = ag.data_hora_inicio
                    assert inicio is not None  # filtrado na query
                    if inicio.astimezone(tz).date() != hoje_local + timedelta(days=1):
                        continue

                    # Dedup inclui a data: reunião remarcada (sugerir → reconfirmar)
                    # deve receber lembrete da NOVA data mesmo com TTL antigo vivo
                    dia_reuniao = inicio.astimezone(tz).date().isoformat()
                    dedup = f"agendamento_lembrete24:{ag.id}:{dia_reuniao}"
                    if not await redis_client.set(dedup, "1", ex=_LEMBRETE_DEDUP_TTL_S, nx=True):
                        continue

                    if await notifier.enviar_lembrete(ag):
                        enviados += 1
        finally:
            await evolution.close()
            await redis_client.aclose()
        return enviados

    enviados = asyncio.run(_run())
    logger.info("agendamento_lembretes_enviados", total=enviados)
    return {"enviados": enviados}


# ---------------------------------------------------------------------------
# Confirmação 3h antes (cliente) — reduz no-show
# ---------------------------------------------------------------------------


@shared_task(bind=True, name="workers.agendamento.enviar_confirmacao_pre_reuniao")
def enviar_confirmacao_pre_reuniao(self: Any) -> dict[str, Any]:
    """
    Janela [now+3h, now+4h): envia UMA única mensagem por reunião — a flag
    whatsapp_confirmacao_pre_reuniao_enviado impede reenvio nas execuções
    horárias seguintes.
    """

    async def _run() -> int:
        from feature_1_ia_personalizada.services.agendamento.notifier import AgendamentoNotifier

        agora = datetime.now(UTC)
        evolution = _criar_evolution()
        enviados = 0
        try:
            async with _sessao_worker() as session:
                rows = (
                    (
                        await session.execute(
                            select(Agendamento).where(
                                Agendamento.status == "confirmado",
                                Agendamento.whatsapp_confirmacao_pre_reuniao_enviado.is_(False),
                                Agendamento.data_hora_inicio.isnot(None),
                                Agendamento.data_hora_inicio >= agora + timedelta(hours=3),
                                Agendamento.data_hora_inicio < agora + timedelta(hours=4),
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                notifier = AgendamentoNotifier(session=session, evolution=evolution)
                for ag in rows:
                    if await notifier.enviar_confirmacao_pre_reuniao(ag):
                        enviados += 1
        finally:
            await evolution.close()
        return enviados

    enviados = asyncio.run(_run())
    logger.info("agendamento_pre_reuniao_enviadas", total=enviados)
    return {"enviados": enviados}


# ---------------------------------------------------------------------------
# Conflitos com prazos processuais (hook pós-andamento + varredura diária)
# ---------------------------------------------------------------------------


@shared_task(bind=True, name="workers.agendamento.verificar_conflitos_prazos")
def verificar_conflitos_prazos(self: Any, processo_id: int | None = None) -> dict[str, Any]:
    """
    Re-verifica reuniões confirmadas contra prazos detectados nos andamentos.
    Conflito NÃO cancela a reunião — apenas alerta o advogado (uma vez por
    par agendamento×prazo, dedup em Redis).
    """

    async def _run() -> int:
        from feature_1_ia_personalizada.services.agendamento.notifier import (
            normalizar_numero_whatsapp,
        )
        from feature_1_ia_personalizada.services.agendamento.prazos import (
            buscar_prazos_escritorio,
        )
        from shared.models.processo import Processo

        agora = datetime.now(UTC)
        evolution = _criar_evolution()
        redis_client = _criar_redis()
        alertas = 0
        try:
            async with _sessao_worker() as session:
                stmt = select(Agendamento).where(
                    Agendamento.status == "confirmado",
                    Agendamento.data_hora_inicio.isnot(None),
                    Agendamento.data_hora_inicio >= agora,
                )
                if processo_id is not None:
                    proc = await session.get(Processo, processo_id)
                    if proc is None:
                        return 0
                    stmt = stmt.where(Agendamento.cliente_id == proc.cliente_id)

                agendamentos = (await session.execute(stmt)).scalars().all()
                if not agendamentos:
                    return 0

                prazos_cache: dict[int, Any] = {}

                for ag in agendamentos:
                    escritorio = await session.get(Escritorio, ag.escritorio_id)
                    if not escritorio or not escritorio.telefone_advogado:
                        continue

                    if ag.cliente_id not in prazos_cache:
                        prazos_cache[ag.cliente_id] = await buscar_prazos_escritorio(
                            session, ag.escritorio_id, cliente_id=ag.cliente_id
                        )
                    prazos = prazos_cache[ag.cliente_id]
                    if not prazos:
                        continue

                    tz = ZoneInfo(escritorio.timezone or "America/Sao_Paulo")
                    inicio = ag.data_hora_inicio
                    assert inicio is not None  # filtrado na query
                    dia_reuniao = inicio.astimezone(tz).date()

                    for prazo in prazos:
                        if dia_reuniao not in (prazo.data, prazo.data - timedelta(days=1)):
                            continue
                        dedup = f"agendamento_conflito_alerta:{ag.id}:{prazo.data.isoformat()}"
                        if not await redis_client.set(
                            dedup, "1", ex=_CONFLITO_DEDUP_TTL_S, nx=True
                        ):
                            continue

                        data_str = inicio.astimezone(tz).strftime("%d/%m às %Hh")
                        try:
                            await evolution.enviar_texto(
                                escritorio.webhook_whatsapp_instance or "",
                                normalizar_numero_whatsapp(escritorio.telefone_advogado),
                                f"⚠️ *Conflito de agenda detectado*\n\n"
                                f"A reunião confirmada em {data_str} coincide com um "
                                f"prazo processual ({prazo.data.strftime('%d/%m')}"
                                f"{f' — proc. {prazo.numero_cnj}' if prazo.numero_cnj else ''}).\n\n"
                                "Se precisar, reagende pelo Hub.",
                            )
                            alertas += 1
                            try:
                                from feature_1_ia_personalizada.api.routes.metrics import (
                                    agendamentos_conflito_prazo_total,
                                )

                                agendamentos_conflito_prazo_total.labels(
                                    escritorio_id=str(ag.escritorio_id)
                                ).inc()
                            except Exception:
                                pass
                        except Exception as exc:
                            logger.error(
                                "agendamento_alerta_conflito_falhou",
                                agendamento_id=ag.id,
                                erro=str(exc),
                            )
        finally:
            await evolution.close()
            await redis_client.aclose()
        return alertas

    alertas = asyncio.run(_run())
    if alertas:
        logger.info("agendamento_alertas_conflito_enviados", total=alertas)
    return {"alertas": alertas}
