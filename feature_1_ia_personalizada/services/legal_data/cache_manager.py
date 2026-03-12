"""
feature_1_ia_personalizada/services/legal_data/cache_manager.py

Módulo responsável por gerenciar políticas de Cache (Tempo de Vida da Memória)
das chamadas demoradas de Tribunais e APIs pagas (Jusbrasil / Datajud).

A principal vantagem usar o Upstash Redis aqui é reduzir o consumo de APIs (Custo USD)
e diminuir a latência gigantesca quando advogados buscam o mesmo processo no
mesmo dia recorrentemente.

Dois contextos de uso:
  - Async (FastAPI / Orchestrator): classe LegalDataCacheManager com redis.asyncio.Redis
  - Sync  (Celery workers):         funções de módulo get/set_*_sync com redis.Redis
    As funções sync reutilizam as chaves e TTLs da classe para consistência.
"""

import json
from datetime import timedelta
from typing import Any

import redis as _redis_sync_mod
import structlog
from redis.asyncio import Redis

from shared.config.settings import settings

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Conexão sync (Redis bloqueante) — usada pelos helpers de workers Celery
# ---------------------------------------------------------------------------
# Criada uma vez no import do módulo, compartilhada entre chamadas.
# socket_connect_timeout=2 garante falha rápida em caso de Redis indisponível
# (graceful degradation — o worker continua sem cache).
_sync_redis: _redis_sync_mod.Redis = _redis_sync_mod.from_url(
    settings.REDIS_URL,
    decode_responses=True,
    socket_connect_timeout=2,
    socket_timeout=2,
)


class LegalDataCacheManager:
    """Gerencia caching para as consultas de processos e andamentos judiciais."""

    # Configuração de Tempos (TTL - Time to Live)
    TTL_CAPA_PROCESSO = int(timedelta(hours=24).total_seconds())  # Capa muda muito pouco, 24 horas.
    TTL_ANDAMENTOS = int(
        timedelta(hours=6).total_seconds()
    )  # Andamentos mudam mais em dias úteis, 6 horas.

    def __init__(self, redis_client: Redis):
        """
        Recebe a instância injetada do redis.asyncio.Redis
        """
        self._redis = redis_client
        logger.info("cache_manager_iniciado", ttl_andamentos_horas=self.TTL_ANDAMENTOS / 3600)

    @staticmethod
    def _key_capa(cnj: str) -> str:
        return f"f1:legal_data:capa:{cnj}"

    @staticmethod
    def _key_andamentos(cnj: str) -> str:
        return f"f1:legal_data:andamentos:{cnj}"

    async def get_capa(self, cnj: str) -> dict[str, Any] | None:
        """Busca do Redis a Capa do processo, se existir dentro do TTL."""
        try:
            cached_data = await self._redis.get(self._key_capa(cnj))
            if cached_data:
                logger.debug("cache_capa_hit", cnj=cnj)
                return json.loads(cached_data)  # type: ignore[no-any-return]

            logger.debug("cache_capa_miss", cnj=cnj)
            return None
        except Exception as e:
            # Em caso de falha no Redis, avisamos o Log mas não quebramos a aplicação (Graceful Degradation)
            logger.error("cache_read_error", error=str(e), key=self._key_capa(cnj))
            return None

    async def set_capa(self, cnj: str, capa_data: dict[str, Any]) -> None:
        """Salva a Capa no Redis pelo TTL designado."""
        try:
            payload = json.dumps(capa_data, ensure_ascii=False)
            await self._redis.setex(self._key_capa(cnj), self.TTL_CAPA_PROCESSO, payload)
            logger.debug("cache_capa_salva", cnj=cnj)
        except Exception as e:
            logger.error("cache_write_error", error=str(e), key=self._key_capa(cnj))

    async def get_andamentos(self, cnj: str) -> list[dict[str, Any]] | None:
        """Busca do Redis a Timeline de Andamentos, se existir dentro do TTL."""
        try:
            cached_data = await self._redis.get(self._key_andamentos(cnj))
            if cached_data:
                logger.debug("cache_andamentos_hit", cnj=cnj)
                return json.loads(cached_data)  # type: ignore[no-any-return]

            logger.debug("cache_andamentos_miss", cnj=cnj)
            return None
        except Exception as e:
            logger.error("cache_read_error", error=str(e), key=self._key_andamentos(cnj))
            return None

    async def set_andamentos(self, cnj: str, andamentos_list: list[dict[str, Any]]) -> None:
        """Salva os andamentos judiciais no Redis."""
        try:
            payload = json.dumps(andamentos_list, ensure_ascii=False)
            await self._redis.setex(self._key_andamentos(cnj), self.TTL_ANDAMENTOS, payload)
            logger.debug("cache_andamentos_salvo", cnj=cnj, qtd=len(andamentos_list))
        except Exception as e:
            logger.error("cache_write_error", error=str(e), key=self._key_andamentos(cnj))

    async def invalidar_cache_processo(self, cnj: str) -> None:
        """Apaga forçadamente o cache de um CNJ quando o usuário clica em 'Sincronizar Agora'."""
        try:
            pipe = self._redis.pipeline()
            pipe.delete(self._key_capa(cnj))
            pipe.delete(self._key_andamentos(cnj))
            await pipe.execute()
            logger.info("cache_invalidado_manualmente", cnj=cnj)
        except Exception as e:
            logger.error("cache_invalidate_error", error=str(e), cnj=cnj)


