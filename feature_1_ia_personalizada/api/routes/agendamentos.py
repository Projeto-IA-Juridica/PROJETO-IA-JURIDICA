from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from feature_1_ia_personalizada.services.agendamento import AgendamentoDetector
from shared.database.session import get_db
from shared.models.agendamento import Agendamento
from shared.models.cliente import Cliente
from shared.models.escritorio import Escritorio
from shared.schemas.agendamento import (
    AgendamentoResponse,
    CancelarRequest,
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
    return data


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
        result.append(resp)
    return result


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
        ag.status = "confirmado"
        ag.canal_aprovacao = "hub"
        ag.resposta_advogado_em = datetime.now(UTC)
        ag.data_hora_inicio = datetime.fromisoformat(opcao["inicio"])
        ag.data_hora_fim = datetime.fromisoformat(opcao["fim"])
        await db.flush()
    finally:
        if r:
            await r.delete(lock_key)

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

        detector = AgendamentoDetector(db=db, escritorio_id=eid, timezone_str=tz_str)
        slots = await detector.buscar_slots(num_slots=3)

        if not slots:
            raise HTTPException(
                status_code=409,
                detail="Não há slots disponíveis nos próximos 30 dias",
            )

        ag.opcoes_propostas = [
            {"inicio": s.inicio.isoformat(), "fim": s.fim.isoformat(), "label": s.label}
            for s in slots
        ]
        ag.opcao_selecionada_pos = None
        ag.status = "aguardando_cliente"
        ag.proposta_enviada_em = None
        ag.expira_em = datetime.now(UTC) + timedelta(hours=_PROPOSTA_TTL_H)
        ag.whatsapp_proposta_cliente_enviado = False
        ag.whatsapp_notificacao_advogado_enviado = False
        if body.nota_advogado:
            ag.nota_advogado = body.nota_advogado
        await db.flush()
    finally:
        if r:
            await r.delete(lock_key)

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

    ag.status = "cancelado"
    ag.motivo_cancelamento = body.motivo
    await db.flush()

    logger.info("agendamento_cancelado", id=agendamento_id, escritorio_id=eid)
    return await _to_response(ag, db)
