"""
Enriquecimento (etapa 2 do roteiro): alvo → mensagem-espelho.

Duas formas de chegar no processo, por prioridade:

  1. CNJ na planilha (você faz a descoberta).  ← caminho principal hoje
     Dado o número CNJ, a máquina busca a movimentação mais recente sozinha
     (reusa o DataJudClient do produto — funciona hoje, sem Escavador) e monta
     o Template A (espelho com processo real).

  2. Descoberta por OAB (futuro).
     Interface `DescobridorProcessos` para quando houver fonte que indexe por
     OAB (Escavador). Enquanto injetado como None, esse caminho não roda.

Sem nenhum processo (sem CNJ e sem descoberta), cai no Template B (dor genérica
+ vitrine). Não é falha: é o caminho esperado para alvo sem processo informado.

O que o sistema CONSEGUE e o que NÃO consegue:
  - descobrir QUAIS processos são de um advogado a partir da OAB → NÃO
    (DataJud não indexa por OAB; mesma trava da F3).
  - dado um CNJ, pegar a movimentação recente → SIM, hoje.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import structlog

from feature_1_ia_personalizada.services.ai.juridical_translator import JuridicalTranslator

logger = structlog.get_logger(__name__)


class LeitorAndamentos(Protocol):
    """Dado um CNJ, devolve a descrição da movimentação mais recente (ou None)."""

    async def movimentacao_recente(self, cnj: str) -> str | None: ...


class DescobridorProcessos(Protocol):
    """Fonte que resolve OAB → processo recente. Implementar com Escavador."""

    async def processo_recente_por_oab(self, oab: str) -> dict | None:
        """Retorna {"cnj": str, "movimentacao": str} ou None."""
        ...


class LeitorDataJud:
    """
    Implementação padrão do LeitorAndamentos usando o DataJudClient do produto.
    Pega o andamento mais recente com texto (ordena por data desc).
    """

    def __init__(self, datajud_client: Any) -> None:
        self._client = datajud_client

    async def movimentacao_recente(self, cnj: str) -> str | None:
        try:
            andamentos = await self._client.buscar_andamentos_async(cnj)
        except Exception as exc:
            logger.warning("enriquecimento_datajud_falhou", cnj=cnj, erro=str(exc))
            return None

        # buscar_andamentos_async → [{"texto": str, "data": str|None}]
        com_texto = [a for a in andamentos if (a.get("texto") or "").strip()]
        if not com_texto:
            return None
        # Mais recente primeiro; data ISO ordena lexicograficamente, None por último.
        com_texto.sort(key=lambda a: a.get("data") or "", reverse=True)
        return str(com_texto[0]["texto"]).strip()


_TITULOS = {
    "dr",
    "dr.",
    "dra",
    "dra.",
    "doutor",
    "doutora",
    "adv",
    "adv.",
    "sr",
    "sr.",
    "sra",
    "sra.",
}


def _primeiro_nome(nome_contato: str | None) -> str:
    """Primeiro nome real, pulando títulos ('Dr. Marcos' → 'Marcos')."""
    if not nome_contato:
        return "advogado(a)"
    for parte in nome_contato.split():
        if parte.lower().strip(".") not in {t.strip(".") for t in _TITULOS}:
            return parte
    return "advogado(a)"


@dataclass(frozen=True)
class MensagemEnriquecida:
    template: str  # "A" | "B"
    texto: str
    processo_cnj: str | None
    movimentacao_bruta: str | None


_TEMPLATE_A = (
    "Doutor(a) {nome}, boa tarde, aqui é o Gabriel.\n"
    "Reparei que o processo {cnj} do seu escritório teve movimentação esses dias.\n"
    "Se você usasse a nossa plataforma, seu cliente teria recebido isso no "
    "WhatsApp automaticamente, poucos minutos depois:\n"
    '"{espelho}"\n'
    "Quem escreveu foi a IA, sozinha, a partir do andamento real. Quer conversar "
    "com ela como se fosse seu próprio cliente? É só mandar um oi aqui: {vitrine}"
)

_TEMPLATE_B = (
    "Doutor(a) {nome}, boa tarde, aqui é o Gabriel.\n"
    "A gente montou uma assistente de IA que atende os clientes do escritório no "
    "WhatsApp: avisa quando o processo anda, tira as dúvidas de sempre e marca "
    "reunião na sua agenda.\n"
    "Quer testar como se você fosse seu próprio cliente? Manda um oi aqui: {vitrine}"
)


class Enriquecedor:
    def __init__(
        self,
        vitrine_url: str,
        leitor: LeitorAndamentos | None = None,
        descobridor: DescobridorProcessos | None = None,
    ) -> None:
        self._vitrine = vitrine_url
        self._leitor = leitor
        self._descobridor = descobridor

    async def enriquecer(
        self,
        nome_contato: str | None,
        oab: str | None = None,
        processo_cnj: str | None = None,
    ) -> MensagemEnriquecida:
        nome = _primeiro_nome(nome_contato)

        cnj = (processo_cnj or "").strip() or None
        movimentacao: str | None = None

        # Caminho 1: CNJ veio na planilha → busca a movimentação direto.
        if cnj and self._leitor is not None:
            movimentacao = await self._leitor.movimentacao_recente(cnj)

        # Caminho 2: sem CNJ, mas com descoberta por OAB (futuro).
        if not movimentacao and not cnj and oab and self._descobridor is not None:
            try:
                achado = await self._descobridor.processo_recente_por_oab(oab)
            except Exception as exc:
                logger.warning("enriquecimento_descoberta_falhou", oab=oab, erro=str(exc))
                achado = None
            if achado and achado.get("movimentacao"):
                cnj = achado["cnj"]
                movimentacao = achado["movimentacao"]

        if cnj and movimentacao:
            espelho = JuridicalTranslator.traduzir_andamento(movimentacao)
            texto = _TEMPLATE_A.format(
                nome=nome, cnj=cnj, espelho=espelho.strip(), vitrine=self._vitrine
            )
            return MensagemEnriquecida("A", texto, cnj, movimentacao)

        # Template B: sem processo ou sem movimentação disponível.
        texto = _TEMPLATE_B.format(nome=nome, vitrine=self._vitrine)
        return MensagemEnriquecida("B", texto, None, None)
