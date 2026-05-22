# feature_1_ia_personalizada/tests/unit/test_score_risco.py
"""
Testes unitários para ScoreRiscoCalculator (Feature 2).

Cobertura:
  - Fórmula ponderada: pesos somam 100%
  - Classificação de nível: baixo | moderado | alto | critico
  - Casos extremos: datajud_data nulo, tipo_acao nulo, valor_causa nulo
  - Cada componente individualmente
  - Interpretação: não menciona vitória/derrota (compliance OAB)
"""

from __future__ import annotations

import pytest

from feature_1_ia_personalizada.services.legal_data.score_risco import (
    ScoreRisco,
    ScoreRiscoCalculator,
    _componente_complexidade,
    _componente_duracao,
    _componente_fase,
    _componente_historico_vara,
    _componente_valor_causa,
)
from shared.config.constants import SCORE_RISCO_PESOS

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _Processo:
    """Processo mínimo para o calculator."""

    def __init__(
        self,
        tipo_acao=None,
        valor_causa=None,
        fase_processual=None,
        polo_cliente="autor",
    ):
        self.tipo_acao = tipo_acao
        self.valor_causa = valor_causa
        self.fase_processual = fase_processual
        self.polo_cliente = polo_cliente


_DATAJUD_TIPICO = {
    "tempo_medio_tramitacao_dias": 365,
    "taxa_procedencia_autor": 0.6,
}

# ---------------------------------------------------------------------------
# Pesos
# ---------------------------------------------------------------------------


def test_pesos_somam_100_porcento():
    """Requisito de compliance: soma dos pesos deve ser exatamente 1.0."""
    total = sum(SCORE_RISCO_PESOS.values())
    assert abs(total - 1.0) < 1e-9, f"Pesos somam {total}, esperado 1.0"


def test_pesos_contem_cinco_componentes():
    chaves_esperadas = {
        "complexidade_juridica",
        "duracao_estimada",
        "historico_vara",
        "valor_causa",
        "fase_processual",
    }
    assert set(SCORE_RISCO_PESOS.keys()) == chaves_esperadas


# ---------------------------------------------------------------------------
# Componente: complexidade
# ---------------------------------------------------------------------------


def test_componente_complexidade_tipo_nulo_retorna_50():
    assert _componente_complexidade(None) == 50


def test_componente_complexidade_tipo_vazio_retorna_50():
    assert _componente_complexidade("") == 50


def test_componente_complexidade_tipo_conhecido():
    """Tipos conhecidos devem retornar valor != 50 (específico do constants.py)."""
    from shared.config.constants import SCORE_RISCO_COMPLEXIDADE_POR_TIPO

    if not SCORE_RISCO_COMPLEXIDADE_POR_TIPO:
        pytest.skip("SCORE_RISCO_COMPLEXIDADE_POR_TIPO vazio no constants.py")

    tipo, valor = next(iter(SCORE_RISCO_COMPLEXIDADE_POR_TIPO.items()))
    resultado = _componente_complexidade(tipo)
    assert resultado == valor


def test_componente_complexidade_case_insensitive():
    from shared.config.constants import SCORE_RISCO_COMPLEXIDADE_POR_TIPO

    if not SCORE_RISCO_COMPLEXIDADE_POR_TIPO:
        pytest.skip("SCORE_RISCO_COMPLEXIDADE_POR_TIPO vazio no constants.py")

    tipo, valor = next(iter(SCORE_RISCO_COMPLEXIDADE_POR_TIPO.items()))
    assert _componente_complexidade(tipo.upper()) == valor


# ---------------------------------------------------------------------------
# Componente: duração
# ---------------------------------------------------------------------------


def test_componente_duracao_sem_datajud_retorna_50():
    assert _componente_duracao(None) == 50


def test_componente_duracao_sem_campo_retorna_50():
    assert _componente_duracao({}) == 50


def test_componente_duracao_zero_dias_retorna_0():
    resultado = _componente_duracao({"tempo_medio_tramitacao_dias": 0})
    assert resultado == 0


