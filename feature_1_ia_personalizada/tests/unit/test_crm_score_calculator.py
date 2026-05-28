# feature_1_ia_personalizada/tests/unit/test_crm_score_calculator.py
"""
Testes unitários para CRMScoreCalculator (Feature 7).

Cobertura:
  - Pesos somam 100%
  - Cada componente individualmente (NPS nulo, sem contato, etc.)
  - Mapeamento score → nível para todas as faixas
  - Cliente perfeito: score ≥ 85
  - Cliente crítico: score ≤ 10
  - Compliance OAB: palavras proibidas ausentes dos campos CRM
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from feature_1_ia_personalizada.services.crm.aggregator import (
    CRMContexto,
    NPSRegistro,
)
from feature_1_ia_personalizada.services.crm.score_calculator import (
    _pontos_contato,
    _pontos_engajamento,
    _pontos_escalacoes,
    _pontos_nps,
    calcular_score_crm,
)
from shared.config.constants import CRM_SCORE_PESOS

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ctx(**kwargs) -> CRMContexto:
    defaults = {
        "cliente_id": 1,
        "escritorio_id": 1,
        "nome": "Teste",
        "profissao": None,
        "empresa": None,
        "data_nascimento": None,
        "nps_historico": [],
        "nps_medio_3m": None,
        "total_interacoes_30d": 5,
        "total_interacoes_90d": 15,
        "dias_desde_ultimo_contato": 10,
        "ultimo_contato_at": datetime.now(UTC) - timedelta(days=10),
        "processos_ativos": [],
        "pior_score_risco": None,
        "escalacoes_pendentes": 0,
        "escalacoes_rejeitadas_30d": 0,
        "crm_score_anterior": None,
        "crm_analisado_em_anterior": None,
        "crm_resumo_anterior": None,
        "crm_acao_sugerida_anterior": None,
    }
    defaults.update(kwargs)
    return CRMContexto(**defaults)


# ---------------------------------------------------------------------------
# Pesos
# ---------------------------------------------------------------------------


def test_pesos_somam_100_porcento():
    total = sum(CRM_SCORE_PESOS.values())
    assert abs(total - 1.0) < 1e-9, f"Pesos somam {total}, esperado 1.0"


# ---------------------------------------------------------------------------
# Componente NPS
# ---------------------------------------------------------------------------


def test_nps_nulo_retorna_40_pontos():
    assert _pontos_nps(None) == 40


@pytest.mark.parametrize(
    "nps,esperado",
    [
        (5.0, 100),
        (4.0, 80),
        (3.0, 50),
        (2.0, 20),
        (1.0, 0),
    ],
)
def test_nps_por_nota(nps, esperado):
    assert _pontos_nps(nps) == esperado


def test_nps_arredondado_para_inteiro_mais_proximo():
    # 4.6 → arredonda para 5 → 100pts
    assert _pontos_nps(4.6) == 100
    # 3.4 → arredonda para 3 → 50pts
    assert _pontos_nps(3.4) == 50


# ---------------------------------------------------------------------------
# Componente contato
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "dias,esperado",
    [
        (0, 100),
        (7, 100),
        (8, 70),
        (30, 70),
        (31, 30),
        (60, 30),
        (61, 0),
        (999, 0),
    ],
)
def test_pontos_contato_faixas(dias, esperado):
    assert _pontos_contato(dias) == esperado


# ---------------------------------------------------------------------------
# Componente engajamento
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "interacoes,esperado",
    [
        (0, 0),
        (1, 40),
        (4, 40),
        (5, 70),
        (10, 70),
        (11, 100),
    ],
)
def test_pontos_engajamento_faixas(interacoes, esperado):
    assert _pontos_engajamento(interacoes) == esperado


# ---------------------------------------------------------------------------
# Componente escalações
# ---------------------------------------------------------------------------


def test_sem_escalacoes_retorna_100():
    assert _pontos_escalacoes(0, 0) == 100


def test_uma_escalacao_pendente_retorna_30():
    assert _pontos_escalacoes(1, 0) == 30


def test_escalacao_rejeitada_retorna_10():
    assert _pontos_escalacoes(0, 1) == 10


def test_tres_ou_mais_pendentes_retorna_zero():
    assert _pontos_escalacoes(3, 0) == 0
    assert _pontos_escalacoes(5, 2) == 0


def test_pendente_tem_prioridade_sobre_rejeitada():
    # pendente (1) → 30pts, não 10pts da rejeitada
    assert _pontos_escalacoes(1, 1) == 30


# ---------------------------------------------------------------------------
# Mapeamento score → nível
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "score,nivel_esperado",
    [
        (100, "excelente"),
        (76, "excelente"),
        (75, "satisfeito"),
        (51, "satisfeito"),
        (50, "neutro"),
        (26, "neutro"),
        (25, "em_risco"),
        (11, "em_risco"),
        (10, "critico"),
        (0, "critico"),
    ],
)
def test_nivel_por_faixa_de_score(score, nivel_esperado):
    # Monta um contexto que produza exatamente o score desejado via mock do cálculo
    from feature_1_ia_personalizada.services.crm.score_calculator import _nivel

    assert _nivel(score) == nivel_esperado


# ---------------------------------------------------------------------------
# Cliente perfeito → score ≥ 85
# ---------------------------------------------------------------------------


def test_cliente_perfeito_score_alto():
    ctx = _ctx(
        nps_medio_3m=5.0,
        nps_historico=[NPSRegistro(data=datetime.now(UTC), nota=5)],
        dias_desde_ultimo_contato=1,
        total_interacoes_30d=15,
        escalacoes_pendentes=0,
        escalacoes_rejeitadas_30d=0,
    )
    resultado = calcular_score_crm(ctx)
    assert resultado.score >= 85, f"Esperado ≥ 85, obtido {resultado.score}"
    assert resultado.nivel == "excelente"


# ---------------------------------------------------------------------------
# Cliente crítico → score ≤ 10
# ---------------------------------------------------------------------------


def test_cliente_critico_score_baixo():
    ctx = _ctx(
        nps_medio_3m=1.0,
        nps_historico=[NPSRegistro(data=datetime.now(UTC), nota=1)],
        dias_desde_ultimo_contato=90,
        total_interacoes_30d=0,
        escalacoes_pendentes=3,
        escalacoes_rejeitadas_30d=2,
    )
    resultado = calcular_score_crm(ctx)
    assert resultado.score <= 10, f"Esperado ≤ 10, obtido {resultado.score}"
    assert resultado.nivel == "critico"


# ---------------------------------------------------------------------------
# Estrutura do resultado
# ---------------------------------------------------------------------------


def test_fatores_contem_todos_os_componentes():
    ctx = _ctx()
    resultado = calcular_score_crm(ctx)
    for chave in ("nps", "contato", "engajamento", "escalacoes"):
        assert chave in resultado.fatores
        assert "pontos" in resultado.fatores[chave]
        assert "peso" in resultado.fatores[chave]
        assert "contribuicao" in resultado.fatores[chave]


def test_score_sempre_entre_0_e_100():
    for ctx in [
        _ctx(nps_medio_3m=5.0, dias_desde_ultimo_contato=0, total_interacoes_30d=20),
        _ctx(
            nps_medio_3m=1.0,
            dias_desde_ultimo_contato=999,
            total_interacoes_30d=0,
            escalacoes_pendentes=5,
        ),
    ]:
        r = calcular_score_crm(ctx)
        assert 0 <= r.score <= 100


# ---------------------------------------------------------------------------
# Compliance OAB — palavras proibidas
# ---------------------------------------------------------------------------

_PALAVRAS_PROIBIDAS = ["vitória", "vitoria", "ganhar", "perder", "probabilidade de"]


def test_compliance_oab_palavras_proibidas_ausentes_no_nivel_e_acao():
    """crm_nivel e fatores não devem conter palavras proibidas."""
    ctx = _ctx()
    resultado = calcular_score_crm(ctx)

    texto_a_verificar = resultado.nivel + " ".join(
        str(v) for fator in resultado.fatores.values() for v in fator.values()
    )
    for palavra in _PALAVRAS_PROIBIDAS:
        assert (
            palavra not in texto_a_verificar.lower()
        ), f"Palavra proibida '{palavra}' encontrada no output do score"
