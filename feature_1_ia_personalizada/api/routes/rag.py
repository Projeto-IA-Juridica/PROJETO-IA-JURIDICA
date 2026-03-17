# feature_1_ia_personalizada/api/routes/rag.py
"""
Rotas de gerenciamento do RAG Jurisprudencial por Escritório.

Endpoints:
  POST   /rag/upload                  — Upload de documento; dispara Celery task
  GET    /rag/status/{job_id}         — Status da ingestão
  GET    /rag/documentos              — Lista documentos do escritório (paginado)
  DELETE /rag/documentos/{doc_hash}   — Soft delete de documento
  POST   /rag/buscar                  — Busca semântica (debug/testes internos)

Segurança:
  Todos os endpoints exigem JWT válido (JWTAuthMiddleware).
  escritorio_id é sempre extraído do token — nunca confiado no payload do cliente.

Arquivo temporário (upload):
  O arquivo é salvo em /tmp e o caminho passado para a task Celery.
  A task é RESPONSÁVEL por deletar o arquivo ao final (sucesso ou erro).
  Isso evita leak de disco em Railway sem necessidade de S3 no MVP.
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from typing import Any

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile  # Request usado nas funções de dependência
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from feature_1_ia_personalizada.services.rag.embeddings import EmbeddingGenerator
from feature_1_ia_personalizada.services.rag.retriever import RAGRetriever
from feature_1_ia_personalizada.services.rag.vector_store import VectorStore
from shared.config.constants import RAG_ALLOWED_EXTENSIONS, RAG_MAX_FILE_SIZE_MB
from shared.database.session import get_db, get_session_factory
from shared.models.documento_rag import TIPOS_VALIDOS, DocumentoRag

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/rag", tags=["RAG Jurisprudencial"])

_JOB_KEY_PREFIX = "f1:rag:job:"
_JOB_TTL = 60 * 60 * 24  # 24 horas


# ---------------------------------------------------------------------------
# Dependências FastAPI
# ---------------------------------------------------------------------------


def get_redis(request: Request) -> Redis:
    return request.app.state.redis_client


def get_escritorio_id(request: Request) -> int:
    if not hasattr(request.state, "user_payload"):
        raise HTTPException(status_code=401, detail="Não autenticado")
    return int(request.state.user_payload.get("escritorio_id"))


def get_embedding_generator(redis: Redis = Depends(get_redis)) -> EmbeddingGenerator:
    return EmbeddingGenerator(redis_client=redis)


def get_vector_store(
    emb: EmbeddingGenerator = Depends(get_embedding_generator),
    redis: Redis = Depends(get_redis),
) -> VectorStore:
    return VectorStore(
        embedding_generator=emb,
        session_factory=get_session_factory(),
        redis_client=redis,
    )


def get_rag_retriever(store: VectorStore = Depends(get_vector_store)) -> RAGRetriever:
    return RAGRetriever(vector_store=store)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class BuscarRequest(BaseModel):
    query: str
    tipo: str | None = None
    tribunal: str | None = None


class DocumentoListItem(BaseModel):
    doc_hash: str
    titulo: str
    tipo: str
    chunks: int
    metadata_json: dict[str, Any]


class DocumentoListResponse(BaseModel):
    items: list[DocumentoListItem]
    total: int
    page: int
    per_page: int


# ---------------------------------------------------------------------------
# POST /rag/upload
# ---------------------------------------------------------------------------


@router.post("/upload", status_code=202)
async def upload_documento(
    file: UploadFile = File(...),
    titulo: str = Query(..., min_length=3, max_length=500),
    tipo: str = Query(..., description=f"Um de: {', '.join(sorted(TIPOS_VALIDOS))}"),
    escritorio_id: int = Depends(get_escritorio_id),
    redis: Redis = Depends(get_redis),
):
    """
    Faz upload de um documento jurídico e dispara ingestão assíncrona via Celery.
    Retorna imediatamente com um `job_id` para acompanhar o status.
    """
    if tipo not in TIPOS_VALIDOS:
        raise HTTPException(
            status_code=422,
            detail=f"Tipo inválido '{tipo}'. Use: {', '.join(sorted(TIPOS_VALIDOS))}",
        )

    nome = file.filename or ""
    extensao = os.path.splitext(nome)[1].lower().lstrip(".")
    if extensao not in RAG_ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Extensão '.{extensao}' não permitida. Use: {', '.join(RAG_ALLOWED_EXTENSIONS)}",
        )

    conteudo = await file.read()
    tamanho_mb = len(conteudo) / (1024 * 1024)
    if tamanho_mb > RAG_MAX_FILE_SIZE_MB:
        raise HTTPException(
            status_code=413,
            detail=f"Arquivo muito grande ({tamanho_mb:.1f} MB). Máximo: {RAG_MAX_FILE_SIZE_MB} MB.",
        )

    # Salva em /tmp — a task Celery deleta ao final (sucesso ou erro)
    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{extensao}") as tmp:
        tmp.write(conteudo)
        tmp_path = tmp.name

    job_id = str(uuid.uuid4())
    job_data = {
        "status": "pendente",
        "escritorio_id": escritorio_id,
        "titulo": titulo,
        "tipo": tipo,
        "arquivo": nome,
        "chunks": 0,
        "erro": None,
    }
    await redis.setex(f"{_JOB_KEY_PREFIX}{job_id}", _JOB_TTL, json.dumps(job_data))

    from feature_1_ia_personalizada.workers.ingest_documentos import ingest_documento

    ingest_documento.apply_async(
        kwargs={
            "arquivo_path": tmp_path,
            "escritorio_id": escritorio_id,
            "titulo": titulo,
            "tipo": tipo,
            "job_id": job_id,
        },
        queue="ia",
    )

    logger.info(
        "rag_upload_recebido",
        escritorio_id=escritorio_id,
        titulo=titulo,
        tipo=tipo,
        tamanho_mb=round(tamanho_mb, 2),
        job_id=job_id,
    )
    return {"job_id": job_id, "status": "pendente"}


# ---------------------------------------------------------------------------
# GET /rag/status/{job_id}
# ---------------------------------------------------------------------------


@router.get("/status/{job_id}")
async def status_ingestao(
    job_id: str,
    escritorio_id: int = Depends(get_escritorio_id),
    redis: Redis = Depends(get_redis),
):
    """Retorna o status atual de um job de ingestão."""
    raw = await redis.get(f"{_JOB_KEY_PREFIX}{job_id}")
    if not raw:
        raise HTTPException(status_code=404, detail="Job não encontrado ou expirado.")

    dados: dict[str, Any] = json.loads(raw)
    if dados.get("escritorio_id") != escritorio_id:
        raise HTTPException(status_code=404, detail="Job não encontrado.")

    return dados


# ---------------------------------------------------------------------------
# GET /rag/documentos
# ---------------------------------------------------------------------------


@router.get("/documentos", response_model=DocumentoListResponse)
async def listar_documentos(
    db: AsyncSession = Depends(get_db),
    escritorio_id: int = Depends(get_escritorio_id),
    tipo: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    """Lista os documentos ingeridos pelo escritório, agrupados por doc_hash."""
    if tipo and tipo not in TIPOS_VALIDOS:
        raise HTTPException(status_code=422, detail=f"Tipo inválido: {tipo}")

    # Filtro base reutilizado nas duas queries
    filtro_base = [
        DocumentoRag.escritorio_id == escritorio_id,
        DocumentoRag.ativo.is_(True),
    ]
    if tipo:
        filtro_base.append(DocumentoRag.tipo == tipo)

    # COUNT separado e direto — sem subquery aninhada
    total = (
        await db.execute(
            select(func.count(func.distinct(DocumentoRag.doc_hash))).where(*filtro_base)
        )
    ).scalar() or 0

    # Página atual
    offset = (page - 1) * per_page
    rows = (
        await db.execute(
            select(
                DocumentoRag.doc_hash,
                DocumentoRag.titulo,
                DocumentoRag.tipo,
                DocumentoRag.metadata_json,
                func.count(DocumentoRag.id).label("chunks"),
            )
            .where(*filtro_base)
            .group_by(
                DocumentoRag.doc_hash,
                DocumentoRag.titulo,
                DocumentoRag.tipo,
                DocumentoRag.metadata_json,
            )
            .order_by(DocumentoRag.titulo)
            .offset(offset)
            .limit(per_page)
        )
    ).all()

    return DocumentoListResponse(
        items=[
            DocumentoListItem(
                doc_hash=row.doc_hash or "",
                titulo=row.titulo,
                tipo=row.tipo,
                chunks=row.chunks,
                metadata_json=dict(row.metadata_json or {}),
            )
            for row in rows
        ],
        total=total,
        page=page,
        per_page=per_page,
    )


# ---------------------------------------------------------------------------
# DELETE /rag/documentos/{doc_hash}
# ---------------------------------------------------------------------------


@router.delete("/documentos/{doc_hash}")
async def deletar_documento(
    doc_hash: str,
    db: AsyncSession = Depends(get_db),
    escritorio_id: int = Depends(get_escritorio_id),
    store: VectorStore = Depends(get_vector_store),
):
    """Soft delete de todos os chunks de um documento pelo doc_hash."""
    existe = (
        await db.execute(
            select(DocumentoRag.id)
            .where(
                DocumentoRag.doc_hash == doc_hash,
                DocumentoRag.escritorio_id == escritorio_id,
                DocumentoRag.ativo.is_(True),
            )
            .limit(1)
        )
    ).scalar()

    if not existe:
        raise HTTPException(
            status_code=404, detail="Documento não encontrado ou já removido."
        )

    n = await store.deletar_documento(doc_hash=doc_hash, escritorio_id=escritorio_id)
    return {"doc_hash": doc_hash, "chunks_removidos": n}


# ---------------------------------------------------------------------------
# POST /rag/buscar  (debug/interno)
# ---------------------------------------------------------------------------


@router.post("/buscar")
async def buscar_semantico(
    body: BuscarRequest,
    escritorio_id: int = Depends(get_escritorio_id),
    retriever: RAGRetriever = Depends(get_rag_retriever),
):
    """Busca semântica direta — para testes e debug internos."""
    filtros: dict[str, Any] | None = None
    if body.tipo or body.tribunal:
        filtros = {}
        if body.tipo:
            filtros["tipo"] = body.tipo
        if body.tribunal:
            filtros["tribunal"] = body.tribunal

    contexto = await retriever.buscar(
        query=body.query,
        escritorio_id=escritorio_id,
        contexto_processo=filtros,
    )
    return {
        "query": body.query,
        "contexto": contexto or "(nenhum resultado acima do threshold)",
    }
