"""
Eventos de agendamento em tempo real (Redis pub/sub → SSE).

Toda transição de estado publica um sinal leve ("changed") no canal do
escritório; o endpoint GET /agendamentos/stream repassa via Server-Sent
Events e o frontend invalida as queries — o card de aprovação some em
milissegundos em vez de esperar o próximo ciclo de polling.

O polling continua existindo como fallback (rede corporativa bloqueando
streaming, Redis fora etc.); com o stream conectado o frontend reduz a
frequência. Publicação é SEMPRE best-effort: falha de Redis nunca pode
quebrar uma confirmação de reunião.
"""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_CANAL_PREFIXO = "agendamento_ev"


def canal_agendamento(escritorio_id: int) -> str:
    return f"{_CANAL_PREFIXO}:{escritorio_id}"


async def publicar_evento_agendamento(redis: Any, escritorio_id: int) -> None:
    """Sinaliza mudança nos agendamentos do escritório. Nunca levanta exceção."""
    if redis is None:
        return
    try:
        await redis.publish(canal_agendamento(escritorio_id), "changed")
    except Exception as exc:
        logger.debug(
            "agendamento_evento_publicacao_falhou",
            escritorio_id=escritorio_id,
            erro=str(exc),
        )