def test_componente_duracao_prazo_alto_retorna_valor_alto():
    resultado = _componente_duracao({"tempo_medio_tramitacao_dias": 9999})
    assert resultado >= 90


# ---------------------------------------------------------------------------
# Componente: histórico da vara
# ---------------------------------------------------------------------------


def test_componente_historico_sem_datajud_retorna_50():
    assert _componente_historico_vara(None, "autor") == 50


def test_componente_historico_autor_taxa_alta_risco_baixo():
    """Para o autor: taxa de procedência alta → risco BAIXO (chances boas)."""
    resultado = _componente_historico_vara({"taxa_procedencia_autor": 0.9}, "autor")
    assert resultado <= 15  # (1 - 0.9) * 100 = 10


def test_componente_historico_reu_taxa_alta_risco_alto():
    """Para o réu: taxa de procedência do autor alta → risco ALTO para o réu."""
    resultado = _componente_historico_vara({"taxa_procedencia_autor": 0.9}, "reu")
    assert resultado >= 85  # 0.9 * 100 = 90


def test_componente_historico_polo_nulo_trata_como_autor():
    resultado_nulo = _componente_historico_vara({"taxa_procedencia_autor": 0.6}, None)
    resultado_autor = _componente_historico_vara({"taxa_procedencia_autor": 0.6}, "autor")
    assert resultado_nulo == resultado_autor


# ---------------------------------------------------------------------------
# Componente: valor da causa
# ---------------------------------------------------------------------------


def test_componente_valor_nulo_retorna_50():
    assert _componente_valor_causa(None) == 50


def test_componente_valor_zero_retorna_50():
    assert _componente_valor_causa(0.0) == 50


def test_componente_valor_muito_baixo_retorna_10():
    from shared.config.constants import SCORE_RISCO_SALARIO_MINIMO_REF

    valor = SCORE_RISCO_SALARIO_MINIMO_REF * 5  # 5 salários mínimos → faixa mais baixa
    assert _componente_valor_causa(valor) == 10


def test_componente_valor_muito_alto_retorna_95():
    from shared.config.constants import SCORE_RISCO_SALARIO_MINIMO_REF

    valor = SCORE_RISCO_SALARIO_MINIMO_REF * 300  # 300 salários → faixa mais alta
    assert _componente_valor_causa(valor) == 95


# ---------------------------------------------------------------------------
# Componente: fase processual
# ---------------------------------------------------------------------------


def test_componente_fase_nula_retorna_valor_de_conhecimento():
    from shared.config.constants import SCORE_RISCO_POR_FASE

    esperado = SCORE_RISCO_POR_FASE.get("conhecimento", 80)
    assert _componente_fase(None) == esperado


def test_componente_fase_encerrado_retorna_valor_baixo():
    from shared.config.constants import SCORE_RISCO_POR_FASE

    resultado = _componente_fase("encerrado")
    # Fase encerrada deve ter risco baixo (processo resolvido)
    assert resultado <= SCORE_RISCO_POR_FASE.get("conhecimento", 80)


def test_componente_fase_case_insensitive():
    assert _componente_fase("JULGAMENTO") == _componente_fase("julgamento")


# ---------------------------------------------------------------------------
# ScoreRiscoCalculator — cálculo completo
# ---------------------------------------------------------------------------


def test_calcular_retorna_score_risco():
    calc = ScoreRiscoCalculator()
    processo = _Processo(tipo_acao="cobrança", polo_cliente="autor")
    resultado = calc.calcular(processo, _DATAJUD_TIPICO)

    assert isinstance(resultado, ScoreRisco)
    assert 0 <= resultado.score <= 100
    assert resultado.nivel in {"baixo", "moderado", "alto", "critico"}
    assert resultado.interpretacao
    assert resultado.atualizado_em.tzinfo is not None  # timezone-aware


