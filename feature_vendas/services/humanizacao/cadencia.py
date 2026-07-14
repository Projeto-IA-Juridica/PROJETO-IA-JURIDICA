"""
O ritmo da conversa: leitura, "digitando", envio, pausa entre balões.

Modelo mental — o que uma pessoa faz ao receber uma mensagem no celular:

    vê a mensagem  →  lê (alguns segundos)  →  começa a digitar
                          ↓                         ↓
                     tick azul              "digitando..." aparece
                                                    ↓
                                        envia o balão 1, pensa, digita o 2

Nada aqui é constante: todo intervalo tem jitter. Timing determinístico é o
tique mais fácil de perceber — se a resposta chega SEMPRE 3.0s depois, é bot,
por melhor que seja o texto.

Teto de latência: a soma dos delays de uma resposta típica fica em 6–14s.
Passar muito disso é irritante e derruba a conversa; a naturalidade não pode
custar a experiência.
"""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass

import structlog

logger = structlog.get_logger(__name__)

# Leitura: pessoa bate o olho e entende. Cresce um pouco com o tamanho do que
# recebeu, mas satura — ninguém "lê" por 30s antes de responder.
_LEITURA_BASE_S = (1.4, 3.2)
_LEITURA_POR_CHAR_S = 0.012
_LEITURA_MAX_S = 6.0

# Digitação: ~11–14 chars/s é polegar rápido de celular. Abaixo do mínimo
# a mensagem "aparece" instantânea; acima do máximo a espera irrita.
_CPS = (10.5, 14.5)
_DIGITACAO_MIN_S = 1.3
_DIGITACAO_MAX_S = 6.5

# Respiro entre um balão e o próximo (a pessoa aperta enviar e volta a digitar).
_ENTRE_CHUNKS_S = (0.5, 1.4)

# De vez em quando alguém demora: pegou o celular, foi ver outra coisa, voltou.
# Baixa probabilidade e teto curto — realismo não pode virar lentidão.
_CHANCE_PAUSA_LONGA = 0.07
_PAUSA_LONGA_S = (4.0, 9.0)


@dataclass(frozen=True)
class Ritmo:
    """Tempos calculados de uma resposta. Em segundos."""

    leitura: float
    digitacao: list[float]  # um por balão
    entre_chunks: list[float]  # len == len(digitacao) - 1

    @property
    def total(self) -> float:
        return self.leitura + sum(self.digitacao) + sum(self.entre_chunks)


def _jitter(faixa: tuple[float, float]) -> float:
    return random.uniform(*faixa)


def calcular_leitura(texto_recebido: str) -> float:
    base = _jitter(_LEITURA_BASE_S) + len(texto_recebido) * _LEITURA_POR_CHAR_S
    if random.random() < _CHANCE_PAUSA_LONGA:
        base += _jitter(_PAUSA_LONGA_S)
    return min(base, _LEITURA_MAX_S + _PAUSA_LONGA_S[1])


def calcular_digitacao(chunk: str) -> float:
    """
    Tempo de digitação de um balão.

    Os limites (min/max) também levam jitter. Sem isso, todo balão longo bate
    exatamente no teto e a conversa sai com delays idênticos (6.5s, 6.5s, 6.5s)
    — repetição exata de timing é o tique de bot mais fácil de perceber, mesmo
    com o texto perfeito.
    """
    segundos = len(chunk) / _jitter(_CPS)
    if segundos > _DIGITACAO_MAX_S:
        return _DIGITACAO_MAX_S * random.uniform(0.80, 1.0)
    if segundos < _DIGITACAO_MIN_S:
        return _DIGITACAO_MIN_S * random.uniform(1.0, 1.35)
    return segundos


def calcular_ritmo(texto_recebido: str, chunks: list[str]) -> Ritmo:
    """Monta o ritmo completo de uma resposta já quebrada em balões."""
    digitacao = [calcular_digitacao(c) for c in chunks]
    entre = [_jitter(_ENTRE_CHUNKS_S) for _ in range(max(0, len(chunks) - 1))]
    return Ritmo(leitura=calcular_leitura(texto_recebido), digitacao=digitacao, entre_chunks=entre)


class EntregaHumanizada:
    """
    Envia uma resposta com o ritmo de uma pessoa.

    Usa o `delay` nativo do Evolution no sendText: a própria Evolution exibe
    "digitando..." pelo tempo pedido e só então entrega o balão. Isso mantém
    o indicador e o envio atômicos — sem risco de "digitando" preso na tela
    se o processo morrer no meio.

    Uso:
        entrega = EntregaHumanizada(evolution, instancia)
        await entrega.responder(numero, texto_recebido, resposta_do_claude)
    """

    def __init__(self, evolution, instancia: str) -> None:  # noqa: ANN001 — EvolutionClient
        self._evo = evolution
        self._instancia = instancia

    async def responder(
        self,
        numero: str,
        texto_recebido: str,
        resposta: str,
        message_id: str | None = None,
    ) -> list[str]:
        """
        Executa a sequência completa: tick azul, pausa de leitura, e os balões
        com "digitando" entre eles. Devolve os balões efetivamente enviados.
        """
        from feature_vendas.services.humanizacao.chunker import quebrar

        chunks = quebrar(resposta)
        if not chunks:
            return []

        ritmo = calcular_ritmo(texto_recebido, chunks)

        # Tick azul primeiro: a pessoa viu a mensagem, ainda não respondeu.
        if message_id:
            try:
                await self._evo.marcar_como_lida(self._instancia, numero, message_id)
            except Exception as exc:  # best-effort — nunca segura a resposta
                logger.debug("humanizacao_marcar_lida_falhou", erro=str(exc))

        await asyncio.sleep(ritmo.leitura)

        for i, chunk in enumerate(chunks):
            await self._evo.enviar_texto(
                self._instancia,
                numero,
                chunk,
                delay_ms=int(ritmo.digitacao[i] * 1000),
            )
            if i < len(ritmo.entre_chunks):
                await asyncio.sleep(ritmo.entre_chunks[i])

        logger.info(
            "humanizacao_resposta_entregue",
            balões=len(chunks),
            segundos_total=round(ritmo.total, 1),
        )
        return chunks
