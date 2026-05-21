# feature_1_ia_personalizada/tests/unit/test_crm_analyzer.py
"""
Testes unitários para CRMAnalyzer (Feature 7).

Cobertura:
  - Cache hit: não chama Claude se score não mudou e análise < 24h
  - Graceful degradation: Claude falha → persiste score sem resumo
  - Output do Claude parseado corretamente em CRMAnaliseResult
  - Cliente sem processos: ação sugerida gerada
  - Compliance OAB: palavras proibidas causam erro e não são persistidas
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from feature_1_ia_personalizada.services.crm.aggregator import CRMContexto, NPSRegistro
from feature_1_ia_personalizada.services.crm.analyzer import CRMAnalyzer, _validar_output

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx_base(**kwargs) -> CRMContexto:
    defaults = {
        "cliente_id": 1,
        "escritorio_id": 1,
        "nome": "João Silva",
        "profissao": "Engenheiro",
        "empresa": "Tech Corp",
        "data_nascimento": None,
        "nps_historico": [NPSRegistro(data=datetime.now(UTC), nota=4)],
        "nps_medio_3m": 4.0,
        "total_interacoes_30d": 8,
        "total_interacoes_90d": 20,
        "dias_desde_ultimo_contato": 5,
        "ultimo_contato_at": datetime.now(UTC) - timedelta(days=5),
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


def _make_analyzer(db=None, claude=None) -> CRMAnalyzer:
    if db is None:
        db = AsyncMock()
    if claude is None:
        claude = MagicMock()
        claude._client = AsyncMock()
    return CRMAnalyzer(claude_client=claude, db=db)


# ---------------------------------------------------------------------------
# Cache hit
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cache_hit_nao_chama_claude():
    """Se score igual e análise < 24h, retorna sem chamar Claude."""
    agora = datetime.now(UTC)
    ctx = _ctx_base(
        crm_score_anterior=75,          # será igual ao calculado
        crm_analisado_em_anterior=agora - timedelta(hours=1),
        crm_resumo_anterior="Resumo anterior.",
        crm_acao_sugerida_anterior="Nenhuma ação necessária",
    )

    claude = MagicMock()
    claude._client = AsyncMock()
    analyzer = _make_analyzer(claude=claude)

    with patch(
        "feature_1_ia_personalizada.services.crm.analyzer.CRMDataAggregator"
    ) as MockAgg, patch(
        "feature_1_ia_personalizada.services.crm.analyzer.calcular_score_crm"
    ) as mock_calc:
        MockAgg.return_value.coletar_contexto_cliente = AsyncMock(return_value=ctx)
        mock_score = MagicMock(score=75, nivel="satisfeito", fatores={})
        mock_calc.return_value = mock_score

        result = await analyzer.analisar_cliente(1, 1)

    assert result.cache_hit is True
    assert result.resumo == "Resumo anterior."
    assert result.tokens_input == 0
    claude._client.messages.create.assert_not_called()


@pytest.mark.asyncio
async def test_cache_expirado_chama_claude():
    """Se análise > 24h, deve chamar Claude mesmo com score igual."""
    agora = datetime.now(UTC)
    ctx = _ctx_base(
        crm_score_anterior=75,
        crm_analisado_em_anterior=agora - timedelta(hours=25),  # expirado
        crm_resumo_anterior="Resumo antigo.",
        crm_acao_sugerida_anterior="Ligar",
    )

    resposta_claude = json.dumps({"resumo": "Novo resumo.", "acao_sugerida": "Enviar atualização"})
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=resposta_claude)]
    mock_msg.usage = MagicMock(input_tokens=100, output_tokens=50)

    claude = MagicMock()
    claude._client = AsyncMock()
    claude._client.messages.create = AsyncMock(return_value=mock_msg)

    db = AsyncMock()
    db.execute = AsyncMock(return_value=AsyncMock())
    db.commit = AsyncMock()

    analyzer = CRMAnalyzer(claude_client=claude, db=db)

    with patch(
        "feature_1_ia_personalizada.services.crm.analyzer.CRMDataAggregator"
    ) as MockAgg, patch(
        "feature_1_ia_personalizada.services.crm.analyzer.calcular_score_crm"
    ) as mock_calc:
        MockAgg.return_value.coletar_contexto_cliente = AsyncMock(return_value=ctx)
        mock_calc.return_value = MagicMock(score=75, nivel="satisfeito", fatores={})

        result = await analyzer.analisar_cliente(1, 1)

    assert result.cache_hit is False
    claude._client.messages.create.assert_called_once()


# ---------------------------------------------------------------------------
# Graceful degradation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_claude_falha_persiste_score_sem_resumo():
    """Se Claude lança exceção, persiste score mas crm_resumo fica vazio."""
    ctx = _ctx_base()

    claude = MagicMock()
    claude._client = AsyncMock()
    claude._client.messages.create = AsyncMock(side_effect=RuntimeError("Claude offline"))

    db = AsyncMock()
    db.execute = AsyncMock(return_value=AsyncMock())
    db.commit = AsyncMock()

    analyzer = CRMAnalyzer(claude_client=claude, db=db)

    with patch(
        "feature_1_ia_personalizada.services.crm.analyzer.CRMDataAggregator"
    ) as MockAgg, patch(
        "feature_1_ia_personalizada.services.crm.analyzer.calcular_score_crm"
    ) as mock_calc:
        MockAgg.return_value.coletar_contexto_cliente = AsyncMock(return_value=ctx)
        mock_calc.return_value = MagicMock(score=60, nivel="neutro", fatores={})

        result = await analyzer.analisar_cliente(1, 1)

    # Score determinístico deve estar presente
    assert result.score == 60
    assert result.nivel == "neutro"
    # Sem resumo — Claude falhou
    assert result.resumo == ""
    assert result.tokens_input == 0
    assert result.custo == Decimal("0")
    # UPDATE no banco ainda é chamado (persiste score)
    db.execute.assert_called()
    db.commit.assert_called()


# ---------------------------------------------------------------------------
# Parse do output do Claude
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_output_claude_parseado_corretamente():
    """Resposta JSON do Claude é convertida em CRMAnaliseResult."""
    ctx = _ctx_base()
    payload = {
        "resumo": "Cliente engajado com NPS alto e processos sem alerta.",
        "acao_sugerida": "Nenhuma ação necessária",
    }

    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(payload))]
    mock_msg.usage = MagicMock(input_tokens=200, output_tokens=60)

    claude = MagicMock()
    claude._client = AsyncMock()
    claude._client.messages.create = AsyncMock(return_value=mock_msg)

    db = AsyncMock()
    db.execute = AsyncMock(return_value=AsyncMock())
    db.commit = AsyncMock()

    analyzer = CRMAnalyzer(claude_client=claude, db=db)

    with patch(
        "feature_1_ia_personalizada.services.crm.analyzer.CRMDataAggregator"
    ) as MockAgg, patch(
        "feature_1_ia_personalizada.services.crm.analyzer.calcular_score_crm"
    ) as mock_calc:
        MockAgg.return_value.coletar_contexto_cliente = AsyncMock(return_value=ctx)
        mock_calc.return_value = MagicMock(score=80, nivel="excelente", fatores={})

        result = await analyzer.analisar_cliente(1, 1)

    assert result.resumo == payload["resumo"]
    assert result.acao_sugerida == "Nenhuma ação necessária"
    assert result.tokens_input == 200
    assert result.tokens_output == 60
    assert result.cache_hit is False


# ---------------------------------------------------------------------------
# Cliente sem processos
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cliente_sem_processos_gera_acao_sugerida():
    """Cliente sem processos ativos não deve falhar — ação sugerida deve ser retornada."""
    ctx = _ctx_base(processos_ativos=[], pior_score_risco=None)

    payload = {
        "resumo": "Cliente sem processos ativos no momento.",
        "acao_sugerida": "Verificar necessidade de novo processo ou re-engajar cliente.",
    }
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(payload))]
    mock_msg.usage = MagicMock(input_tokens=150, output_tokens=40)

    claude = MagicMock()
    claude._client = AsyncMock()
    claude._client.messages.create = AsyncMock(return_value=mock_msg)

    db = AsyncMock()
    db.execute = AsyncMock(return_value=AsyncMock())
    db.commit = AsyncMock()

    analyzer = CRMAnalyzer(claude_client=claude, db=db)

    with patch(
        "feature_1_ia_personalizada.services.crm.analyzer.CRMDataAggregator"
    ) as MockAgg, patch(
        "feature_1_ia_personalizada.services.crm.analyzer.calcular_score_crm"
    ) as mock_calc:
        MockAgg.return_value.coletar_contexto_cliente = AsyncMock(return_value=ctx)
        mock_calc.return_value = MagicMock(score=55, nivel="satisfeito", fatores={})

        result = await analyzer.analisar_cliente(1, 1)

    assert result.acao_sugerida != ""
    assert result.nivel == "satisfeito"


# ---------------------------------------------------------------------------
# Compliance OAB
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("resumo,acao", [
    ("Alta probabilidade de vitória no processo.", "Aguardar julgamento"),
    ("Cliente deve ganhar a causa.", "Nenhuma ação necessária"),
    ("Risco de perder o processo aumentou.", "Ligar"),
    ("Probabilidade de sucesso estimada em 80%.", "Enviar atualização"),
])
def test_validar_output_rejeita_palavras_proibidas(resumo, acao):
    with pytest.raises(ValueError, match="compliance OAB"):
        _validar_output(resumo, acao)


def test_validar_output_aceita_texto_limpo():
    """Texto sem palavras proibidas deve passar sem erro."""
    _validar_output(
        "Cliente com NPS alto e bom engajamento nos últimos 30 dias.",
        "Nenhuma ação necessária",
    )