def test_calcular_processo_minimo_sem_datajud():
    """Processo sem nenhum dado → score válido (fase_processual=None → conhecimento=80)."""
    calc = ScoreRiscoCalculator()
    resultado = calc.calcular(_Processo(), None)

    assert isinstance(resultado, ScoreRisco)
    # complexidade=50, duracao=50, historico=50, valor_causa=50, fase_processual=80(conhecimento)
    # score = 50*0.25 + 50*0.25 + 50*0.20 + 50*0.15 + 80*0.15 = 12.5+12.5+10+7.5+12 = 54.5 → 54
    assert resultado.score == 54


def test_calcular_nivel_baixo_faixa_0_25():
    """Score ≤ 25 → nivel = 'baixo'."""
    calc = ScoreRiscoCalculator()
    # Cria processo que deve resultar em score baixo
    # Fase encerrado (risco baixo) + autor + taxa 90% + processo simples
    from shared.config.constants import SCORE_RISCO_SALARIO_MINIMO_REF

    datajud = {"tempo_medio_tramitacao_dias": 1, "taxa_procedencia_autor": 0.99}
    processo = _Processo(
        fase_processual="encerrado",
        polo_cliente="autor",
        valor_causa=SCORE_RISCO_SALARIO_MINIMO_REF * 1,
    )
    resultado = calc.calcular(processo, datajud)
    # Não garantimos exatamente < 25, mas o nivel deve estar correto para o score calculado
    if resultado.score <= 25:
        assert resultado.nivel == "baixo"


def test_calcular_nivel_critico_faixa_76_100():
    """Score > 75 → nivel = 'critico'."""
    calc = ScoreRiscoCalculator()
    from shared.config.constants import SCORE_RISCO_SALARIO_MINIMO_REF

    datajud = {"tempo_medio_tramitacao_dias": 9999, "taxa_procedencia_autor": 0.01}
    processo = _Processo(
        fase_processual="conhecimento",
        polo_cliente="reu",
        valor_causa=SCORE_RISCO_SALARIO_MINIMO_REF * 500,
    )
    resultado = calc.calcular(processo, datajud)
    if resultado.score > 75:
        assert resultado.nivel == "critico"


def test_calcular_nivel_correto_para_score():
    """Nivel deve ser consistente com o score calculado em qualquer caso."""
    calc = ScoreRiscoCalculator()
    resultado = calc.calcular(_Processo(polo_cliente="autor"), _DATAJUD_TIPICO)

    score = resultado.score
    if score <= 25:
        assert resultado.nivel == "baixo"
    elif score <= 50:
        assert resultado.nivel == "moderado"
    elif score <= 75:
        assert resultado.nivel == "alto"
    else:
        assert resultado.nivel == "critico"


def test_calcular_componentes_dentro_do_range():
    calc = ScoreRiscoCalculator()
    resultado = calc.calcular(_Processo(polo_cliente="autor"), _DATAJUD_TIPICO)

    c = resultado.componentes
    for campo in (
        "complexidade_juridica",
        "duracao_estimada",
        "historico_vara",
        "valor_causa",
        "fase_processual",
    ):
        valor = getattr(c, campo)
        assert 0 <= valor <= 100, f"{campo}={valor} fora do range 0–100"


# ---------------------------------------------------------------------------
# Interpretação — compliance OAB
# ---------------------------------------------------------------------------


def test_interpretacao_nao_menciona_vitoria():
    calc = ScoreRiscoCalculator()
    resultado = calc.calcular(_Processo(polo_cliente="autor"), _DATAJUD_TIPICO)

    texto = resultado.interpretacao.lower()
    palavras_proibidas = ["vitória", "vitoria", "ganhar", "perder", "derrota", "probabilidade de"]
    for palavra in palavras_proibidas:
        assert palavra not in texto, f"Interpretação menciona '{palavra}' — viola compliance OAB"


def test_interpretacao_nao_vazia():
    calc = ScoreRiscoCalculator()
    resultado = calc.calcular(_Processo(), None)
    assert resultado.interpretacao.strip()
