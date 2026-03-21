"""
feature_1_ia_personalizada/api/routes/crm.py
=============================================
Endpoints CRM Inteligente (Feature 7).

Todos os endpoints exigem JWT. O escritorio_id é extraído do token —
nunca do body — para garantir isolamento multi-tenant.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from feature_1_ia_personalizada.services.ai.claude_client import ClaudeClient
from feature_1_ia_personalizada.services.crm.analyzer import CRMAnalyzer, CRMAnaliseResult
from feature_1_ia_personalizada.workers.crm_worker import crm_analisar_escritorio
from shared.config.settings import settings
from shared.database.session import get_db
from shared.models.cliente import Cliente
from shared.models.interacao import Interacao
from shared.schemas.cliente import CRMClienteCard

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/crm", tags=["CRM Inteligente"])

_NIVEIS_VALIDOS = {"excelente", "satisfeito", "neutro", "em_risco", "critico"}
_RATE_LIMIT_ANALISE_MANUAL_TTL = 300   # 5 minutos por cliente
_RATE_LIMIT_ESCRITORIO_TTL = 14_400    # 4 horas por escritório


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _escritorio_id(request: Request) -> int:
    if not hasattr(request.state, "user_payload"):
        raise HTTPException(status_code=401, detail="Não autenticado")
    return int(request.state.user_payload["escritorio_id"])


def _redis(request: Request):
    return request.app.state.redis_client


async def _get_crm_card(db: AsyncSession, cliente_id: int, escritorio_id: int) -> CRMClienteCard:
    """Monta um CRMClienteCard com métricas agregadas em uma query."""
    stmt = (
        select(
            Cliente.id,
            Cliente.nome,
            Cliente.telefone_whatsapp,
            Cliente.crm_nivel,
            Cliente.crm_score,
            Cliente.crm_resumo,
            Cliente.crm_acao_sugerida,
            Cliente.crm_analisado_em,
            func.count(Interacao.id).label("total_interacoes"),
            func.avg(Interacao.satisfacao).label("nps_medio"),
            func.max(Interacao.created_at).label("ultimo_contato"),
        )
        .outerjoin(Interacao, Interacao.cliente_id == Cliente.id)
        .where(
            Cliente.id == cliente_id,
            Cliente.escritorio_id == escritorio_id,
            Cliente.ativo == True,
        )
        .group_by(
            Cliente.id,
            Cliente.nome,
            Cliente.telefone_whatsapp,
            Cliente.crm_nivel,
            Cliente.crm_score,
            Cliente.crm_resumo,
            Cliente.crm_acao_sugerida,
            Cliente.crm_analisado_em,
        )
    )
    row = (await db.execute(stmt)).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    # Conta processos ativos via subquery separada para manter a query principal limpa
    from shared.models.processo import Processo
    total_proc = (
        await db.execute(
            select(func.count()).where(
                Processo.cliente_id == cliente_id,
                Processo.escritorio_id == escritorio_id,
                Processo.status == "ativo",
            )
        )
    ).scalar_one()

    return CRMClienteCard(
        id=row.id,
        nome=row.nome,
        telefone_whatsapp=row.telefone_whatsapp,
        crm_nivel=row.crm_nivel,
        crm_score=row.crm_score,
        crm_resumo=row.crm_resumo,
        crm_acao_sugerida=row.crm_acao_sugerida,
        crm_analisado_em=row.crm_analisado_em,
        total_processos=total_proc,
        nps_medio=round(float(row.nps_medio), 2) if row.nps_medio else None,
        ultimo_contato=row.ultimo_contato,
    )


# ---------------------------------------------------------------------------
# GET /crm/clientes
# ---------------------------------------------------------------------------

@router.get("/clientes", response_model=list[CRMClienteCard])
async def listar_clientes_crm(
    request: Request,
    db: AsyncSession = Depends(get_db),
    nivel: str | None = Query(None, description="excelente | satisfeito | neutro | em_risco | critico"),
    sem_analise: bool = Query(False, description="Retorna apenas clientes sem crm_nivel"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    eid = _escritorio_id(request)

    if nivel and nivel not in _NIVEIS_VALIDOS:
        raise HTTPException(status_code=422, detail=f"nivel inválido. Opções: {sorted(_NIVEIS_VALIDOS)}")

    stmt = (
        select(
            Cliente.id,
            Cliente.nome,
            Cliente.telefone_whatsapp,
            Cliente.crm_nivel,
            Cliente.crm_score,
            Cliente.crm_resumo,
            Cliente.crm_acao_sugerida,
            Cliente.crm_analisado_em,
            func.count(Interacao.id).label("total_interacoes"),
            func.avg(Interacao.satisfacao).label("nps_medio"),
            func.max(Interacao.created_at).label("ultimo_contato"),
        )
        .outerjoin(Interacao, Interacao.cliente_id == Cliente.id)
        .where(Cliente.escritorio_id == eid, Cliente.ativo == True)
        .group_by(
            Cliente.id, Cliente.nome, Cliente.telefone_whatsapp,
            Cliente.crm_nivel, Cliente.crm_score, Cliente.crm_resumo,
            Cliente.crm_acao_sugerida, Cliente.crm_analisado_em,
        )
        .order_by(Cliente.crm_score.asc().nullslast())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    if nivel:
        stmt = stmt.where(Cliente.crm_nivel == nivel)
    if sem_analise:
        stmt = stmt.where(Cliente.crm_nivel.is_(None))

    from shared.models.processo import Processo

    rows = (await db.execute(stmt)).all()
    if not rows:
        return []

    # Busca contagem de processos ativos para todos os clientes da página em uma query
    ids_pagina = [r.id for r in rows]
    proc_rows = (
        await db.execute(
            select(Processo.cliente_id, func.count().label("total"))
            .where(
                Processo.cliente_id.in_(ids_pagina),
                Processo.escritorio_id == eid,
                Processo.status == "ativo",
            )
            .group_by(Processo.cliente_id)
        )
    ).all()
    proc_por_cliente = {r.cliente_id: r.total for r in proc_rows}

    return [
        CRMClienteCard(
            id=r.id,
            nome=r.nome,
            telefone_whatsapp=r.telefone_whatsapp,
            crm_nivel=r.crm_nivel,
            crm_score=r.crm_score,
            crm_resumo=r.crm_resumo,
            crm_acao_sugerida=r.crm_acao_sugerida,
            crm_analisado_em=r.crm_analisado_em,
            total_processos=proc_por_cliente.get(r.id, 0),
            nps_medio=round(float(r.nps_medio), 2) if r.nps_medio else None,
            ultimo_contato=r.ultimo_contato,
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# GET /crm/clientes/{id}
# ---------------------------------------------------------------------------

@router.get("/clientes/{cliente_id}", response_model=CRMClienteCard)
async def detalhe_cliente_crm(
    cliente_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    eid = _escritorio_id(request)
    return await _get_crm_card(db, cliente_id, eid)


# ---------------------------------------------------------------------------
# POST /crm/clientes/{id}/analisar
# ---------------------------------------------------------------------------

@router.post("/clientes/{cliente_id}/analisar", response_model=dict)
async def analisar_cliente(
    cliente_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    eid = _escritorio_id(request)
    r = _redis(request)

    # Rate-limit atômico: SET NX antes da análise evita race condition
    chave = f"crm_rate_analise:{eid}:{cliente_id}"
    if r:
        adquiriu = await r.set(chave, "1", ex=_RATE_LIMIT_ANALISE_MANUAL_TTL, nx=True)
        if not adquiriu:
            raise HTTPException(
                status_code=429,
                detail="Análise já solicitada recentemente. Aguarde 5 minutos.",
            )

    claude = ClaudeClient(api_key=settings.ANTHROPIC_API_KEY)
    analyzer = CRMAnalyzer(claude_client=claude, db=db)

    try:
        result: CRMAnaliseResult = await analyzer.analisar_cliente(cliente_id, eid)
    except ValueError as exc:
        # Libera o lock se o cliente não existir (não faz sentido bloquear)
        if r:
            await r.delete(chave)
        raise HTTPException(status_code=404, detail=str(exc))

    return {
        "nivel": result.nivel,
        "score": result.score,
        "resumo": result.resumo,
        "acao_sugerida": result.acao_sugerida,
        "cache_hit": result.cache_hit,
        "tokens_input": result.tokens_input,
        "tokens_output": result.tokens_output,
        "custo_usd": str(result.custo),
    }


# ---------------------------------------------------------------------------
# POST /crm/analisar-escritorio
# ---------------------------------------------------------------------------

@router.post("/analisar-escritorio", status_code=status.HTTP_202_ACCEPTED)
async def analisar_escritorio(request: Request):
    eid = _escritorio_id(request)
    r = _redis(request)

    # Rate-limit atômico: SET NX antes de enfileirar evita race condition
    chave = f"crm_rate_escritorio:{eid}"
    if r:
        adquiriu = await r.set(chave, "1", ex=_RATE_LIMIT_ESCRITORIO_TTL, nx=True)
        if not adquiriu:
            raise HTTPException(
                status_code=429,
                detail="Análise do escritório já solicitada recentemente. Aguarde 4 horas.",
            )

    job = crm_analisar_escritorio.delay(eid)

    return {"job_id": job.id, "escritorio_id": eid}


# ---------------------------------------------------------------------------
# GET /crm/resumo
# ---------------------------------------------------------------------------

@router.get("/resumo")
async def resumo_crm(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    eid = _escritorio_id(request)

    # Contagens por nível + média de score + sem análise
    stmt_niveis = select(
        Cliente.crm_nivel,
        func.count().label("total"),
        func.avg(Cliente.crm_score).label("score_medio"),
    ).where(
        Cliente.escritorio_id == eid,
        Cliente.ativo == True,
    ).group_by(Cliente.crm_nivel)

    rows = (await db.execute(stmt_niveis)).all()

    contagens: dict[str, int] = {n: 0 for n in _NIVEIS_VALIDOS}
    sem_analise = 0
    scores: list[float] = []

    for r in rows:
        if r.crm_nivel is None:
            sem_analise = r.total
        else:
            contagens[r.crm_nivel] = r.total
            if r.score_medio is not None:
                scores.extend([float(r.score_medio)] * r.total)

    score_medio_escritorio = round(sum(scores) / len(scores), 1) if scores else None

    return {
        **contagens,
        "score_medio_escritorio": score_medio_escritorio,
        "sem_analise": sem_analise,
    }
