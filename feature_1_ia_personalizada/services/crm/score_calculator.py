"""
feature_1_ia_personalizada/services/crm/score_calculator.py
=============================================================
CRMScoreCalculator — função pura, sem banco e sem Claude.

Recebe um CRMContexto e retorna um CRMScore com score 0–100,
nível textual e detalhamento de cada componente para auditoria.
"""

from __future__ import annotations

from dataclasses import dataclass

from feature_1_ia_personalizada.services.crm.aggregator import CRMContexto
from shared.config.constants import (
    CRM_CONTATO_PONTOS,
    CRM_ENGAJAMENTO_PONTOS,
    CRM_NIVEL_FAIXAS,
    CRM_NPS_PONTOS,
    CRM_NPS_PONTOS_NULO,
    CRM_SCORE_PESOS,
)


@dataclass
class CRMScore:
    score: int  # 0–100 arredondado
    nivel: str  # excelente | satisfeito | neutro | em_risco | critico
    fatores: dict  # detalhamento de cada componente (pontos e peso aplicado)


# ---------------------------------------------------------------------------
# Helpers de lookup
# ---------------------------------------------------------------------------


def _pontos_nps(nps_medio: float | None) -> int:
    if nps_medio is None:
        return CRM_NPS_PONTOS_NULO
    nota = round(nps_medio)
    nota = max(1, min(5, nota))
    return CRM_NPS_PONTOS[nota]


def _pontos_contato(dias: int) -> int:
    for limite, pontos in CRM_CONTATO_PONTOS:
        if dias <= limite:
            return pontos
    return 0


def _pontos_engajamento(total_30d: int) -> int:
    # Itera do maior limite para o menor; retorna ao primeiro `total > limite`
    for limite, pontos in CRM_ENGAJAMENTO_PONTOS:
        if total_30d > limite:
            return pontos
    return 0  # total_30d == 0


def _pontos_escalacoes(pendentes: int, rejeitadas_30d: int) -> int:
    # Spec define: pendente → 30pts, rejeitada → 10pts, nenhuma → 100pts.
    # Extensão: ≥ 3 pendentes é situação crítica → 0pts (gap na spec preenchido
    # para evitar que o pior caso possível seja 30pts independente do volume).
    if pendentes >= 3:
        return 0
    if pendentes > 0:
        return 30
    if rejeitadas_30d > 0:
        return 10
    return 100


def _nivel(score: int) -> str:
    for minimo, nivel in CRM_NIVEL_FAIXAS:
        if score >= minimo:
            return nivel
    return "critico"


# ---------------------------------------------------------------------------
# Função pública
# ---------------------------------------------------------------------------


def calcular_score_crm(contexto: CRMContexto) -> CRMScore:
    """
    Calcula o score CRM a partir de um CRMContexto.
    Função pura — sem I/O, sem efeitos colaterais.
    """
    p_nps = _pontos_nps(contexto.nps_medio_3m)
    p_contato = _pontos_contato(contexto.dias_desde_ultimo_contato)
    p_engajamento = _pontos_engajamento(contexto.total_interacoes_30d)
    p_escalacoes = _pontos_escalacoes(
        contexto.escalacoes_pendentes,
        contexto.escalacoes_rejeitadas_30d,
    )

    pesos = CRM_SCORE_PESOS
    score_float = (
        p_nps * pesos["nps"]
        + p_contato * pesos["contato"]
        + p_engajamento * pesos["engajamento"]
        + p_escalacoes * pesos["escalacoes"]
    )
    score = max(0, min(100, round(score_float)))

    fatores = {
        "nps": {
            "pontos": p_nps,
            "peso": pesos["nps"],
            "contribuicao": round(p_nps * pesos["nps"], 1),
        },
        "contato": {
            "pontos": p_contato,
            "peso": pesos["contato"],
            "contribuicao": round(p_contato * pesos["contato"], 1),
        },
        "engajamento": {
            "pontos": p_engajamento,
            "peso": pesos["engajamento"],
            "contribuicao": round(p_engajamento * pesos["engajamento"], 1),
        },
        "escalacoes": {
            "pontos": p_escalacoes,
            "peso": pesos["escalacoes"],
            "contribuicao": round(p_escalacoes * pesos["escalacoes"], 1),
        },
    }

    return CRMScore(score=score, nivel=_nivel(score), fatores=fatores)