# ---------------------------------------------------------------------------
# Helpers síncronos — para workers Celery (contexto bloqueante)
# ---------------------------------------------------------------------------
# Reutilizam as chaves e TTLs de LegalDataCacheManager para garantir que
# o cache gravado pelo orchestrator (async) seja lido pelo worker (sync)
# e vice-versa.  Graceful degradation: qualquer erro Redis retorna None/no-op.
# ---------------------------------------------------------------------------


def get_andamentos_sync(cnj: str) -> list[dict[str, Any]] | None:
    """
    Retorna a lista de andamentos do Redis (sync) ou None em caso de miss/erro.
    Usado por workers Celery antes de chamar Jusbrasil/DataJud.
    """
    try:
        cached = _sync_redis.get(LegalDataCacheManager._key_andamentos(cnj))
        if cached:
            logger.debug("cache_andamentos_hit_sync", cnj=cnj)
            data_str = cached.decode("utf-8") if isinstance(cached, bytes) else str(cached)
            return json.loads(data_str)  # type: ignore[no-any-return]
        logger.debug("cache_andamentos_miss_sync", cnj=cnj)
        return None
    except Exception as e:
        logger.error("cache_read_sync_error", error=str(e))
        return None


def set_andamentos_sync(cnj: str, andamentos: list[dict[str, Any]]) -> None:
    """
    Persiste a lista de andamentos no Redis (sync).
    Reutiliza TTL_ANDAMENTOS (6h) definido em LegalDataCacheManager.
    """
    try:
        _sync_redis.setex(
            LegalDataCacheManager._key_andamentos(cnj),
            LegalDataCacheManager.TTL_ANDAMENTOS,
            json.dumps(andamentos, ensure_ascii=False),
        )
        logger.debug("cache_andamentos_salvo_sync", cnj=cnj, qtd=len(andamentos))
    except Exception as e:
        logger.error("cache_write_sync_error", error=str(e))


def get_capa_sync(cnj: str) -> dict[str, Any] | None:
    """
    Retorna os metadados (capa) do processo do Redis (sync) ou None.
    Usado por workers Celery antes de chamar Jusbrasil/DataJud.
    """
    try:
        cached = _sync_redis.get(LegalDataCacheManager._key_capa(cnj))
        if cached:
            logger.debug("cache_capa_hit_sync", cnj=cnj)
            data_str = cached.decode("utf-8") if isinstance(cached, bytes) else str(cached)
            return json.loads(data_str)  # type: ignore[no-any-return]
        logger.debug("cache_capa_miss_sync", cnj=cnj)
        return None
    except Exception as e:
        logger.error("cache_read_sync_error", error=str(e))
        return None


def set_capa_sync(cnj: str, capa: dict[str, Any]) -> None:
    """
    Persiste os metadados (capa) do processo no Redis (sync).
    Reutiliza TTL_CAPA_PROCESSO (24h) definido em LegalDataCacheManager.
    """
    try:
        _sync_redis.setex(
            LegalDataCacheManager._key_capa(cnj),
            LegalDataCacheManager.TTL_CAPA_PROCESSO,
            json.dumps(capa, ensure_ascii=False),
        )
        logger.debug("cache_capa_salva_sync", cnj=cnj)
    except Exception as e:
        logger.error("cache_write_sync_error", error=str(e))
