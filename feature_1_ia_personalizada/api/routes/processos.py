from datetime import datetime
from typing import Any

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from feature_1_ia_personalizada.services.legal_data.cache_manager import (
    invalidar_cache_dna_async,
    invalidar_caches_processo_async,
)
from feature_1_ia_personalizada.services.legal_data.datajud_client import (
    DataJudClient,
    DataJudClientError,
)
from feature_1_ia_personalizada.workers.celery_app import celery_app
from shared.config.settings import settings
from shared.database.connection import async_session_factory
from shared.database.session import get_db
from shared.models.processo import Processo
from shared.schemas.processo import (
    _NIVEIS_SCORE_VALIDOS,
    ProcessoCreate,
    ProcessoList,
    ProcessoResponse,
    ProcessoUpdate,
)
from shared.utils.lgpd import registrar_acesso

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/processos", tags=["Processos Jurídicos"])


def _get_escritorio_id(request: Request) -> int:
    """Helper para extrair o escritorio_id injetado pelo JWTAuthMiddleware"""
    if not hasattr(request.state, "user_payload"):
        raise HTTPException(status_code=401, detail="Não autenticado")
    escritorio_id = request.state.user_payload.get("escritorio_id")
    if escritorio_id is None:
        raise HTTPException(status_code=401, detail="Token sem escritorio_id")
    return int(escritorio_id)


def _get_user_id(request: Request) -> int:
    payload = getattr(request.state, "user_payload", {})
    user_id = payload.get("sub", 0)
    try:
        return int(user_id) if user_id else 0
    except (TypeError, ValueError):
        return 0


def _get_redis(request: Request) -> Any:
    """Retorna o redis_client do app.state, ou None se indisponível."""
    return getattr(request.app.state, "redis_client", None)


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
) -> ProcessoList:
    """
    Lista os processos do escritório logado (paginado).
    - Exclusivo: Oculta dados de outros escritórios (Multi-tenant).
    - Suporta filtros opcionais por status, cliente_id, busca de CNJ e score_nivel.
    """
    try:
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
    except HTTPException:
        raise
    except Exception as exc:
        import structlog

        logger = structlog.get_logger(__name__)
        logger.error("list_processos_erro", erro=str(exc), exc_info=True, page=page)
        raise HTTPException(
            status_code=500,
            detail="Erro ao listar processos. Tente novamente em alguns instantes.",
        ) from exc


async def _enriquecer_processo_async(processo_id: int, numero_cnj: str) -> None:
    """Busca tribunal, vara, comarca e tipo_ação no DataJud e salva no banco imediatamente."""
    try:
        client = DataJudClient(api_key=settings.DATAJUD_API_KEY)
        data = await client.consultar_processo(numero_cnj)
    except DataJudClientError as exc:
        logger.warning("enriquecimento_datajud_falhou", processo_id=processo_id, erro=str(exc))
        return
    except Exception as exc:
        logger.warning("enriquecimento_inesperado", processo_id=processo_id, erro=str(exc))
        return

    hits = data.get("hits", {}).get("hits", [])
    if not hits:
        logger.info("enriquecimento_sem_hits", processo_id=processo_id, cnj=numero_cnj)
        return

    source = hits[0].get("_source", {})
    metadados = DataJudClient._extrair_metadados(source)
    if not metadados:
        return

    campos: dict = {}
    if metadados.get("tribunal"):
        campos["tribunal"] = metadados["tribunal"]
    if metadados.get("vara"):
        campos["vara"] = metadados["vara"]
    if metadados.get("comarca"):
        campos["comarca"] = metadados["comarca"]
    if metadados.get("tipo_acao"):
        campos["tipo_acao"] = metadados["tipo_acao"]
    if metadados.get("data_distribuicao"):
        try:
            campos["data_distribuicao"] = datetime.fromisoformat(
                str(metadados["data_distribuicao"]).replace("Z", "+00:00")
            )
        except (ValueError, TypeError):
            pass
    if metadados.get("valor_causa") is not None:
        try:
            campos["valor_causa"] = float(metadados["valor_causa"])
        except (TypeError, ValueError):
            pass

    if not campos:
        return

    try:
        async with async_session_factory() as session:
            await session.execute(
                update(Processo).where(Processo.id == processo_id).values(**campos)
            )
            await session.commit()
        logger.info("enriquecimento_salvo", processo_id=processo_id, campos=list(campos.keys()))
    except Exception as exc:
        logger.warning("enriquecimento_db_falhou", processo_id=processo_id, erro=str(exc))


