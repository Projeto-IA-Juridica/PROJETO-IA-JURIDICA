"""
Testes unitários para CalculadoraAnalytics.

Estratégia:
  - db é um AsyncMock: scalar.side_effect controla retornos em sequência.
  - tendencia_semanal e ranking_clientes usam db.execute mockado.
  - Cobre: dados normais, zero interações, NPS nulo, em_risco, sem_avaliacao.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from feature_1_ia_personalizada.services.analytics.calculadora import CalculadoraAnalytics


def _mock_db() -> AsyncMock:
    return AsyncMock()


def _calc(db: AsyncMock, dias: int = 30) -> CalculadoraAnalytics:
    return CalculadoraAnalytics(db, escritorio_id=1, dias=dias)


def _make_row(**kwargs):
    """Cria um row-like object com atributos nomeados."""
    row = MagicMock()
    for k, v in kwargs.items():
        setattr(row, k, v)
    return row


# ---------------------------------------------------------------------------
# obter_resumo
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_obter_resumo_com_dados():
    """Resumo calculado corretamente com dados reais."""
    db = _mock_db()
    # Ordem: _total_interacoes_periodo, clientes_ativos, nps_medio, nps_anterior
    db.scalar.side_effect = [150, 20, 4.2, 3.8]

    result = await _calc(db).obter_resumo()

    assert result["total_interacoes"] == 150
    assert result["clientes_ativos"] == 20
    assert result["nps_medio"] == 4.2
    assert result["nps_anterior"] == 3.8
    assert result["variacao_nps"] == "+0.4"


@pytest.mark.asyncio
async def test_obter_resumo_zero_interacoes():
    """Edge case: sem interações no período."""
    db = _mock_db()
    db.scalar.side_effect = [0, 0, None, None]

    result = await _calc(db).obter_resumo()

    assert result["total_interacoes"] == 0
    assert result["clientes_ativos"] == 0
    assert result["nps_medio"] == 0.0
    assert result["nps_anterior"] == 0.0
    assert result["variacao_nps"] == "+0.0"


@pytest.mark.asyncio
async def test_obter_resumo_variacao_negativa():
    """Variação NPS negativa formatada com sinal de menos."""
    db = _mock_db()
    db.scalar.side_effect = [10, 5, 3.0, 4.5]

    result = await _calc(db).obter_resumo()

    assert result["nps_medio"] == 3.0
    assert result["nps_anterior"] == 4.5
    assert result["variacao_nps"] == "-1.5"


@pytest.mark.asyncio
async def test_obter_resumo_nps_atual_com_anterior_nulo():
    """NPS anterior nulo (sem dados no período anterior) → variacao positiva a partir de zero."""
    db = _mock_db()
    db.scalar.side_effect = [30, 8, 4.0, None]

    result = await _calc(db).obter_resumo()

    assert result["nps_medio"] == 4.0
    assert result["nps_anterior"] == 0.0
    assert result["variacao_nps"] == "+4.0"


# ---------------------------------------------------------------------------
# obter_eficiencia
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_obter_eficiencia_com_dados():
    """Eficiência calculada corretamente."""
    db = _mock_db()
    # Ordem: tempo_resposta, _total_interacoes_periodo, interacoes_sem_humano, custo
    db.scalar.side_effect = [1500, 100, 60, Decimal("0.42")]

    result = await _calc(db).obter_eficiencia()

    assert result["tempo_resposta_medio_ms"] == 1500
    assert result["interacoes_sem_humano"] == 60
    assert result["percentual_autonomia"] == 60.0   # 60/100 * 100
    assert result["horas_economizadas_estimadas"] == 8.0  # 60 * 8min / 60
    assert result["custo_total_usd"] == 0.42


@pytest.mark.asyncio
async def test_obter_eficiencia_zero_interacoes():
    """Edge case: nenhuma interação → autonomia 0%, sem divisão por zero."""
    db = _mock_db()
    db.scalar.side_effect = [None, 0, 0, None]

    result = await _calc(db).obter_eficiencia()

    assert result["percentual_autonomia"] == 0.0
    assert result["horas_economizadas_estimadas"] == 0.0
    assert result["custo_total_usd"] == 0.0


# ---------------------------------------------------------------------------
# tendencia_semanal
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tendencia_semanal_com_dados():
    """Tendência semanal: autonomia e NPS calculados por semana."""
    db = _mock_db()
    semana = datetime(2026, 3, 10, tzinfo=UTC)
    rows = [
        _make_row(semana=semana, total_interacoes=40, nps_medio=4.0, saidas=30),
        _make_row(semana=semana + timedelta(weeks=1), total_interacoes=20, nps_medio=3.5, saidas=20),
    ]
    mock_result = MagicMock()
    mock_result.all.return_value = rows
    db.execute.return_value = mock_result

    result = await _calc(db).tendencia_semanal(semanas=8)

    assert len(result) == 2
    assert result[0]["total_interacoes"] == 40
    assert result[0]["nps_medio"] == 4.0
    assert result[0]["autonomia_pct"] == 75.0  # 30/40 * 100
    assert result[1]["autonomia_pct"] == 100.0  # 20/20 * 100


@pytest.mark.asyncio
async def test_tendencia_semanal_sem_dados():
    """Tendência semanal vazia quando não há interações."""
    db = _mock_db()
    mock_result = MagicMock()
    mock_result.all.return_value = []
    db.execute.return_value = mock_result

    result = await _calc(db).tendencia_semanal()

    assert result == []


@pytest.mark.asyncio
async def test_tendencia_semanal_nps_nulo():
    """Semana sem nenhum NPS respondido → nps_medio = 0.0."""
    db = _mock_db()
    semana = datetime(2026, 3, 10, tzinfo=UTC)
    rows = [_make_row(semana=semana, total_interacoes=10, nps_medio=None, saidas=5)]
    mock_result = MagicMock()
    mock_result.all.return_value = rows
    db.execute.return_value = mock_result

    result = await _calc(db).tendencia_semanal()

    assert result[0]["nps_medio"] == 0.0


# ---------------------------------------------------------------------------
# ranking_clientes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ranking_clientes_em_risco():
    """Cliente com NPS ≤ 3 e sem contato recente → em_risco=True, sem_avaliacao=False."""
    db = _mock_db()
    ultimo = datetime.now(UTC) - timedelta(days=45)
    rows = [_make_row(cliente_id=1, nome="Maria", nps_medio=2.0, total_interacoes=5, ultimo_contato=ultimo)]
    mock_result = MagicMock()
    mock_result.all.return_value = rows
    db.execute.return_value = mock_result

    result = await _calc(db).ranking_clientes()

    assert result[0]["em_risco"] is True
    assert result[0]["sem_avaliacao"] is False
    assert result[0]["nps_medio"] == 2.0


@pytest.mark.asyncio
async def test_ranking_clientes_sem_avaliacao():
    """Cliente sem nenhum NPS respondido → sem_avaliacao=True, em_risco=False."""
    db = _mock_db()
    ultimo = datetime.now(UTC) - timedelta(days=45)
    rows = [_make_row(cliente_id=2, nome="João", nps_medio=None, total_interacoes=3, ultimo_contato=ultimo)]
    mock_result = MagicMock()
    mock_result.all.return_value = rows
    db.execute.return_value = mock_result

    result = await _calc(db).ranking_clientes()

    assert result[0]["sem_avaliacao"] is True
    assert result[0]["em_risco"] is False
    assert result[0]["nps_medio"] is None


@pytest.mark.asyncio
async def test_ranking_clientes_nps_baixo_mas_contato_recente():
    """NPS baixo mas com contato recente → não é em_risco."""
    db = _mock_db()
    ultimo = datetime.now(UTC) - timedelta(days=5)  # contato recente
    rows = [_make_row(cliente_id=3, nome="Ana", nps_medio=2.0, total_interacoes=8, ultimo_contato=ultimo)]
    mock_result = MagicMock()
    mock_result.all.return_value = rows
    db.execute.return_value = mock_result

    result = await _calc(db).ranking_clientes()

    assert result[0]["em_risco"] is False


@pytest.mark.asyncio
async def test_ranking_clientes_vazio():
    """Sem interações no período → lista vazia."""
    db = _mock_db()
    mock_result = MagicMock()
    mock_result.all.return_value = []
    db.execute.return_value = mock_result

    result = await _calc(db).ranking_clientes()

    assert result == []


# ---------------------------------------------------------------------------
# _total_interacoes_periodo (reutilização interna)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_total_interacoes_periodo_reutilizado():
    """
    Valida que obter_resumo e obter_eficiencia não duplicam a mesma query:
    ambos usam _total_interacoes_periodo e scalar é chamado o número exato de vezes.
    """
    db = _mock_db()
    # obter_resumo: 4 scalars (total, clientes, nps_atual, nps_anterior)
    db.scalar.side_effect = [50, 10, 4.0, 3.5]
    await _calc(db).obter_resumo()
    assert db.scalar.call_count == 4

    db.scalar.reset_mock()
    # obter_eficiencia: 4 scalars (tempo, total, ia, custo)
    db.scalar.side_effect = [800, 50, 35, Decimal("0.10")]
    await _calc(db).obter_eficiencia()
    assert db.scalar.call_count == 4
