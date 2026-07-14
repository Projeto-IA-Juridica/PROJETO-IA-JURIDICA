"""
Validação da mensagem-espelho (etapa 3 do roteiro): a rede anti-vexame.

Antes de disparar uma mensagem que cita um processo real de um escritório real,
confere se os dados batem com a fonte. Um espelho errado (processo de outro
escritório, movimentação mal interpretada) enviado a frio queima o alvo para
sempre. Este é o mesmo princípio do fact-checker anti-alucinação do produto.

Saída → decide a fila:
    confianca >= _LIMIAR_ENVIO   → fila_envio   (dispara automático)
    confianca <  _LIMIAR_ENVIO   → fila_excecao (humano revisa só estas)
    Template B                    → fila_envio   (não cita processo; nada a validar)

O humano só olha a fila de exceção — os poucos casos duvidosos. O grosso passa
direto. É isso que torna o disparo automático sem virar roleta.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

logger = structlog.get_logger(__name__)

_LIMIAR_ENVIO = 70  # 0-100


@dataclass(frozen=True)
class ResultadoValidacao:
    confianca: int
    fila: str  # "fila_envio" | "fila_excecao"
    observacao: str


def _tem_dado_sensivel(movimentacao: str) -> bool:
    """Não prospectar em cima de matéria sensível (mesmo espírito da F3 B2C)."""
    m = movimentacao.lower()
    gatilhos = (
        "internação",
        "interdição",
        "curatela",
        "alienação parental",
        "violência doméstica",
        "abuso",
        "guarda de menor",
    )
    return any(g in m for g in gatilhos)


def validar_espelho(
    *,
    template: str,
    processo_cnj: str | None,
    movimentacao_bruta: str | None,
    mensagem: str,
) -> ResultadoValidacao:
    """
    Validação determinística das invariantes do espelho. Barata e explicável;
    não gasta token. (Uma segunda camada com LLM pode ser plugada aqui depois,
    reusando o FactChecker do produto, se a taxa de erro justificar.)
    """
    if template == "B":
        return ResultadoValidacao(100, "fila_envio", "template genérico, sem processo a validar")

    confianca = 100
    obs: list[str] = []

    if not processo_cnj:
        return ResultadoValidacao(0, "fila_excecao", "template A sem CNJ")

    # CNJ no formato NNNNNNN-DD.AAAA.J.TR.OOOO (20 dígitos).
    digitos = [c for c in processo_cnj if c.isdigit()]
    if len(digitos) != 20:
        confianca -= 40
        obs.append("CNJ com número de dígitos fora do padrão")

    if not movimentacao_bruta or len(movimentacao_bruta.strip()) < 15:
        confianca -= 40
        obs.append("movimentação vazia ou curta demais para traduzir com segurança")

    if movimentacao_bruta and _tem_dado_sensivel(movimentacao_bruta):
        return ResultadoValidacao(0, "fila_excecao", "matéria sensível: não prospectar")

    # A mensagem precisa conter o CNJ citado. Se não contém, o template quebrou
    # (a mensagem não é o espelho daquele processo) — erro estrutural, não de
    # confiança: vai direto para exceção, nunca dispara automático.
    if processo_cnj not in mensagem:
        return ResultadoValidacao(0, "fila_excecao", "CNJ não aparece na mensagem montada")

    confianca = max(0, confianca)
    fila = "fila_envio" if confianca >= _LIMIAR_ENVIO else "fila_excecao"

    logger.info("validacao_espelho", cnj=processo_cnj, confianca=confianca, fila=fila)
    return ResultadoValidacao(confianca, fila, "; ".join(obs) or "ok")
