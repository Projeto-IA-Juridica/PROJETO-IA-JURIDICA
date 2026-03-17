# feature_1_ia_personalizada/tests/unit/test_embeddings.py
"""
Testes unitários do EmbeddingGenerator.

Cobre:
  - Cache hit: API não é chamada quando embedding está no Redis
  - Cache miss: API é chamada e resultado é cacheado
  - Fallback Voyage → OpenAI em caso de erro
  - gerar_batch retorna vetores na ordem correta
  - Validação de dimensão estoura erro para dim errada
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from feature_1_ia_personalizada.services.rag.embeddings import (
    EmbeddingGenerator,
    _validar_batch,
)
from shared.models.documento_rag import EMBEDDING_DIM

# ---------------------------------------------------------------------------
# Fake Redis para testes
# ---------------------------------------------------------------------------


class _FakeRedis:
    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self._store[key] = value

    async def mget(self, *keys: str) -> list[str | None]:
        return [self._store.get(k) for k in keys]

    def pipeline(self):
        return _FakePipeline(self)


class _FakePipeline:
    def __init__(self, redis: _FakeRedis) -> None:
        self._redis = redis
        self._ops: list[tuple] = []

    def setex(self, key: str, ttl: int, value: str) -> "_FakePipeline":
        self._ops.append((key, ttl, value))
        return self

    async def execute(self) -> None:
        for key, ttl, value in self._ops:
            self._redis._store[key] = value


def _vetor_fake(dim: int = EMBEDDING_DIM) -> list[float]:
    return [0.1] * dim


# ---------------------------------------------------------------------------
# Testes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_hit_nao_chama_api():
    """Quando o embedding está no cache, a API não deve ser chamada."""
    redis = _FakeRedis()
    gen = EmbeddingGenerator(redis_client=redis)

    vetor = _vetor_fake()
    texto = "prazo recursal"

    # Pré-popula cache manualmente
    from feature_1_ia_personalizada.services.rag.embeddings import _cache_key
    redis._store[_cache_key(texto)] = json.dumps(vetor)

    with patch.object(gen, "_gerar_provedor_batch", new_callable=AsyncMock) as mock_api:
        resultado = await gen.gerar(texto)

    mock_api.assert_not_called()
    assert resultado == vetor


@pytest.mark.asyncio
async def test_cache_miss_chama_api_e_cacheia():
    """Quando não há cache, a API é chamada e o resultado é salvo."""
    redis = _FakeRedis()
    gen = EmbeddingGenerator(redis_client=redis)
    vetor_esperado = _vetor_fake()

    with patch.object(
        gen, "_gerar_provedor_batch", new_callable=AsyncMock, return_value=[vetor_esperado]
    ):
        resultado = await gen.gerar("audiência de instrução")

    assert resultado == vetor_esperado

    # Verifica que foi cacheado
    from feature_1_ia_personalizada.services.rag.embeddings import _cache_key
    cached_raw = redis._store.get(_cache_key("audiência de instrução"))
    assert cached_raw is not None
    assert json.loads(cached_raw) == vetor_esperado


@pytest.mark.asyncio
async def test_fallback_voyage_para_openai():
    """Quando Voyage falha, o gerador usa OpenAI automaticamente."""
    redis = _FakeRedis()
    gen = EmbeddingGenerator(redis_client=redis)
    gen._voyage_key = "fake-voyage-key"

    vetor_openai = _vetor_fake()

    with patch.object(gen, "_voyage_batch", new_callable=AsyncMock, side_effect=Exception("timeout")):
        with patch.object(
            gen, "_openai_batch", new_callable=AsyncMock, return_value=[vetor_openai]
        ):
            resultado = await gen.gerar("recurso de apelação")

    assert resultado == vetor_openai


@pytest.mark.asyncio
async def test_gerar_batch_preserva_ordem():
    """gerar_batch deve retornar vetores na mesma ordem dos textos de entrada."""
    redis = _FakeRedis()
    gen = EmbeddingGenerator(redis_client=redis)

    textos = ["texto A", "texto B", "texto C"]
    vetores = [[float(i)] * EMBEDDING_DIM for i in range(len(textos))]

    with patch.object(
        gen, "_gerar_provedor_batch", new_callable=AsyncMock, return_value=vetores
    ):
        resultado = await gen.gerar_batch(textos)

    assert len(resultado) == 3
    assert resultado[0][0] == 0.0
    assert resultado[1][0] == 1.0
    assert resultado[2][0] == 2.0


def test_validar_batch_dim_errada_levanta_erro():
    """Vetor com dimensão errada deve levantar ValueError."""
    vetor_errado = [0.1] * 512  # deveria ser EMBEDDING_DIM (1024)
    with pytest.raises(ValueError, match="1024D"):
        _validar_batch([vetor_errado], "openai", 1)


def test_validar_batch_quantidade_errada_levanta_erro():
    """Número de vetores diferente do esperado deve levantar ValueError."""
    vetores = [_vetor_fake(), _vetor_fake()]
    with pytest.raises(ValueError, match="esperado 3"):
        _validar_batch(vetores, "voyage", 3)
