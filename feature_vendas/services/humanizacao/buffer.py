"""
Buffer de mensagens: espera a pessoa terminar de falar.

Ninguém escreve um parágrafo. Escreve assim:

    19:04:02  "boa tarde"
    19:04:05  "doutor, uma dúvida"
    19:04:11  "o processo do meu irmão saiu alguma coisa?"

Um bot responde três vezes — e se entrega na primeira. Uma pessoa lê as três
e responde uma vez. Este módulo faz isso: cada mensagem que chega reinicia
uma janela de silêncio; quando a janela fecha sem nada novo, as mensagens são
concatenadas e viram UMA entrada para o orquestrador.

Implementação (debounce distribuído, sem lock):
  - cada mensagem faz INCR num contador de sequência da conversa e RPUSH no
    buffer;
  - a invocação dorme a janela de silêncio e compara o contador com o valor
    que ela viu ao chegar;
  - se mudou, outra mensagem chegou depois: esta invocação DESISTE (a mais
    recente vai responder por todas);
  - se não mudou, ela é a última: drena o buffer e devolve o texto consolidado.

Assim, N mensagens em rajada geram N invocações, mas só a última responde —
sem lock, sem corrida, e funciona com múltiplos workers Celery em paralelo.
"""

from __future__ import annotations

import asyncio
import random

import structlog
from redis.asyncio import Redis

logger = structlog.get_logger(__name__)

_TTL_S = 300  # buffer órfão (worker morreu no meio) se limpa sozinho

# Janela de silêncio: quanto esperamos por uma próxima mensagem antes de
# considerar que a pessoa terminou. Com jitter — a pausa não pode ser sempre
# igual. Áudio ganha janela maior: quem manda áudio costuma mandar outro.
_JANELA_TEXTO_S = (4.5, 7.0)
_JANELA_AUDIO_S = (7.0, 10.0)

# Teto de segurança: alguém escrevendo sem parar não pode adiar a resposta
# para sempre. Passou disso, respondemos com o que temos.
_MAX_ESPERA_TOTAL_S = 25.0


def _k_buffer(escritorio_id: int, cliente_id: int) -> str:
    return f"vendas:buf:{escritorio_id}:{cliente_id}"


def _k_seq(escritorio_id: int, cliente_id: int) -> str:
    return f"vendas:seq:{escritorio_id}:{cliente_id}"


class BufferMensagens:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def registrar(self, escritorio_id: int, cliente_id: int, texto: str) -> int:
        """Guarda a mensagem e devolve o número de sequência desta chegada."""
        pipe = self._redis.pipeline()
        pipe.rpush(_k_buffer(escritorio_id, cliente_id), texto)
        pipe.expire(_k_buffer(escritorio_id, cliente_id), _TTL_S)
        pipe.incr(_k_seq(escritorio_id, cliente_id))
        pipe.expire(_k_seq(escritorio_id, cliente_id), _TTL_S)
        resultado = await pipe.execute()
        return int(resultado[2])

    async def aguardar_e_consolidar(
        self,
        escritorio_id: int,
        cliente_id: int,
        texto: str,
        eh_audio: bool = False,
    ) -> str | None:
        """
        Ponto de entrada único.

        Devolve o texto consolidado se esta invocação é a responsável por
        responder, ou None se outra mensagem chegou depois (e portanto outra
        invocação vai responder por todas).

        O chamador simplesmente faz:
            consolidado = await buffer.aguardar_e_consolidar(...)
            if consolidado is None:
                return          # outra invocação assume
            ... segue o fluxo com `consolidado` ...
        """
        minha_seq = await self.registrar(escritorio_id, cliente_id, texto)

        esperado = 0.0
        while True:
            janela = random.uniform(*(_JANELA_AUDIO_S if eh_audio else _JANELA_TEXTO_S))
            await asyncio.sleep(janela)
            esperado += janela

            seq_atual = int(await self._redis.get(_k_seq(escritorio_id, cliente_id)) or 0)

            if seq_atual == minha_seq:
                break  # silêncio: a pessoa terminou

            if esperado >= _MAX_ESPERA_TOTAL_S:
                # Fluxo contínuo de mensagens. Respondemos com o que já temos;
                # assumimos a sequência atual para as invocações pendentes
                # desistirem em vez de responderem em duplicidade.
                logger.info(
                    "buffer_teto_espera_atingido",
                    escritorio_id=escritorio_id,
                    cliente_id=cliente_id,
                )
                minha_seq = seq_atual
                break

            # Chegou mensagem nova depois da minha: a invocação dela é a última.
            logger.debug(
                "buffer_invocacao_desiste",
                escritorio_id=escritorio_id,
                cliente_id=cliente_id,
                minha_seq=minha_seq,
                seq_atual=seq_atual,
            )
            return None

        return await self._drenar(escritorio_id, cliente_id)

    async def _drenar(self, escritorio_id: int, cliente_id: int) -> str | None:
        """Retira tudo do buffer e junta em um texto só."""
        chave = _k_buffer(escritorio_id, cliente_id)
        pipe = self._redis.pipeline()
        pipe.lrange(chave, 0, -1)
        pipe.delete(chave)
        resultado = await pipe.execute()

        itens: list[str] = [
            i.decode("utf-8") if isinstance(i, bytes) else str(i) for i in (resultado[0] or [])
        ]
        if not itens:
            return None

        if len(itens) > 1:
            logger.info(
                "buffer_mensagens_consolidadas",
                escritorio_id=escritorio_id,
                cliente_id=cliente_id,
                quantidade=len(itens),
            )

        # Junta como a pessoa escreveu: uma linha por mensagem. O modelo lê o
        # conjunto e responde uma vez só.
        return "\n".join(itens)
