# feature_1_ia_personalizada/services/rag/embeddings.py
"""
EmbeddingGenerator — geração de vetores semânticos para o RAG jurídico.

Provedor primário:  Voyage AI voyage-law-2  (1024D, especializado em jurídico)
Provedor fallback:  OpenAI text-embedding-3-small com dimensions=1024
  — ativado automaticamente quando VOYAGE_API_KEY está ausente ou na falha.

Clientes HTTP:
  - httpx.AsyncClient para Voyage AI (persistente, sem aiohttp)
  - openai.AsyncOpenAI para OpenAI (persistente)
  Ambos são instanciados uma vez no __init__ e reutilizados em todas as chamadas,
  evitando abertura/fechamento de conexões TCP por request.

Batch real:
  - gerar_batch() envia UM request com todos os textos — não N requests de 1 texto.
  - Ambas as APIs (Voyage e OpenAI) aceitam arrays. Isso reduz drasticamente
    o uso de Rate Limit e a latência total.

Cache Redis em batch:
  - mget para buscar todos os textos de uma vez.
  - pipeline para salvar todos os novos embeddings em uma transação.
  - TTL: 7 dias — mesmo chunk nunca gera embedding duas vezes.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, cast

import httpx
import structlog
from openai import AsyncOpenAI
from prometheus_client import Counter, Histogram
from redis.asyncio import Redis

from shared.config.settings import settings
from shared.models.documento_rag import EMBEDDING_DIM

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Métricas
# ---------------------------------------------------------------------------

_latencia = Histogram(
    "rag_embedding_seconds",
    "Latência de geração de embeddings (por chamada de batch)",
    labelnames=["provedor"],
)
_cache_hits = Counter(
    "rag_embedding_cache_hits_total",
    "Embeddings individuais servidos do cache Redis",
)
_erros = Counter(
    "rag_embedding_errors_total",
    "Erros na geração de embeddings",
    labelnames=["provedor"],
)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

_TTL_CACHE_EMBEDDING = 60 * 60 * 24 * 7  # 7 dias em segundos
_VOYAGE_URL = "https://api.voyageai.com/v1/embeddings"
_VOYAGE_MODEL = "voyage-law-2"
_OPENAI_MODEL = "text-embedding-3-small"


def _cache_key(texto: str) -> str:
    """Chave Redis baseada nos primeiros 32 hex do SHA256 do texto."""
    digest = hashlib.sha256(texto.encode()).hexdigest()[:32]
    return f"f1:rag:emb:{digest}"


# ---------------------------------------------------------------------------
# EmbeddingGenerator
# ---------------------------------------------------------------------------


class EmbeddingGenerator:
    """
    Gera embeddings vetoriais para ingestão e busca no RAG.

    Instanciar uma vez e reutilizar — os clientes HTTP são persistentes
    e mantêm connection pools internamente.
    """

    def __init__(self, redis_client: Redis) -> None:
        self._redis = redis_client
        self._voyage_key: str | None = getattr(settings, "VOYAGE_API_KEY", None)

        # Cliente httpx persistente para Voyage AI (connection pool automático)
        # Timeout conservador: embeddings são rápidos; 20s é mais que suficiente
        self._http = httpx.AsyncClient(timeout=20.0)

        # Cliente OpenAI persistente (usa httpx internamente)
        self._openai = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

        provedor = "voyage-law-2" if self._voyage_key else _OPENAI_MODEL
        logger.info("embedding_provedor_ativo", provedor=provedor)

    async def aclose(self) -> None:
        """Fecha os clientes HTTP persistentes. Chamar no shutdown da aplicação."""
        await self._http.aclose()
        await self._openai.close()

    # -----------------------------------------------------------------------
    # API pública
    # -----------------------------------------------------------------------

    async def gerar(self, texto: str) -> list[float]:
        """Atalho para um único texto — internamente usa gerar_batch."""
        resultados = await self.gerar_batch([texto])
        return resultados[0]

    async def gerar_batch(self, textos: list[str]) -> list[list[float]]:
        """
        Gera embeddings para uma lista de textos em UMA chamada de API.

        Fluxo:
          1. mget Redis — recupera todos os hits de cache de uma vez.
          2. Filtra misses — só os textos sem cache vão para a API.
          3. Uma chamada de API com todos os misses no payload.
          4. pipeline Redis — salva todos os novos embeddings em uma transação.
          5. Monta resultado final na ordem original de `textos`.
        """
        if not textos:
            return []

        chaves = [_cache_key(t) for t in textos]

        # 1. Busca em lote no cache
        cached_raw: list[Any] = await self._redis_mget(chaves)

        resultado: list[list[float] | None] = [None] * len(textos)
        indices_miss: list[int] = []

        for i, raw in enumerate(cached_raw):
            if raw is not None:
                resultado[i] = json.loads(raw)
                _cache_hits.inc()
            else:
                indices_miss.append(i)

        # 2. Nada para gerar — tudo veio do cache
        if not indices_miss:
            return resultado  # type: ignore[return-value]

        # 3. Uma única chamada de API com todos os textos em falta
        textos_miss = [textos[i] for i in indices_miss]
        vetores_novos = await self._gerar_provedor_batch(textos_miss)

        # 4. Salva novos embeddings no cache em lote (pipeline Redis)
        await self._redis_mset_batch(
            {chaves[indices_miss[j]]: vetores_novos[j] for j in range(len(indices_miss))}
        )

        # 5. Preenche resultado na ordem original
        for j, idx in enumerate(indices_miss):
            resultado[idx] = vetores_novos[j]

        return resultado  # type: ignore[return-value]

    # -----------------------------------------------------------------------
    # Internos — provedores
    # -----------------------------------------------------------------------

    async def _gerar_provedor_batch(self, textos: list[str]) -> list[list[float]]:
        """Tenta Voyage; faz fallback para OpenAI em caso de erro."""
        if self._voyage_key:
            try:
                return await self._voyage_batch(textos)
            except Exception as exc:
                _erros.labels(provedor="voyage").inc()
                logger.warning(
                    "embedding_voyage_falhou_fallback_openai",
                    erro=str(exc),
                    n_textos=len(textos),
                )

        return await self._openai_batch(textos)

    async def _voyage_batch(self, textos: list[str]) -> list[list[float]]:
        """Uma única requisição HTTP com todos os textos no payload."""
        payload = {"input": textos, "model": _VOYAGE_MODEL}
        headers = {
            "Authorization": f"Bearer {self._voyage_key}",
            "Content-Type": "application/json",
        }

        with _latencia.labels(provedor="voyage").time():
            resp = await self._http.post(_VOYAGE_URL, json=payload, headers=headers)
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()

        # Voyage retorna os itens já ordenados por índice
        vetores = [item["embedding"] for item in sorted(data["data"], key=lambda x: x["index"])]
        _validar_batch(vetores, "voyage", len(textos))
        return vetores

    async def _openai_batch(self, textos: list[str]) -> list[list[float]]:
        """Uma única chamada OpenAI com todos os textos e dimensions=1024."""
        with _latencia.labels(provedor="openai").time():
            resp = await self._openai.embeddings.create(
                model=_OPENAI_MODEL,
                input=textos,
                dimensions=EMBEDDING_DIM,
            )

        # OpenAI retorna ordenado por index
        vetores = [item.embedding for item in sorted(resp.data, key=lambda x: x.index)]
        _validar_batch(vetores, "openai", len(textos))
        return vetores

    # -----------------------------------------------------------------------
    # Internos — cache Redis
    # -----------------------------------------------------------------------

    async def _redis_mget(self, chaves: list[str]) -> list[Any]:
        try:
            return cast(list[Any], await self._redis.mget(*chaves))
        except Exception as exc:
            logger.debug("embedding_cache_mget_erro", erro=str(exc))
            return [None] * len(chaves)

    async def _redis_mset_batch(self, mapa: dict[str, list[float]]) -> None:
        """Salva múltiplos embeddings com setex em um pipeline Redis."""
        try:
            pipe = self._redis.pipeline()
            for chave, vetor in mapa.items():
                pipe.setex(chave, _TTL_CACHE_EMBEDDING, json.dumps(vetor))
            await pipe.execute()
        except Exception as exc:
            logger.debug("embedding_cache_mset_erro", erro=str(exc))


# ---------------------------------------------------------------------------
# Validação
# ---------------------------------------------------------------------------


def _validar_batch(vetores: list[list[float]], provedor: str, esperado: int) -> None:
    if len(vetores) != esperado:
        raise ValueError(
            f"Provedor '{provedor}' retornou {len(vetores)} embeddings, " f"esperado {esperado}."
        )
    for vetor in vetores:
        if len(vetor) != EMBEDDING_DIM:
            _erros.labels(provedor=provedor).inc()
            raise ValueError(
                f"Embedding do provedor '{provedor}' retornou {len(vetor)}D, "
                f"esperado {EMBEDDING_DIM}D."
            )
