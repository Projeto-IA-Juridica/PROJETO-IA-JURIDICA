from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from feature_1_ia_personalizada.services.agendamento import AgendamentoDetector
from shared.database.session import get_db
from shared.models.disponibilidade_advogado import DisponibilidadeAdvogado
from shared.models.escritorio import Escritorio
from shared.schemas.agendamento import (
    DisponibilidadeItem,
    DisponibilidadeResponse,
    SlotResponse,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/agenda", tags=["Agendamento — Configuração"])


def _escritorio_id(request: Request) -> int:
    if not hasattr(request.state, "user_payload"):
        raise HTTPException(status_code=401, detail="Não autenticado")
    return int(request.state.user_payload["escritorio_id"])


# ---------------------------------------------------------------------------
# GET /agenda/disponibilidade
# ---------------------------------------------------------------------------


@router.get("/disponibilidade", response_model=list[DisponibilidadeResponse])
async def listar_disponibilidade(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> list[DisponibilidadeResponse]:
    eid = _escritorio_id(request)

    rows = (
        (
            await db.execute(
                select(DisponibilidadeAdvogado)
                .where(DisponibilidadeAdvogado.escritorio_id == eid)
                .order_by(DisponibilidadeAdvogado.dia_semana)
            )
        )
        .scalars()
        .all()
    )

    return [DisponibilidadeResponse.model_validate(r) for r in rows]


# ---------------------------------------------------------------------------
# PUT /agenda/disponibilidade
# ---------------------------------------------------------------------------


@router.put("/disponibilidade", response_model=list[DisponibilidadeResponse])
async def atualizar_disponibilidade(
    body: list[DisponibilidadeItem],
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> list[DisponibilidadeResponse]:
    eid = _escritorio_id(request)

    if len(body) > 6:
        raise HTTPException(status_code=422, detail="Máximo de 6 entradas (seg–sáb)")

    dias_vistos: set[int] = set()
    for item in body:
        if item.dia_semana in dias_vistos:
            raise HTTPException(
                status_code=422,
                detail=f"dia_semana {item.dia_semana} duplicado na requisição",
            )
        dias_vistos.add(item.dia_semana)
        if item.hora_fim <= item.hora_inicio:
            raise HTTPException(
                status_code=422,
                detail=f"hora_fim deve ser maior que hora_inicio (dia_semana={item.dia_semana})",
            )

    # Substituição total — delete + insert é mais simples que upsert com 6 linhas máximo
    await db.execute(
        delete(DisponibilidadeAdvogado).where(DisponibilidadeAdvogado.escritorio_id == eid)
    )

    novos: list[DisponibilidadeAdvogado] = []
    for item in body:
        row = DisponibilidadeAdvogado(
            escritorio_id=eid,
            dia_semana=item.dia_semana,
            hora_inicio=item.hora_inicio,
            hora_fim=item.hora_fim,
            ativo=item.ativo,
        )
        db.add(row)
        novos.append(row)

    await db.flush()

    logger.info("disponibilidade_atualizada", escritorio_id=eid, dias=len(novos))
    return [DisponibilidadeResponse.model_validate(r) for r in novos]


# ---------------------------------------------------------------------------
# GET /agenda/slots
# ---------------------------------------------------------------------------


@router.get("/slots", response_model=list[SlotResponse])
async def listar_slots_disponiveis(
    request: Request,
    db: AsyncSession = Depends(get_db),
    num_slots: int = Query(default=3, ge=1, le=10),
    duracao_min: int = Query(default=60, ge=15, le=480),
) -> list[Any]:
    eid = _escritorio_id(request)

    escritorio = (
        await db.execute(select(Escritorio.timezone).where(Escritorio.id == eid))
    ).scalar_one_or_none()

    if escritorio is None:
        raise HTTPException(status_code=404, detail="Escritório não encontrado")

    detector = AgendamentoDetector(
        db=db,
        escritorio_id=eid,
        timezone_str=escritorio,
    )
    slots = await detector.buscar_slots(num_slots=num_slots, duracao_min=duracao_min)

    return [SlotResponse(inicio=s.inicio, fim=s.fim, label=s.label) for s in slots]
