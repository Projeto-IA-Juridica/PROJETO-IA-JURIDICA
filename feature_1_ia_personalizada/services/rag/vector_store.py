# feature_1_ia_personalizada/services/rag/vector_store.py
"""
VectorStore — interface de busca semântica sobre documentos_rag via pgvector.

Métodos públicos:
  buscar()           — busca por embedding pré-gerado (nível baixo)
  buscar_por_texto() — gera embedding da query e chama buscar() (com cache Redis)
  deletar_documento() — soft delete por doc_hash (ativo=False em todos os chunks)

Performance:
  - Índice HNSW criado na migration 007.
  - SET LOCAL hnsw.ef_search = 80 por sessão para recall máximo.
  - Cache Redis de busca: TTL 30 min, fire-and-forget (não bloqueia resposta).
  - pgvector serializa o vetor nativo — sem conversão manual para string.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from typing import Any

import structlog
from prometheus_client import Counter, Histogram
from redis.asyncio import Redis
from sqlalchemy import asc, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from feature_1_ia_personalizada.services.rag.embeddings import EmbeddingGenerator
from shared.models.documento_rag import DocumentoRag

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Métricas
# ---------------------------------------------------------------------------

_latencia_busca = Histogram(
    "rag_vector_search_seconds",
    "Latência da busca vetorial no pgvector",
)
_cache_hits = Counter(
    "rag_search_cache_hits_total",
    "Buscas textuais servidas do cache Redis",
)
_buscas_total = Counter(
    "rag_searches_total",
    "Total de buscas vetoriais realizadas",
    labelnames=["tipo"],  # "embedding" | "texto"
)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

_TTL_CACHE_BUSCA = 60 * 30  # 30 minutos
_HNSW_EF_SEARCH = 80        # recall alto; padrão pgvector é 40
_TOP_K_CANDIDATOS = 10       # candidatos retornados antes do re-ranking no RAGRetriever


# ---------------------------------------------------------------------------
# DTO de resultado
# ---------------------------------------------------------------------------


@dataclass
class ResultadoBusca:
    id: int
    escritorio_id: int
    titulo: str
    tipo: str
    conteudo: str
    chunk_index: int
    doc_hash: str | None
    metadata_json: dict[str, Any]
    distancia: float  # distância coseno: 0 = idêntico, 2 = oposto


# ---------------------------------------------------------------------------
# VectorStore
# ---------------------------------------------------------------------------


class VectorStore:
    """
    Realiza buscas semânticas na tabela documentos_rag usando pgvector.

    Instanciar uma vez e reutilizar.
    """

    def __init__(
        self,
        embedding_generator: EmbeddingGenerator,
        session_factory: async_sessionmaker[AsyncSession],
        redis_client: Redis,
    ) -> None:
        self._embeddings = embedding_generator
        self._session_factory = session_factory
        self._redis = redis_client

    # -----------------------------------------------------------------------
    # API pública
    # -----------------------------------------------------------------------

    async def buscar(
        self,
        query_embedding: list[float],
        escritorio_id: int,
        top_k: int = _TOP_K_CANDIDATOS,
        filtros: dict[str, Any] | None = None,
    ) -> list[ResultadoBusca]:
        """
        Busca os top_k chunks mais próximos do query_embedding.

        Usa a API ORM do SQLAlchemy + pgvector para serialização nativa do vetor
        (sem conversão manual para string) e sem risco de SQL injection.

        filtros opcionais:
          tipo      — str, ex: "sentenca"
          tribunal  — str, ex: "TJSP"  (JSONB metadata_json->>'tribunal')
          tipo_acao — str, ex: "Ação de Indenização"
        """
        _buscas_total.labels(tipo="embedding").inc()

        distancia = DocumentoRag.embedding.cosine_distance(query_embedding).label(
            "distancia"
        )

        stmt = (
            select(DocumentoRag, distancia)
            .where(
                DocumentoRag.escritorio_id == escritorio_id,
                DocumentoRag.ativo.is_(True),
            )
            .order_by(asc("distancia"))
            .limit(top_k)
        )

        # Filtros opcionais — adicionados via ORM (parametrizados, sem concatenação)
        if filtros:
            if "tipo" in filtros:
                stmt = stmt.where(DocumentoRag.tipo == filtros["tipo"])
            if "tribunal" in filtros:
                stmt = stmt.where(
                    DocumentoRag.metadata_json["tribunal"].astext == filtros["tribunal"]
                )
            if "tipo_acao" in filtros:
                stmt = stmt.where(
                    DocumentoRag.metadata_json["tipo_acao"].astext == filtros["tipo_acao"]
                )

        async with self._session_factory() as session:
            # Configura ef_search por sessão — SET LOCAL é seguro em transação async
            await session.execute(
                text(f"SET LOCAL hnsw.ef_search = {_HNSW_EF_SEARCH}")
            )

            with _latencia_busca.time():
                result = await session.execute(stmt)

            rows = result.all()

        return [
            ResultadoBusca(
                id=doc.id,
                escritorio_id=doc.escritorio_id,
                titulo=doc.titulo,
                tipo=doc.tipo,
                conteudo=doc.conteudo,
                chunk_index=doc.chunk_index,
                doc_hash=doc.doc_hash,
                metadata_json=dict(doc.metadata_json or {}),
                distancia=float(dist),
            )
            for doc, dist in rows
        ]

    async def buscar_por_texto(
        self,
        query_texto: str,
        escritorio_id: int,
        top_k: int = _TOP_K_CANDIDATOS,
        filtros: dict[str, Any] | None = None,
    ) -> list[ResultadoBusca]:
        """
        Gera embedding da query e busca no pgvector.
        Resultado cacheado no Redis por 30 minutos (gravação fire-and-forget).
        """
        _buscas_total.labels(tipo="texto").inc()

        cache_key = _search_cache_key(query_texto, escritorio_id, top_k, filtros)

        # Tenta cache
        cached = await self._get_cache(cache_key)
        if cached is not None:
            _cache_hits.inc()
            return cached

        # Gera embedding e busca
        query_embedding = await self._embeddings.gerar(query_texto)
        resultados = await self.buscar(query_embedding, escritorio_id, top_k, filtros)

        # Grava cache em background — não bloqueia a resposta ao cliente
        asyncio.create_task(self._set_cache(cache_key, resultados))

        return resultados

    async def deletar_documento(
        self, doc_hash: str, escritorio_id: int
    ) -> int:
        """
        Soft delete de todos os chunks de um documento pelo doc_hash.
        Retorna o número de chunks desativados.
        """
        async with self._session_factory() as session:
            stmt = (
                update(DocumentoRag)
                .where(
                    DocumentoRag.doc_hash == doc_hash,
                    DocumentoRag.escritorio_id == escritorio_id,
                    DocumentoRag.ativo.is_(True),
                )
                .values(ativo=False)
                .returning(DocumentoRag.id)
            )
            result = await session.execute(stmt)
            await session.commit()
            n = len(result.scalars().all())

        logger.info(
            "rag_documento_deletado",
            doc_hash=doc_hash[:16],
            escritorio_id=escritorio_id,
            chunks_desativados=n,
        )
        return n

    # -----------------------------------------------------------------------
    # Cache Redis
    # -----------------------------------------------------------------------

    async def _get_cache(self, key: str) -> list[ResultadoBusca] | None:
        try:
            raw = await self._redis.get(key)
            if raw:
                data: list[dict] = json.loads(raw)
                return [ResultadoBusca(**item) for item in data]
        except Exception as exc:
            logger.debug("rag_search_cache_read_erro", erro=str(exc))
        return None

    async def _set_cache(self, key: str, resultados: list[ResultadoBusca]) -> None:
        try:
            payload = json.dumps(
                [
                    {
                        "id": r.id,
                        "escritorio_id": r.escritorio_id,
                        "titulo": r.titulo,
                        "tipo": r.tipo,
                        "conteudo": r.conteudo,
                        "chunk_index": r.chunk_index,
                        "doc_hash": r.doc_hash,
                        "metadata_json": r.metadata_json,
                        "distancia": r.distancia,
                    }
                    for r in resultados
                ],
                ensure_ascii=False,
            )
            await self._redis.setex(key, _TTL_CACHE_BUSCA, payload)
        except Exception as exc:
            logger.debug("rag_search_cache_write_erro", erro=str(exc))


# ---------------------------------------------------------------------------
# Funções utilitárias
# ---------------------------------------------------------------------------


def _search_cache_key(
    query: str,
    escritorio_id: int,
    top_k: int,
    filtros: dict[str, Any] | None,
) -> str:
    digest = hashlib.sha256(query.encode()).hexdigest()[:24]
    filtros_str = json.dumps(filtros or {}, sort_keys=True)
    filtros_hash = hashlib.md5(filtros_str.encode(), usedforsecurity=False).hexdigest()[:8]
    return f"f1:rag:search:{digest}:{escritorio_id}:{top_k}:{filtros_hash}"
