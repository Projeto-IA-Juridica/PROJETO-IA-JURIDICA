# feature_1_ia_personalizada/tests/unit/test_cache_manager.py
"""
Testes do LegalDataCacheManager: hit/miss, TTL, formato de chaves,
isolamento por CNJ, invalidação e resiliência (graceful degradation).

Também cobre os helpers síncronos (get/set_andamentos_sync, get/set_capa_sync)
usados pelos workers Celery, mockando _sync_redis com MagicMock síncrono.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from feature_1_ia_personalizada.services.legal_data.cache_manager import (
    LegalDataCacheManager,
    get_andamentos_sync,
    get_capa_sync,
    set_andamentos_sync,
    set_capa_sync,
)


# ---------------------------------------------------------------------------
# Fake Redis — suporte a get/setex/pipeline(delete)
# ---------------------------------------------------------------------------

class _FakeCacheRedis:
    """
    Simula redis.asyncio.Redis para os métodos usados pelo CacheManager.

    ATENÇÃO: `get` retorna `str` em vez de `bytes` como o Redis real faz.
    `json.loads` aceita ambos, então os testes passam — mas código futuro que
    chame `.decode()` ou compare bytes em `cached_data` antes do `json.loads`
    passará aqui e quebrará em produção. Manter essa classe simples é intencional;
    ajustar para retornar `bytes` se o cache_manager evoluir nessa direção.
    """

    def __init__(self) -> None:
        self._store: dict[str, str] = {}
        self._ttls: dict[str, int] = {}

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def setex(self, key: str, seconds: int, value: str) -> None:
        self._store[key] = value
        self._ttls[key] = seconds

    def pipeline(self) -> "_FakeCachePipeline":
        return _FakeCachePipeline(self)

    # Helpers de inspeção para os testes
    def _ttl(self, key: str) -> int | None:
        return self._ttls.get(key)

    def _exists(self, key: str) -> bool:
        return key in self._store


class _FakeCachePipeline:
    def __init__(self, redis: _FakeCacheRedis) -> None:
        self._redis = redis
        self._cmds: list = []

    def delete(self, key: str) -> "_FakeCachePipeline":
        self._cmds.append(("delete", key))
        return self

    async def execute(self) -> list:
        results = []
        for cmd in self._cmds:
            if cmd[0] == "delete":
                key = cmd[1]
                existed = key in self._redis._store
                self._redis._store.pop(key, None)
                self._redis._ttls.pop(key, None)
                results.append(1 if existed else 0)
        self._cmds.clear()
        return results


class _ErrorRedis(_FakeCacheRedis):
    """Simula Redis com falha em todas as operações — testa graceful degradation."""

    async def get(self, key: str) -> str | None:  # type: ignore[override]
        raise ConnectionError("Redis indisponível")

    async def setex(self, key: str, seconds: int, value: str) -> None:  # type: ignore[override]
        raise ConnectionError("Redis indisponível")

    def pipeline(self) -> "_ErrorPipeline":  # type: ignore[override]
        return _ErrorPipeline()


class _ErrorPipeline:
    def delete(self, key: str) -> "_ErrorPipeline":
        return self

    async def execute(self) -> list:
        raise ConnectionError("Redis indisponível")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def redis() -> _FakeCacheRedis:
    return _FakeCacheRedis()


@pytest.fixture
def cache(redis: _FakeCacheRedis) -> LegalDataCacheManager:
    return LegalDataCacheManager(redis)


@pytest.fixture
def cache_error() -> LegalDataCacheManager:
    return LegalDataCacheManager(_ErrorRedis())


# ---------------------------------------------------------------------------
# Dados de teste
# ---------------------------------------------------------------------------

CNJ = "0001234-12.2023.8.26.0100"
CNJ_2 = "0009999-99.2024.8.26.0050"

CAPA = {
    "numero_processo": CNJ,
    "classe": "Execução Fiscal",
    "assunto": "IPTU",
    "tribunal": "TJSP",
    "comarca": "São Paulo",
}

ANDAMENTOS = [
    {"data": "2024-01-15", "descricao": "Despacho ordinatório"},
    {"data": "2024-01-20", "descricao": "Intimação da parte — réu notificado"},
]


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

class TestConstantes:
    def test_ttl_capa_e_24_horas(self):
        assert LegalDataCacheManager.TTL_CAPA_PROCESSO == 60 * 60 * 24

    def test_ttl_andamentos_e_6_horas(self):
        assert LegalDataCacheManager.TTL_ANDAMENTOS == 60 * 60 * 6


# ---------------------------------------------------------------------------
# Happy path — Capa
# ---------------------------------------------------------------------------

class TestCapa:
    async def test_miss_antes_de_salvar_retorna_none(self, cache: LegalDataCacheManager):
        assert await cache.get_capa(CNJ) is None

    async def test_set_get_round_trip(self, cache: LegalDataCacheManager):
        await cache.set_capa(CNJ, CAPA)
        assert await cache.get_capa(CNJ) == CAPA

    async def test_ttl_correto_apos_set(self, cache: LegalDataCacheManager, redis: _FakeCacheRedis):
        await cache.set_capa(CNJ, CAPA)
        chave = LegalDataCacheManager._key_capa(CNJ)
        assert redis._ttl(chave) == LegalDataCacheManager.TTL_CAPA_PROCESSO

    async def test_unicode_preservado(self, cache: LegalDataCacheManager):
        capa_unicode = {**CAPA, "assunto": "Execução — débito tributário (Art. 5º, § 3°)"}
        await cache.set_capa(CNJ, capa_unicode)
        assert (await cache.get_capa(CNJ))["assunto"] == capa_unicode["assunto"]

    async def test_sobrescrever_atualiza_valor(self, cache: LegalDataCacheManager):
        await cache.set_capa(CNJ, CAPA)
        capa_nova = {**CAPA, "classe": "Ação Ordinária"}
        await cache.set_capa(CNJ, capa_nova)
        assert (await cache.get_capa(CNJ))["classe"] == "Ação Ordinária"


# ---------------------------------------------------------------------------
# Happy path — Andamentos
# ---------------------------------------------------------------------------

class TestAndamentos:
    async def test_miss_antes_de_salvar_retorna_none(self, cache: LegalDataCacheManager):
        assert await cache.get_andamentos(CNJ) is None

    async def test_set_get_round_trip(self, cache: LegalDataCacheManager):
        await cache.set_andamentos(CNJ, ANDAMENTOS)
        assert await cache.get_andamentos(CNJ) == ANDAMENTOS

    async def test_ttl_correto_apos_set(self, cache: LegalDataCacheManager, redis: _FakeCacheRedis):
        await cache.set_andamentos(CNJ, ANDAMENTOS)
        chave = LegalDataCacheManager._key_andamentos(CNJ)
        assert redis._ttl(chave) == LegalDataCacheManager.TTL_ANDAMENTOS

    async def test_lista_vazia_salva_e_recupera(self, cache: LegalDataCacheManager):
        await cache.set_andamentos(CNJ, [])
        assert await cache.get_andamentos(CNJ) == []

    async def test_ordem_preservada(self, cache: LegalDataCacheManager):
        await cache.set_andamentos(CNJ, ANDAMENTOS)
        resultado = await cache.get_andamentos(CNJ)
        assert resultado[0]["data"] == "2024-01-15"
        assert resultado[1]["data"] == "2024-01-20"


# ---------------------------------------------------------------------------
# Formato e isolamento de chaves
# ---------------------------------------------------------------------------

class TestChaves:
    def test_formato_chave_capa(self):
        assert LegalDataCacheManager._key_capa(CNJ) == f"f1:legal_data:capa:{CNJ}"

    def test_formato_chave_andamentos(self):
        assert LegalDataCacheManager._key_andamentos(CNJ) == f"f1:legal_data:andamentos:{CNJ}"

    def test_capa_e_andamentos_chaves_distintas(self):
        assert LegalDataCacheManager._key_capa(CNJ) != LegalDataCacheManager._key_andamentos(CNJ)

    async def test_cnjs_distintos_nao_se_misturam_capa(self, cache: LegalDataCacheManager):
        await cache.set_capa(CNJ, {**CAPA, "comarca": "São Paulo"})
        await cache.set_capa(CNJ_2, {**CAPA, "comarca": "Campinas"})
        assert (await cache.get_capa(CNJ))["comarca"] == "São Paulo"
        assert (await cache.get_capa(CNJ_2))["comarca"] == "Campinas"

    async def test_cnjs_distintos_nao_se_misturam_andamentos(self, cache: LegalDataCacheManager):
        await cache.set_andamentos(CNJ, ANDAMENTOS)
        await cache.set_andamentos(CNJ_2, [])
        assert await cache.get_andamentos(CNJ) == ANDAMENTOS
        assert await cache.get_andamentos(CNJ_2) == []


# ---------------------------------------------------------------------------
# Invalidação
# ---------------------------------------------------------------------------

class TestInvalidacao:
    async def test_invalida_capa_e_andamentos_do_cnj(
        self, cache: LegalDataCacheManager, redis: _FakeCacheRedis
    ):
        await cache.set_capa(CNJ, CAPA)
        await cache.set_andamentos(CNJ, ANDAMENTOS)

        await cache.invalidar_cache_processo(CNJ)

        assert not redis._exists(LegalDataCacheManager._key_capa(CNJ))
        assert not redis._exists(LegalDataCacheManager._key_andamentos(CNJ))

    async def test_apos_invalidar_get_retorna_none(self, cache: LegalDataCacheManager):
        await cache.set_capa(CNJ, CAPA)
        await cache.set_andamentos(CNJ, ANDAMENTOS)

        await cache.invalidar_cache_processo(CNJ)

        assert await cache.get_capa(CNJ) is None
        assert await cache.get_andamentos(CNJ) is None

    async def test_invalida_cnj_sem_cache_nao_crasha(self, cache: LegalDataCacheManager):
        """Invalidar chave inexistente não levanta exceção."""
        await cache.invalidar_cache_processo("0000000-00.0000.0.00.0000")

    async def test_invalida_nao_afeta_outro_cnj(
        self, cache: LegalDataCacheManager, redis: _FakeCacheRedis
    ):
        await cache.set_capa(CNJ, CAPA)
        await cache.set_capa(CNJ_2, {**CAPA, "comarca": "Campinas"})

        await cache.invalidar_cache_processo(CNJ)

        assert not redis._exists(LegalDataCacheManager._key_capa(CNJ))
        assert redis._exists(LegalDataCacheManager._key_capa(CNJ_2))


# ---------------------------------------------------------------------------
# Resiliência — graceful degradation quando Redis falha
# ---------------------------------------------------------------------------

class TestResiliencia:
    async def test_get_capa_redis_error_retorna_none(self, cache_error: LegalDataCacheManager):
        assert await cache_error.get_capa(CNJ) is None

    async def test_set_capa_redis_error_nao_crasha(self, cache_error: LegalDataCacheManager):
        await cache_error.set_capa(CNJ, CAPA)

    async def test_get_andamentos_redis_error_retorna_none(self, cache_error: LegalDataCacheManager):
        assert await cache_error.get_andamentos(CNJ) is None

    async def test_set_andamentos_redis_error_nao_crasha(self, cache_error: LegalDataCacheManager):
        await cache_error.set_andamentos(CNJ, ANDAMENTOS)

    async def test_invalidar_redis_error_nao_crasha(self, cache_error: LegalDataCacheManager):
        await cache_error.invalidar_cache_processo(CNJ)


# ---------------------------------------------------------------------------
# Helpers síncronos — get/set_andamentos_sync, get/set_capa_sync
# ---------------------------------------------------------------------------
# Usam patch("...cache_manager._sync_redis") com MagicMock síncrono para
# isolar dos testes do Redis real. Os helpers são chamados por workers Celery.
# ---------------------------------------------------------------------------

_CACHE_MODULE = "feature_1_ia_personalizada.services.legal_data.cache_manager"


class TestHelpersSincronos:
    # -----------------------------------------------------------------------
    # get_andamentos_sync
    # -----------------------------------------------------------------------

    def test_get_andamentos_sync_hit(self):
        """Quando Redis tem os dados, retorna a lista deserializada."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = json.dumps(ANDAMENTOS)
        with patch(f"{_CACHE_MODULE}._sync_redis", mock_redis):
            result = get_andamentos_sync(CNJ)
        assert result == ANDAMENTOS
        mock_redis.get.assert_called_once_with(LegalDataCacheManager._key_andamentos(CNJ))

    def test_get_andamentos_sync_miss(self):
        """Quando Redis não tem os dados, retorna None."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        with patch(f"{_CACHE_MODULE}._sync_redis", mock_redis):
            result = get_andamentos_sync(CNJ)
        assert result is None

    def test_get_andamentos_sync_redis_error_retorna_none(self):
        """Erro no Redis retorna None (graceful degradation)."""
        mock_redis = MagicMock()
        mock_redis.get.side_effect = ConnectionError("Redis indisponível")
        with patch(f"{_CACHE_MODULE}._sync_redis", mock_redis):
            result = get_andamentos_sync(CNJ)
        assert result is None

    def test_get_andamentos_sync_hit_lista_vazia(self):
        """Lista vazia no cache é um hit válido — retorna [] em vez de None."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = json.dumps([])
        with patch(f"{_CACHE_MODULE}._sync_redis", mock_redis):
            result = get_andamentos_sync(CNJ)
        assert result == []

    # -----------------------------------------------------------------------
    # set_andamentos_sync
    # -----------------------------------------------------------------------

    def test_set_andamentos_sync_chama_setex_com_ttl_correto(self):
        """Persiste no Redis com TTL_ANDAMENTOS (6h) e chave correta."""
        mock_redis = MagicMock()
        with patch(f"{_CACHE_MODULE}._sync_redis", mock_redis):
            set_andamentos_sync(CNJ, ANDAMENTOS)
        mock_redis.setex.assert_called_once_with(
            LegalDataCacheManager._key_andamentos(CNJ),
            LegalDataCacheManager.TTL_ANDAMENTOS,
            json.dumps(ANDAMENTOS, ensure_ascii=False),
        )

    def test_set_andamentos_sync_lista_vazia(self):
        """Lista vazia é persitida normalmente."""
        mock_redis = MagicMock()
        with patch(f"{_CACHE_MODULE}._sync_redis", mock_redis):
            set_andamentos_sync(CNJ, [])
        mock_redis.setex.assert_called_once()

    def test_set_andamentos_sync_redis_error_nao_crasha(self):
        """Erro no Redis não propaga exceção (graceful degradation)."""
        mock_redis = MagicMock()
        mock_redis.setex.side_effect = ConnectionError("Redis indisponível")
        with patch(f"{_CACHE_MODULE}._sync_redis", mock_redis):
            set_andamentos_sync(CNJ, ANDAMENTOS)  # Não deve lançar exceção

    # -----------------------------------------------------------------------
    # get_capa_sync
    # -----------------------------------------------------------------------

    def test_get_capa_sync_hit(self):
        """Quando Redis tem os dados, retorna o dict deserializado."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = json.dumps(CAPA)
        with patch(f"{_CACHE_MODULE}._sync_redis", mock_redis):
            result = get_capa_sync(CNJ)
        assert result == CAPA
        mock_redis.get.assert_called_once_with(LegalDataCacheManager._key_capa(CNJ))

    def test_get_capa_sync_miss(self):
        """Quando Redis não tem os dados, retorna None."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        with patch(f"{_CACHE_MODULE}._sync_redis", mock_redis):
            result = get_capa_sync(CNJ)
        assert result is None

    def test_get_capa_sync_redis_error_retorna_none(self):
        """Erro no Redis retorna None (graceful degradation)."""
        mock_redis = MagicMock()
        mock_redis.get.side_effect = ConnectionError("Redis indisponível")
        with patch(f"{_CACHE_MODULE}._sync_redis", mock_redis):
            result = get_capa_sync(CNJ)
        assert result is None

    # -----------------------------------------------------------------------
    # set_capa_sync
    # -----------------------------------------------------------------------

    def test_set_capa_sync_chama_setex_com_ttl_correto(self):
        """Persiste no Redis com TTL_CAPA_PROCESSO (24h) e chave correta."""
        mock_redis = MagicMock()
        with patch(f"{_CACHE_MODULE}._sync_redis", mock_redis):
            set_capa_sync(CNJ, CAPA)
        mock_redis.setex.assert_called_once_with(
            LegalDataCacheManager._key_capa(CNJ),
            LegalDataCacheManager.TTL_CAPA_PROCESSO,
            json.dumps(CAPA, ensure_ascii=False),
        )

    def test_set_capa_sync_redis_error_nao_crasha(self):
        """Erro no Redis não propaga exceção (graceful degradation)."""
        mock_redis = MagicMock()
        mock_redis.setex.side_effect = ConnectionError("Redis indisponível")
        with patch(f"{_CACHE_MODULE}._sync_redis", mock_redis):
            set_capa_sync(CNJ, CAPA)  # Não deve lançar exceção

    # -----------------------------------------------------------------------
    # Consistência de chaves entre sync e async
    # -----------------------------------------------------------------------

    def test_chaves_sync_e_async_sao_identicas(self):
        """As funções sync usam as mesmas chaves que LegalDataCacheManager async."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        with patch(f"{_CACHE_MODULE}._sync_redis", mock_redis):
            get_andamentos_sync(CNJ)
            get_capa_sync(CNJ)

        calls = [call.args[0] for call in mock_redis.get.call_args_list]
        assert LegalDataCacheManager._key_andamentos(CNJ) in calls
        assert LegalDataCacheManager._key_capa(CNJ) in calls
