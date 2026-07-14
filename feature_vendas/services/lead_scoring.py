"""
Detecção de lead quente (etapa 5 do playbook).

Decide quando a Clara para de conduzir sozinha e passa o bastão para um sócio.
Espelha os critérios do playbook, qualquer um dispara:

  - pediu preço, proposta, trial ou reunião      (sinal explícito de compra)
  - escritório com 5+ advogados E engajado         (ticket justifica a call)
  - qualificação completa E ainda conversando      (lead trabalhado, maduro)

Barato e explicável: regex + estado da qualificação, sem token. (Uma camada
LLM pode refinar depois, como o matching da F3 faz, se houver falso positivo.)
O objetivo não é adivinhar intenção sutil — é não deixar passar um lead que
está claramente pedindo para avançar.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Sinais explícitos de compra. Ordenados por força; o primeiro que casar vence.
_SINAIS = {
    "pediu_reuniao": re.compile(
        r"\b(reuni[aã]o|conversar|falar com|marca(r)?|agenda(r)?|call|liga(r|ção))\b", re.I
    ),
    "pediu_preco": re.compile(
        r"\b(pre[çc]o|quanto custa|valor|mensalidade|plano[s]?|quanto (é|fica|sai))\b", re.I
    ),
    "pediu_trial": re.compile(
        r"\b(test(ar|e)|trial|experiment(ar|o)|degusta|gr[aá]tis|como come[çc]o|contrat(ar|o))\b",
        re.I,
    ),
    "pediu_proposta": re.compile(
        r"\b(proposta|or[çc]amento|contrato|como funciona a assinatura)\b", re.I
    ),
}

_MIN_INTERACOES_ENGAJADO = 3
_MIN_ADVOGADOS_QUENTE = 5


@dataclass(frozen=True)
class Qualificacao:
    """O que a Clara já descobriu na conversa (etapa 4)."""

    num_advogados: int | None = None
    area: str | None = None
    quem_responde: str | None = None  # "eles" | "secretaria" | None

    @property
    def completa(self) -> bool:
        return all((self.num_advogados is not None, self.area, self.quem_responde))


@dataclass(frozen=True)
class ResultadoLead:
    quente: bool
    gatilho: str  # o motivo do handoff (vai no briefing do sócio)
    sinais: list[str]


def avaliar_lead(
    *,
    ultima_mensagem: str,
    total_interacoes: int,
    qualificacao: Qualificacao,
) -> ResultadoLead:
    sinais: list[str] = [nome for nome, rx in _SINAIS.items() if rx.search(ultima_mensagem)]

    # 1. Pedido explícito de avançar — o mais forte, dispara sozinho.
    for prioridade in ("pediu_reuniao", "pediu_trial", "pediu_preco", "pediu_proposta"):
        if prioridade in sinais:
            return ResultadoLead(True, prioridade, sinais)

    engajado = total_interacoes >= _MIN_INTERACOES_ENGAJADO

    # 2. Escritório grande e já conversando.
    if (
        qualificacao.num_advogados is not None
        and qualificacao.num_advogados >= _MIN_ADVOGADOS_QUENTE
        and engajado
    ):
        return ResultadoLead(True, "escritorio_grande_engajado", sinais)

    # 3. Qualificação completa e ainda na conversa.
    if qualificacao.completa and engajado:
        return ResultadoLead(True, "qualificacao_completa", sinais)

    return ResultadoLead(False, "", sinais)


# Rótulos legíveis para o briefing do sócio.
GATILHO_LABEL = {
    "pediu_reuniao": "pediu para conversar/marcar reunião",
    "pediu_preco": "perguntou preço",
    "pediu_trial": "quer testar / começar",
    "pediu_proposta": "pediu proposta",
    "escritorio_grande_engajado": "escritório 5+ advogados, engajado",
    "qualificacao_completa": "qualificado e engajado",
}
