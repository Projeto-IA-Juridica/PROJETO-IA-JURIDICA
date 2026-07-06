from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from feature_1_ia_personalizada.services.agendamento import AgendamentoDetector
from feature_1_ia_personalizada.services.agendamento.prazos import buscar_prazos_escritorio
from shared.database.session import get_db
from shared.models.agendamento import Agendamento
from shared.models.cliente import Cliente
from shared.models.disponibilidade_advogado import DisponibilidadeAdvogado
from shared.models.escritorio import Escritorio
from shared.schemas.agendamento import (
    AgendamentoResponse,
    DisponibilidadeItem,
    DisponibilidadeResponse,
    EventosAgendaResponse,
    PrazoAgendaItem,
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

    return [
        SlotResponse(inicio=s.inicio, fim=s.fim, label=s.label, conflito_prazo=s.conflito_prazo)
        for s in slots
    ]


# ---------------------------------------------------------------------------
# GET /agenda/eventos — itens da semana para a aba Agenda
# ---------------------------------------------------------------------------

_PRAZOS_CACHE_TTL_S = 120


async def _prazos_com_cache(
    request: Request, db: AsyncSession, escritorio_id: int
) -> list[PrazoAgendaItem]:
    """Varre os processos por prazos com cache Redis de 2 min (polling do frontend)."""
    import json

    redis = getattr(request.app.state, "redis_client", None)
    cache_key = f"agenda_prazos:{escritorio_id}"

    if redis is not None:
        try:
            cached = await redis.get(cache_key)
            if cached:
                return [PrazoAgendaItem(**item) for item in json.loads(cached)]
        except Exception:
            pass  # cache é otimização — falha não bloqueia

    prazos = await buscar_prazos_escritorio(db, escritorio_id)
    ids_clientes = list({p.cliente_id for p in prazos})
    nomes: dict[int, str] = {}
    if ids_clientes:
        nome_rows = (
            await db.execute(select(Cliente.id, Cliente.nome).where(Cliente.id.in_(ids_clientes)))
        ).all()
        nomes = {r.id: r.nome for r in nome_rows}

    items = [
        PrazoAgendaItem(
            data=p.data,
            descricao=p.descricao,
            processo_id=p.processo_id,
            cliente_id=p.cliente_id,
            cliente_nome=nomes.get(p.cliente_id),
            numero_cnj=p.numero_cnj,
        )
        for p in prazos
    ]

    if redis is not None:
        try:
            payload = json.dumps([i.model_dump(mode="json") for i in items], ensure_ascii=False)
            await redis.set(cache_key, payload, ex=_PRAZOS_CACHE_TTL_S)
        except Exception:
            pass

    return items


@router.get("/eventos", response_model=EventosAgendaResponse)
async def listar_eventos_agenda(
    request: Request,
    db: AsyncSession = Depends(get_db),
    inicio: datetime = Query(description="Início do intervalo (ISO, com timezone)"),
    fim: datetime = Query(description="Fim do intervalo (ISO, com timezone)"),
) -> EventosAgendaResponse:
    """
    Eventos da agenda semanal:
      - agendamentos confirmados e aguardando aprovação com horário no intervalo
      - prazos processuais detectados nos andamentos (read-only, linha vermelha)
      - tem_disponibilidade para o empty state de configuração
    """
    eid = _escritorio_id(request)

    if fim <= inicio:
        raise HTTPException(status_code=422, detail="fim deve ser posterior a inicio")
    if (fim - inicio).days > 62:
        raise HTTPException(status_code=422, detail="Intervalo máximo de 62 dias")

    rows = (
        (
            await db.execute(
                select(Agendamento)
                .where(
                    Agendamento.escritorio_id == eid,
                    Agendamento.status.in_(["confirmado", "aguardando_advogado"]),
                    Agendamento.data_hora_inicio.isnot(None),
                    Agendamento.data_hora_inicio >= inicio,
                    Agendamento.data_hora_inicio <= fim,
                )
                .order_by(Agendamento.data_hora_inicio)
            )
        )
        .scalars()
        .all()
    )

    ids_clientes = list({r.cliente_id for r in rows})
    nomes_map: dict[int, str] = {}
    if ids_clientes:
        nome_rows = (
            await db.execute(select(Cliente.id, Cliente.nome).where(Cliente.id.in_(ids_clientes)))
        ).all()
        nomes_map = {r.id: r.nome for r in nome_rows}

    agendamentos = []
    for ag in rows:
        resp = AgendamentoResponse.model_validate(ag)
        resp.cliente_nome = nomes_map.get(ag.cliente_id)
        agendamentos.append(resp)

    # Prazos da semana (best-effort — extração regex dos andamentos).
    # A varredura dos processos é cacheada no Redis por 2 min: o frontend faz
    # polling a cada 15s e não deve re-escanear a carteira inteira a cada ciclo.
    prazos_items: list[PrazoAgendaItem] = []
    try:
        todos_prazos = await _prazos_com_cache(request, db, eid)
        data_ini, data_fim = inicio.date(), fim.date()
        prazos_items = [p for p in todos_prazos if data_ini <= p.data <= data_fim]
    except Exception as exc:
        logger.warning("agenda_prazos_falhou", escritorio_id=eid, erro=str(exc))

    tem_disponibilidade = (
        await db.execute(
            select(DisponibilidadeAdvogado.id)
            .where(
                DisponibilidadeAdvogado.escritorio_id == eid,
                DisponibilidadeAdvogado.ativo.is_(True),
            )
            .limit(1)
        )
    ).first() is not None

    return EventosAgendaResponse(
        agendamentos=agendamentos,
        prazos=prazos_items,
        tem_disponibilidade=tem_disponibilidade,
    )
