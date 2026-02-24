"""
feature_1_ia_personalizada/services/legal_data/cache_manager.py

Módulo responsável por gerenciar políticas de Cache (Tempo de Vida da Memória)
das chamadas demoradas de Tribunais e APIs pagas (Jusbrasil / Datajud).

A principal vantagem usar o Upstash Redis aqui é reduzir o consumo de APIs (Custo USD)
e diminuir a latência gigantesca quando advogados buscam o mesmo processo no
mesmo dia recorrentemente. 
"""

import json
from datetime import timedelta
from typing import Optional, Any, Dict, List
import structlog
from redis.asyncio import Redis

logger = structlog.get_logger(__name__)

class LegalDataCacheManager:
    """Gerencia caching para as consultas de processos e andamentos judiciais."""

    # Configuração de Tempos (TTL - Time to Live)
    TTL_CAPA_PROCESSO = int(timedelta(hours=24).total_seconds())  # Capa muda muito pouco, 24 horas.
    TTL_ANDAMENTOS = int(timedelta(hours=6).total_seconds())      # Andamentos mudam mais em dias úteis, 6 horas.

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

    async def get_capa(self, cnj: str) -> Optional[Dict[str, Any]]:
        """Busca do Redis a Capa do processo, se existir dentro do TTL."""
        try:
            cached_data = await self._redis.get(self._key_capa(cnj))
            if cached_data:
                logger.debug("cache_capa_hit", cnj=cnj)
                return json.loads(cached_data)
                
            logger.debug("cache_capa_miss", cnj=cnj)
            return None
        except Exception as e:
            # Em caso de falha no Redis, avisamos o Log mas não quebramos a aplicação (Graceful Degradation)
            logger.error("cache_read_error", error=str(e), key=self._key_capa(cnj))
            return None

    async def set_capa(self, cnj: str, capa_data: Dict[str, Any]) -> None:
        """Salva a Capa no Redis pelo TTL designado."""
        try:
            payload = json.dumps(capa_data, ensure_ascii=False)
            await self._redis.setex(
                self._key_capa(cnj), 
                self.TTL_CAPA_PROCESSO, 
                payload
            )
            logger.debug("cache_capa_salva", cnj=cnj)
        except Exception as e:
            logger.error("cache_write_error", error=str(e), key=self._key_capa(cnj))

    async def get_andamentos(self, cnj: str) -> Optional[List[Dict[str, Any]]]:
        """Busca do Redis a Timeline de Andamentos, se existir dentro do TTL."""
        try:
            cached_data = await self._redis.get(self._key_andamentos(cnj))
            if cached_data:
                logger.debug("cache_andamentos_hit", cnj=cnj)
                return json.loads(cached_data)
                
            logger.debug("cache_andamentos_miss", cnj=cnj)
            return None
        except Exception as e:
            logger.error("cache_read_error", error=str(e), key=self._key_andamentos(cnj))
            return None

    async def set_andamentos(self, cnj: str, andamentos_list: List[Dict[str, Any]]) -> None:
        """Salva os andamentos judiciais no Redis."""
        try:
            payload = json.dumps(andamentos_list, ensure_ascii=False)
            await self._redis.setex(
                self._key_andamentos(cnj), 
                self.TTL_ANDAMENTOS, 
                payload
            )
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
