"""
Testes unitários para CalculadoraAnalytics.

Estratégia:
  - db é um AsyncMock: scalar.side_effect controla retornos em sequência.
  - tendencia_semanal e ranking_clientes usam db.execute mockado.
  - Cobre: dados normais, zero interações, score CRM nulo, em_risco, sem_analise.
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
    """Resumo traz interações, clientes ativos e o score CRM médio da carteira."""
    db = _mock_db()
    # scalar(): _total_interacoes_periodo e clientes_ativos
    db.scalar.side_effect = [150, 20]
    # execute(): média e contagem de clientes com score
    row = _make_row(score_medio=72.4, analisados=18)
    resultado_score = MagicMock()
    resultado_score.one.return_value = row
    db.execute.return_value = resultado_score

    result = await _calc(db).obter_resumo()

    assert result["total_interacoes"] == 150
    assert result["clientes_ativos"] == 20
    assert result["score_crm_medio"] == 72.4
    assert result["clientes_analisados"] == 18


@pytest.mark.asyncio
async def test_obter_resumo_zero_interacoes():
    """Edge case: sem interações e sem nenhum cliente analisado."""
    db = _mock_db()
    db.scalar.side_effect = [0, 0]
    row = _make_row(score_medio=None, analisados=0)
    resultado_score = MagicMock()
    resultado_score.one.return_value = row
    db.execute.return_value = resultado_score

    result = await _calc(db).obter_resumo()

    assert result["total_interacoes"] == 0
    assert result["clientes_ativos"] == 0
    # Sem análise nenhuma o score é None (e não 0) — 0 significaria "péssimo".
    assert result["score_crm_medio"] is None
    assert result["clientes_analisados"] == 0


@pytest.mark.asyncio
async def test_obter_resumo_score_e_arredondado():
    """Média do banco vem com casas demais e é arredondada para 1 decimal."""
    db = _mock_db()
    db.scalar.side_effect = [10, 5]
    row = _make_row(score_medio=Decimal("63.4567"), analisados=3)
    resultado_score = MagicMock()
    resultado_score.one.return_value = row
    db.execute.return_value = resultado_score

    result = await _calc(db).obter_resumo()

    assert result["score_crm_medio"] == 63.5


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
    assert result["percentual_autonomia"] == 60.0  # 60/100 * 100
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
    """Tendência semanal: volume e autonomia por semana."""
    db = _mock_db()
    semana = datetime(2026, 3, 10, tzinfo=UTC)
    rows = [
        _make_row(semana=semana, total_interacoes=40, saidas=30),
        _make_row(semana=semana + timedelta(weeks=1), total_interacoes=20, saidas=20),
    ]
    mock_result = MagicMock()
    mock_result.all.return_value = rows
    db.execute.return_value = mock_result

    result = await _calc(db).tendencia_semanal(semanas=8)

    assert len(result) == 2
    assert result[0]["total_interacoes"] == 40
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
async def test_tendencia_semanal_autonomia_parcial():
    """Semana com metade das mensagens enviadas pela IA → autonomia 50%."""
    db = _mock_db()
    semana = datetime(2026, 3, 10, tzinfo=UTC)
    rows = [_make_row(semana=semana, total_interacoes=10, saidas=5)]
    mock_result = MagicMock()
    mock_result.all.return_value = rows
    db.execute.return_value = mock_result

    result = await _calc(db).tendencia_semanal()

    assert result[0]["autonomia_pct"] == 50.0


# ---------------------------------------------------------------------------
# ranking_clientes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ranking_clientes_em_risco():
    """Cliente classificado pela IA como em_risco entra sinalizado no ranking."""
    db = _mock_db()
    ultimo = datetime.now(UTC) - timedelta(days=45)
    rows = [
        _make_row(
            cliente_id=1,
            nome="Maria",
            crm_score=18,
            crm_nivel="em_risco",
            total_interacoes=5,
            ultimo_contato=ultimo,
        )
    ]
    mock_result = MagicMock()
    mock_result.all.return_value = rows
    db.execute.return_value = mock_result

    result = await _calc(db).ranking_clientes()

    assert result[0]["em_risco"] is True
    assert result[0]["sem_analise"] is False
    assert result[0]["crm_score"] == 18
    assert result[0]["crm_nivel"] == "em_risco"


@pytest.mark.asyncio
async def test_ranking_clientes_sem_analise():
    """Cliente que a IA ainda não classificou → sem_analise=True, em_risco=False."""
    db = _mock_db()
    ultimo = datetime.now(UTC) - timedelta(days=45)
    rows = [
        _make_row(
            cliente_id=2,
            nome="João",
            crm_score=None,
            crm_nivel=None,
            total_interacoes=3,
            ultimo_contato=ultimo,
        )
    ]
    mock_result = MagicMock()
    mock_result.all.return_value = rows
    db.execute.return_value = mock_result

    result = await _calc(db).ranking_clientes()

    assert result[0]["sem_analise"] is True
    assert result[0]["em_risco"] is False
    assert result[0]["crm_score"] is None


@pytest.mark.asyncio
async def test_ranking_clientes_score_baixo_mas_nivel_saudavel():
    """Score baixo não basta: o sinal de risco vem do nível classificado pela IA."""
    db = _mock_db()
    ultimo = datetime.now(UTC) - timedelta(days=5)
    rows = [
        _make_row(
            cliente_id=3,
            nome="Ana",
            crm_score=35,
            crm_nivel="neutro",
            total_interacoes=8,
            ultimo_contato=ultimo,
        )
    ]
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
    # obter_resumo faz 2 scalar() (total de interações e clientes ativos);
    # o score CRM médio vem de um execute() separado.
    db.scalar.side_effect = [50, 10]
    resultado_score = MagicMock()
    resultado_score.one.return_value = _make_row(score_medio=70.0, analisados=4)
    db.execute.return_value = resultado_score

    await _calc(db).obter_resumo()
    assert db.scalar.call_count == 2

    db.scalar.reset_mock()
    # obter_eficiencia: 4 scalars (tempo, total, ia, custo)
    db.scalar.side_effect = [800, 50, 35, Decimal("0.10")]
    await _calc(db).obter_eficiencia()
    assert db.scalar.call_count == 4
