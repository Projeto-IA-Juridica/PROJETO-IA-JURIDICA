from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database.session import get_db
from shared.models.processo import Processo
from shared.schemas.processo import (
    ProcessoCreate,
    ProcessoList,
    ProcessoResponse,
    ProcessoUpdate,
    _NIVEIS_SCORE_VALIDOS,
)
from shared.utils.lgpd import registrar_acesso

router = APIRouter(prefix="/processos", tags=["Processos Jurídicos"])


def _get_escritorio_id(request: Request) -> int:
    """Helper para extrair o escritorio_id injetado pelo JWTAuthMiddleware"""
    if not hasattr(request.state, "user_payload"):
        raise HTTPException(status_code=401, detail="Não autenticado")
    return int(request.state.user_payload.get("escritorio_id"))


def _get_user_id(request: Request) -> int:
    payload = getattr(request.state, "user_payload", {})
    return int(payload.get("sub", 0))


def _get_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return str(forwarded).split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.get("", response_model=ProcessoList)
async def list_processos(
    request: Request,
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status_processo: str | None = Query(None, alias="status"),
    cliente_id: int | None = None,
    search: str | None = Query(None, min_length=3, description="Busca por CNJ"),
    score_nivel: str | None = Query(
        None,
        description="Filtra por nível de risco: baixo | moderado | alto | critico",
    ),
):
    """
    Lista os processos do escritório logado (paginado).
    - Exclusivo: Oculta dados de outros escritórios (Multi-tenant).
    - Suporta filtros opcionais por status, cliente_id, busca de CNJ e score_nivel.
    """
    escritorio_id = _get_escritorio_id(request)

    # Valida score_nivel antes de qualquer I/O
    if score_nivel is not None and score_nivel not in _NIVEIS_SCORE_VALIDOS:
        raise HTTPException(
            status_code=422,
            detail=f"score_nivel inválido. Opções: {sorted(_NIVEIS_SCORE_VALIDOS)}",
        )

    registrar_acesso(
        _get_user_id(request),
        f"processos:escritorio:{escritorio_id}",
        "leitura",
        _get_ip(request),
    )

    stmt = select(Processo).where(Processo.escritorio_id == escritorio_id)

    if status_processo:
        stmt = stmt.where(Processo.status == status_processo)
    if cliente_id:
        stmt = stmt.where(Processo.cliente_id == cliente_id)
    if search:
        stmt = stmt.where(Processo.numero_cnj.ilike(f"%{search}%"))
    if score_nivel:
        stmt = stmt.where(Processo.score_nivel == score_nivel)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = await db.scalar(count_stmt)

    stmt = stmt.order_by(Processo.created_at.desc())
    stmt = stmt.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(stmt)
    processos = result.scalars().all()

    total_valid = total or 0

    return ProcessoList(
        items=list(processos),  # type: ignore[arg-type]
        page=page,
        per_page=per_page,
        total=total_valid,
    )


@router.post("", response_model=ProcessoResponse, status_code=status.HTTP_201_CREATED)
async def create_processo(
    payload: ProcessoCreate, request: Request, db: AsyncSession = Depends(get_db)
):
    """
    Cadastra um novo processo para acompanhamento.
    Verifica se o CNJ já foi cadastrado neste escritório.
    """
    escritorio_id = _get_escritorio_id(request)
    registrar_acesso(
        _get_user_id(request),
        f"processo:novo:cliente:{payload.cliente_id}",
        "escrita",
        _get_ip(request),
    )

    stmt = select(Processo).where(
        and_(
            Processo.escritorio_id == escritorio_id,
            Processo.numero_cnj == payload.numero_cnj,
        )
    )
    result = await db.execute(stmt)
    if result.scalars().first():
        raise HTTPException(
            status_code=400,
            detail="Este processo (CNJ) já está cadastrado para o seu escritório.",
        )

    novo_processo = Processo(
        escritorio_id=escritorio_id,
        numero_cnj=payload.numero_cnj,
        cliente_id=payload.cliente_id,
        polo_cliente=payload.polo_cliente,
        tipo_acao=payload.tipo_acao,
        status="ativo",
        monitoramento_ativo=True,
    )

    db.add(novo_processo)
    await db.flush()

    return novo_processo


@router.get("/{processo_id}", response_model=ProcessoResponse)
async def get_processo(processo_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    """
    Detalha um processo específico, garantindo que pertença ao escritório do usuário.
    Inclui score de risco quando calculado (null se o worker ainda não processou).
    """
    escritorio_id = _get_escritorio_id(request)

    processo = await db.get(Processo, processo_id)
    if not processo or processo.escritorio_id != escritorio_id:
        raise HTTPException(
            status_code=404,
            detail="Processo não encontrado ou sem permissão de acesso.",
        )

    registrar_acesso(_get_user_id(request), f"processo:{processo_id}", "leitura", _get_ip(request))
    return processo


@router.put("/{processo_id}", response_model=ProcessoResponse)
async def update_processo(
    processo_id: int,
    payload: ProcessoUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Edita dados manuais de um processo (Polo, Advogado, Frequencia de Monitoramento)."""
    escritorio_id = _get_escritorio_id(request)

    processo = await db.get(Processo, processo_id)
    if not processo or processo.escritorio_id != escritorio_id:
        raise HTTPException(status_code=404, detail="Processo não encontrado ou sem permissão.")

    registrar_acesso(_get_user_id(request), f"processo:{processo_id}", "escrita", _get_ip(request))

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(processo, key, value)

    await db.flush()
    await db.refresh(processo)
    return processo


@router.delete("/{processo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_processo(processo_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    """
    Soft delete: arquiva o processo e desativa o monitoramento.
    """
    escritorio_id = _get_escritorio_id(request)

    processo = await db.get(Processo, processo_id)
    if not processo or processo.escritorio_id != escritorio_id:
        raise HTTPException(status_code=404, detail="Processo não encontrado ou sem permissão.")

    registrar_acesso(_get_user_id(request), f"processo:{processo_id}", "exclusao", _get_ip(request))

    processo.status = "arquivado"
    processo.monitoramento_ativo = False

    await db.flush()
    return None