def _disparar_monitoramento(processo_id: int) -> None:
    """Envia task Celery de monitoramento periódico. Silencia erros (Celery pode estar indisponível)."""
    try:
        celery_app.send_task(
            "workers.monitorar_processo_individual",
            args=[processo_id],
            queue="monitoramento",
        )
    except Exception:
        pass


@router.post("", response_model=ProcessoResponse, status_code=status.HTTP_201_CREATED)
async def create_processo(
    payload: ProcessoCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> Processo:
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

    # Novo processo altera a distribuição de tipos_acao — invalida DNA do escritório
    redis = _get_redis(request)
    if redis:
        await invalidar_cache_dna_async(redis, escritorio_id)

    # Enriquece com DataJud diretamente (sem Celery) — garante tribunal/vara/comarca na resposta
    background_tasks.add_task(
        _enriquecer_processo_async, novo_processo.id, novo_processo.numero_cnj
    )
    # Dispara também via Celery para o ciclo de monitoramento periódico
    background_tasks.add_task(_disparar_monitoramento, novo_processo.id)

    return novo_processo


@router.get("/{processo_id}", response_model=ProcessoResponse)
async def get_processo(
    processo_id: int, request: Request, db: AsyncSession = Depends(get_db)
) -> Processo:
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
) -> Processo:
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

    # Dados do processo mudaram — invalida cache de capa e andamentos para este CNJ
    redis = _get_redis(request)
    if redis:
        await invalidar_caches_processo_async(redis, processo.numero_cnj)
        # tipo_acao alterado muda a distribuição usada pelo DNA do escritório
        if "tipo_acao" in update_data:
            await invalidar_cache_dna_async(redis, escritorio_id)

    return processo


@router.post("/{processo_id}/enriquecer", response_model=ProcessoResponse)
async def enriquecer_processo(
    processo_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> Processo:
    """
    Re-busca tribunal, vara, comarca e tipo_ação no DataJud para um processo já cadastrado.
    Útil para processos criados antes desta funcionalidade ou cujo enriquecimento falhou.
    """
    escritorio_id = _get_escritorio_id(request)

    processo = await db.get(Processo, processo_id)
    if not processo or processo.escritorio_id != escritorio_id:
        raise HTTPException(status_code=404, detail="Processo não encontrado ou sem permissão.")

    background_tasks.add_task(_enriquecer_processo_async, processo.id, processo.numero_cnj)
    return processo


@router.delete("/{processo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_processo(
    processo_id: int, request: Request, db: AsyncSession = Depends(get_db)
) -> None:
    """
    Soft delete: arquiva o processo e desativa o monitoramento.
    """
    escritorio_id = _get_escritorio_id(request)

    processo = await db.get(Processo, processo_id)
    if not processo or processo.escritorio_id != escritorio_id:
        raise HTTPException(status_code=404, detail="Processo não encontrado ou sem permissão.")

    registrar_acesso(_get_user_id(request), f"processo:{processo_id}", "exclusao", _get_ip(request))

    cnj = processo.numero_cnj
    processo.status = "arquivado"
    processo.monitoramento_ativo = False

    await db.flush()

    # Processo arquivado: invalida cache de dados judiciais e DNA do escritório
    redis = _get_redis(request)
    if redis:
        await invalidar_caches_processo_async(redis, cnj)
        await invalidar_cache_dna_async(redis, escritorio_id)

    return None
