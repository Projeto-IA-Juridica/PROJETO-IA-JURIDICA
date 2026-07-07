from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from feature_1_ia_personalizada.services.agendamento import AgendamentoDetector
from feature_1_ia_personalizada.services.agendamento.eventos import (
    canal_agendamento,
    publicar_evento_agendamento,
)
from feature_1_ia_personalizada.services.agendamento.prazos import (
    buscar_prazos_escritorio,
    datas_a_evitar,
    descrever_conflito,
)
from shared.database.session import get_db
from shared.models.agendamento import Agendamento
from shared.models.cliente import Cliente
from shared.models.escritorio import Escritorio
from shared.models.interacao import Interacao
from shared.schemas.agendamento import (
    AgendamentoResponse,
    CancelarRequest,
    MensagemContexto,
    SugerirRequest,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/agendamentos", tags=["Agendamento — Hub"])

_LOCK_TTL_S = 30
_PROPOSTA_TTL_H = 48
_STATUS_VALIDOS = {
    "aguardando_cliente",
    "aguardando_advogado",
    "confirmado",
    "cancelado",
    "expirado",
}


def _escritorio_id(request: Request) -> int:
    if not hasattr(request.state, "user_payload"):
        raise HTTPException(status_code=401, detail="Não autenticado")
    return int(request.state.user_payload["escritorio_id"])


def _redis(request: Request) -> Any:
    return getattr(request.app.state, "redis_client", None)


async def _get_agendamento(
    agendamento_id: int,
    escritorio_id: int,
    db: AsyncSession,
) -> Agendamento:
    row = (
        await db.execute(
            select(Agendamento).where(
                Agendamento.id == agendamento_id,
                Agendamento.escritorio_id == escritorio_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado")
    return row


async def _to_response(ag: Agendamento, db: AsyncSession) -> AgendamentoResponse:
    nome = (
        await db.execute(select(Cliente.nome).where(Cliente.id == ag.cliente_id))
    ).scalar_one_or_none()

    data = AgendamentoResponse.model_validate(ag)
    data.cliente_nome = nome
    await _enriquecer_pendente(data, ag, db)
    return data


_MAX_CHARS_CONTEXTO = 280


async def _enriquecer_pendente(
    resp: AgendamentoResponse, ag: Agendamento, db: AsyncSession
) -> None:
    """
    Para cards aguardando aprovação: adiciona o contexto da conversa que originou
    o pedido e o alerta de conflito com prazo processual (aviso, nunca bloqueio).
    """
    if ag.status != "aguardando_advogado":
        return

    # Contexto da conversa — últimas interações do cliente (mais antigas primeiro)
    try:
        interacoes = (
            (
                await db.execute(
                    select(Interacao)
                    .where(
                        Interacao.escritorio_id == ag.escritorio_id,
                        Interacao.cliente_id == ag.cliente_id,
                    )
                    .order_by(Interacao.created_at.desc())
                    .limit(3)
                )
            )
            .scalars()
            .all()
        )
        contexto: list[MensagemContexto] = []
        for i in reversed(interacoes):
            if i.mensagem_cliente:
                contexto.append(
                    MensagemContexto(
                        autor="cliente", texto=i.mensagem_cliente[:_MAX_CHARS_CONTEXTO]
                    )
                )
            if i.mensagem_ia:
                contexto.append(
                    MensagemContexto(autor="ia", texto=i.mensagem_ia[:_MAX_CHARS_CONTEXTO])
                )
        resp.contexto_conversa = contexto[-6:]
    except Exception as exc:
        logger.warning("agendamento_contexto_falhou", agendamento_id=ag.id, erro=str(exc))

    # Conflito de prazo — recalculado na leitura (novos andamentos podem trazer prazos)
    try:
        if ag.data_hora_inicio is not None:
            tz_str = (
                await db.execute(
                    select(Escritorio.timezone).where(Escritorio.id == ag.escritorio_id)
                )
            ).scalar_one_or_none() or "America/Sao_Paulo"
            from zoneinfo import ZoneInfo

            prazos = await buscar_prazos_escritorio(db, ag.escritorio_id, cliente_id=ag.cliente_id)
            dia_local = ag.data_hora_inicio.astimezone(ZoneInfo(tz_str)).date()
            descricao = descrever_conflito(dia_local, prazos)
            if descricao:
                resp.conflito_prazo = True
                resp.conflito_descricao = descricao
        # Fallback: flag gravada na opção quando a proposta foi gerada
        if not resp.conflito_prazo and ag.opcoes_propostas and ag.opcao_selecionada_pos is not None:
            try:
                opcao = ag.opcoes_propostas[ag.opcao_selecionada_pos]
                if opcao.get("conflito_prazo"):
                    resp.conflito_prazo = True
                    resp.conflito_descricao = (
                        resp.conflito_descricao
                        or "Horário próximo a um prazo processual — verifique a agenda"
                    )
            except (IndexError, TypeError):
                pass
    except Exception as exc:
        logger.warning("agendamento_conflito_falhou", agendamento_id=ag.id, erro=str(exc))


def _enfileirar_mensagem_pos_acao(agendamento_id: int, acao: str) -> None:
    """
    Dispara o envio WhatsApp fora do ciclo HTTP (Celery, fila ia).
    Chamar SEMPRE após commit — o worker abre sessão própria e leria estado
    antigo se a transação ainda não estivesse persistida.
    """
    try:
        from feature_1_ia_personalizada.workers.agendamento_worker import (
            enviar_mensagens_pos_acao,
        )

        enviar_mensagens_pos_acao.delay(agendamento_id=agendamento_id, acao=acao)
    except Exception as exc:
        logger.error(
            "agendamento_pos_acao_dispatch_falhou",
            agendamento_id=agendamento_id,
            acao=acao,
            erro=str(exc),
        )


# ---------------------------------------------------------------------------
# GET /agendamentos
# ---------------------------------------------------------------------------


@router.get("", response_model=list[AgendamentoResponse])
async def listar_agendamentos(
    request: Request,
    db: AsyncSession = Depends(get_db),
    status_filtro: str | None = Query(default=None, alias="status"),
    data_inicio: datetime | None = Query(default=None),
    data_fim: datetime | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> list[AgendamentoResponse]:
    eid = _escritorio_id(request)

    if status_filtro and status_filtro not in _STATUS_VALIDOS:
        raise HTTPException(
            status_code=422,
            detail=f"status inválido. Opções: {sorted(_STATUS_VALIDOS)}",
        )

    stmt = (
        select(Agendamento)
        .where(Agendamento.escritorio_id == eid)
        .order_by(Agendamento.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    if status_filtro:
        stmt = stmt.where(Agendamento.status == status_filtro)
    if data_inicio:
        stmt = stmt.where(Agendamento.data_hora_inicio >= data_inicio)
    if data_fim:
        stmt = stmt.where(Agendamento.data_hora_inicio <= data_fim)

    rows = (await db.execute(stmt)).scalars().all()

    # Busca nomes em batch
    ids_clientes = list({r.cliente_id for r in rows})
    nomes_map: dict[int, str] = {}
    if ids_clientes:
        nome_rows = (
            await db.execute(select(Cliente.id, Cliente.nome).where(Cliente.id.in_(ids_clientes)))
        ).all()
        nomes_map = {r.id: r.nome for r in nome_rows}

    result = []
    for ag in rows:
        resp = AgendamentoResponse.model_validate(ag)
        resp.cliente_nome = nomes_map.get(ag.cliente_id)
        # Cards de aprovação precisam de contexto + alerta de prazo (polling do Hub)
        await _enriquecer_pendente(resp, ag, db)
        result.append(resp)
    return result


# ---------------------------------------------------------------------------
# GET /agendamentos/stream — Server-Sent Events (tempo real)
# ---------------------------------------------------------------------------

_SSE_POLL_TIMEOUT_S = 25.0  # sem evento nesse intervalo → heartbeat


@router.get("/stream", include_in_schema=False)
async def stream_agendamentos(request: Request) -> StreamingResponse:
    """
    Stream SSE de mudanças nos agendamentos do escritório (Redis pub/sub).

    Cada transição de estado publica "changed"; o frontend invalida as
    queries e re-busca pelos endpoints normais. Declarada ANTES de /{id}
    para "stream" não colidir com o path param inteiro.
    """
    eid = _escritorio_id(request)
    r = _redis(request)
    if r is None:
        raise HTTPException(status_code=503, detail="Tempo real indisponível (Redis offline)")

    async def gerar() -> Any:
        pubsub = r.pubsub()
        await pubsub.subscribe(canal_agendamento(eid))
        logger.info("agendamento_sse_conectado", escritorio_id=eid)
        try:
            # retry orienta o EventSource/cliente a reconectar em 5s
            yield "retry: 5000\n\n"
            while True:
                if await request.is_disconnected():
                    break
                msg = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=_SSE_POLL_TIMEOUT_S
                )
                if msg is not None and msg.get("type") == "message":
                    yield "event: agendamentos\ndata: changed\n\n"
                else:
                    yield ": ping\n\n"  # heartbeat mantém proxies/conexão vivos
        finally:
            try:
                await pubsub.unsubscribe(canal_agendamento(eid))
                await pubsub.aclose()
            except Exception:
                pass
            logger.info("agendamento_sse_desconectado", escritorio_id=eid)

    return StreamingResponse(
        gerar(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # desativa buffering em nginx
        },
    )


# ---------------------------------------------------------------------------
# GET /agendamentos/{id}
# ---------------------------------------------------------------------------


@router.get("/{agendamento_id}", response_model=AgendamentoResponse)
async def detalhe_agendamento(
    agendamento_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AgendamentoResponse:
    eid = _escritorio_id(request)
    ag = await _get_agendamento(agendamento_id, eid, db)
    return await _to_response(ag, db)


# ---------------------------------------------------------------------------
# POST /agendamentos/{id}/confirmar
# ---------------------------------------------------------------------------


@router.post(
    "/{agendamento_id}/confirmar",
    response_model=AgendamentoResponse,
    status_code=status.HTTP_200_OK,
)
async def confirmar_agendamento(
    agendamento_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AgendamentoResponse:
    eid = _escritorio_id(request)
    ag = await _get_agendamento(agendamento_id, eid, db)

    # Idempotência: qualquer canal que confirmou primeiro → hub retorna 200 sem re-processar
    if ag.status == "confirmado":
        return await _to_response(ag, db)

    if ag.status != "aguardando_advogado":
        raise HTTPException(
            status_code=409,
            detail=f"Agendamento não pode ser confirmado no status '{ag.status}'",
        )

    if ag.opcao_selecionada_pos is None or not ag.opcoes_propostas:
        raise HTTPException(
            status_code=409,
            detail="Cliente ainda não selecionou uma opção",
        )

    # Redis lock — previne dupla confirmação concorrente
    r = _redis(request)
    lock_key = f"agendamento_confirmar:{agendamento_id}"
    if r:
        acquired = await r.set(lock_key, "1", ex=_LOCK_TTL_S, nx=True)
        if not acquired:
            raise HTTPException(status_code=409, detail="Confirmação em andamento, aguarde")

    try:
        pos = ag.opcao_selecionada_pos
        if pos >= len(ag.opcoes_propostas):
            raise HTTPException(
                status_code=409,
                detail=f"opcao_selecionada_pos={pos} fora do range (total={len(ag.opcoes_propostas)})",
            )
        opcao = ag.opcoes_propostas[pos]
        agora = datetime.now(UTC)
        ag.status = "confirmado"
        ag.canal_aprovacao = "hub"
        ag.resposta_advogado_em = agora
        ag.data_hora_inicio = datetime.fromisoformat(opcao["inicio"])
        ag.data_hora_fim = datetime.fromisoformat(opcao["fim"])
        # Commit explícito ANTES de enfileirar o envio — o worker abre sessão própria
        await db.commit()
    finally:
        if r:
            await r.delete(lock_key)

    try:
        from feature_1_ia_personalizada.api.routes.metrics import (
            agendamentos_confirmados_total,
            tempo_aprovacao_advogado_segundos,
        )

        agendamentos_confirmados_total.labels(escritorio_id=str(eid)).inc()
        if ag.resposta_cliente_em:
            delta = (agora - ag.resposta_cliente_em).total_seconds()
            if delta >= 0:
                tempo_aprovacao_advogado_segundos.labels(escritorio_id=str(eid)).observe(delta)
    except Exception:
        pass

    _enfileirar_mensagem_pos_acao(agendamento_id, "confirmado")
    await publicar_evento_agendamento(r, eid)

    logger.info("agendamento_confirmado", id=agendamento_id, canal="hub", escritorio_id=eid)
    return await _to_response(ag, db)


# ---------------------------------------------------------------------------
# POST /agendamentos/{id}/sugerir
# ---------------------------------------------------------------------------


@router.post(
    "/{agendamento_id}/sugerir",
    response_model=AgendamentoResponse,
    status_code=status.HTTP_200_OK,
)
async def sugerir_novos_horarios(
    agendamento_id: int,
    body: SugerirRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AgendamentoResponse:
    eid = _escritorio_id(request)
    ag = await _get_agendamento(agendamento_id, eid, db)

    if ag.status != "aguardando_advogado":
        raise HTTPException(
            status_code=409,
            detail=f"Agendamento não está aguardando aprovação (status='{ag.status}')",
        )

    r = _redis(request)
    lock_key = f"agendamento_sugerir:{agendamento_id}"
    if r:
        acquired = await r.set(lock_key, "1", ex=_LOCK_TTL_S, nx=True)
        if not acquired:
            raise HTTPException(status_code=409, detail="Sugestão em andamento, aguarde")

    try:
        tz_str = (
            await db.execute(select(Escritorio.timezone).where(Escritorio.id == eid))
        ).scalar_one_or_none() or "America/Sao_Paulo"

        # Prazos do cliente entram como dias a evitar nas novas opções
        prazos = await buscar_prazos_escritorio(db, eid, cliente_id=ag.cliente_id)
        detector = AgendamentoDetector(db=db, escritorio_id=eid, timezone_str=tz_str)
        slots = await detector.buscar_slots(num_slots=3, datas_evitar=datas_a_evitar(prazos))

        if not slots:
            raise HTTPException(
                status_code=409,
                detail="Não há slots disponíveis nos próximos 30 dias",
            )

        ag.opcoes_propostas = [
            {
                "inicio": s.inicio.isoformat(),
                "fim": s.fim.isoformat(),
                "label": s.label,
                "conflito_prazo": s.conflito_prazo,
            }
            for s in slots
        ]
        ag.opcao_selecionada_pos = None
        ag.data_hora_inicio = None
        ag.data_hora_fim = None
        ag.status = "aguardando_cliente"
        ag.proposta_enviada_em = None
        ag.expira_em = datetime.now(UTC) + timedelta(hours=_PROPOSTA_TTL_H)
        ag.whatsapp_proposta_cliente_enviado = False
        ag.whatsapp_notificacao_advogado_enviado = False
        # Reset também das flags de confirmação: sem isso, uma reunião remarcada
        # e reconfirmada nunca enviaria a confirmação/lembrete da NOVA data
        ag.whatsapp_confirmacao_cliente_enviado = False
        ag.whatsapp_confirmacao_pre_reuniao_enviado = False
        if body.nota_advogado:
            ag.nota_advogado = body.nota_advogado
        await db.commit()
    finally:
        if r:
            await r.delete(lock_key)

    _enfileirar_mensagem_pos_acao(agendamento_id, "proposta")
    await publicar_evento_agendamento(r, eid)

    logger.info("agendamento_sugeriu_novos_horarios", id=agendamento_id, escritorio_id=eid)
    return await _to_response(ag, db)


# ---------------------------------------------------------------------------
# POST /agendamentos/{id}/cancelar
# ---------------------------------------------------------------------------


@router.post(
    "/{agendamento_id}/cancelar",
    response_model=AgendamentoResponse,
    status_code=status.HTTP_200_OK,
)
async def cancelar_agendamento(
    agendamento_id: int,
    body: CancelarRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AgendamentoResponse:
    eid = _escritorio_id(request)
    ag = await _get_agendamento(agendamento_id, eid, db)

    if ag.status in {"cancelado", "expirado"}:
        raise HTTPException(
            status_code=409,
            detail=f"Agendamento já está '{ag.status}'",
        )

    # Cliente só é avisado se já participava do fluxo (recebeu proposta/confirmação)
    notificar_cliente = ag.status in {"aguardando_cliente", "aguardando_advogado", "confirmado"}

    ag.status = "cancelado"
    ag.motivo_cancelamento = body.motivo
    await db.commit()

    if notificar_cliente and ag.whatsapp_proposta_cliente_enviado:
        _enfileirar_mensagem_pos_acao(agendamento_id, "cancelado")
    await publicar_evento_agendamento(_redis(request), eid)

    logger.info("agendamento_cancelado", id=agendamento_id, escritorio_id=eid)
    return await _to_response(ag, db)
