# feature_1_ia_personalizada/services/ai/memory.py
from __future__ import annotations

import json
from typing import Literal

import structlog
from redis.asyncio import Redis

logger = structlog.get_logger(__name__)

_TTL_SEGUNDOS = 60 * 60 * 24 * 7  # 7 dias sem interação → histórico expira
_MAX_MENSAGENS = 100  # FIFO: remove as mais antigas ao atingir o limite
_MAX_CONTENT_CHARS = 4096  # trunca conteúdo antes de serializar — proteção de memória


def _chave(escritorio_id: int, cliente_id: int) -> str:
    return f"f1:conv:{escritorio_id}:{cliente_id}"


class ConversationMemory:
    """
    Armazena o histórico de conversa de cada cliente no Redis.

    Estrutura: Redis List onde cada elemento é um JSON compacto {role, content}.
    A lista cresce pelo final (RPUSH) e é lida do início (LRANGE).
    TTL de 7 dias é renovado a cada interação — conversa "reinicia" após inatividade.
    """

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def salvar_mensagem(
        self,
        escritorio_id: int,
        cliente_id: int,
        role: Literal["user", "assistant"],
        content: str,
    ) -> None:
        """
        Adiciona uma mensagem ao final do histórico.
        Remove a mensagem mais antiga se o limite de 100 for atingido.
        Renova o TTL de 7 dias.
        """
        chave = _chave(escritorio_id, cliente_id)
        content_truncado = content[:_MAX_CONTENT_CHARS]
        payload = json.dumps({"role": role, "content": content_truncado}, ensure_ascii=False)

        pipe = self._redis.pipeline()
        pipe.rpush(chave, payload)
        # Mantém apenas as últimas _MAX_MENSAGENS — LTRIM descarta as mais antigas
        pipe.ltrim(chave, -_MAX_MENSAGENS, -1)
        pipe.expire(chave, _TTL_SEGUNDOS)
        await pipe.execute()

        logger.debug(
            "memoria_mensagem_salva",
            escritorio_id=escritorio_id,
            cliente_id=cliente_id,
            role=role,
        )

    async def buscar_historico(
        self,
        escritorio_id: int,
        cliente_id: int,
        limite: int = 20,
    ) -> list[dict[str, str]]:
        """
        Retorna as últimas `limite` mensagens no formato [{role, content}].
        Retorna lista vazia se não houver histórico ou se estiver expirado.
        """
        chave = _chave(escritorio_id, cliente_id)

        # Pipeline: busca histórico e renova TTL atomicamente
        pipe = self._redis.pipeline()
        pipe.lrange(chave, -limite, -1)
        pipe.expire(chave, _TTL_SEGUNDOS)
        resultados = await pipe.execute()
        raw: list[bytes] = resultados[0]

        historico: list[dict[str, str]] = []
        for item in raw:
            try:
                historico.append(json.loads(item))
            except json.JSONDecodeError:
                # Não loga o conteúdo bruto — pode conter dados pessoais (LGPD)
                logger.warning(
                    "memoria_item_invalido",
                    escritorio_id=escritorio_id,
                    cliente_id=cliente_id,
                )

        return historico

    async def limpar_historico(self, escritorio_id: int, cliente_id: int) -> None:
        """Remove completamente o histórico da conversa."""
        chave = _chave(escritorio_id, cliente_id)
        await self._redis.delete(chave)
        logger.info(
            "memoria_historico_limpo",
            escritorio_id=escritorio_id,
            cliente_id=cliente_id,
        )

    async def tamanho_historico(self, escritorio_id: int, cliente_id: int) -> int:
        """Retorna o número de mensagens no histórico. Útil para debug e testes."""
        chave = _chave(escritorio_id, cliente_id)
        tamanho: int = await self._redis.llen(chave)  # type: ignore[misc]
        return tamanho
