# feature_1_ia_personalizada/tests/unit/test_crm_analyzer.py
"""
Testes unitários para CRMAnalyzer (Feature 7).

O analyzer passou a delegar a CLASSIFICAÇÃO do relacionamento ao Claude
(nível + score 0-100 a partir da conversa recente) — antes o score era
determinístico e o Claude só escrevia o resumo.

Cobertura:
  - Cache hit: não chama Claude quando a análise é recente e não houve
    interação nova depois dela
  - Cache invalidado: análise antiga, incompleta, ou com contato posterior
  - Classificação parseada corretamente (inclusive com cerca de markdown)
  - Normalização: score é forçado para dentro da faixa do nível
  - Nível inválido e falha do Claude → RuntimeError, sem persistir nada
  - Compliance OAB: palavras proibidas bloqueiam a persistência
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from feature_1_ia_personalizada.services.crm.aggregator import CRMContexto, UltimaMensagem
from feature_1_ia_personalizada.services.crm.analyzer import (
    CRMAnalyzer,
    _normalizar_classificacao,
    _validar_output,
)

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
        "total_interacoes_30d": 8,
        "total_interacoes_90d": 20,
        "dias_desde_ultimo_contato": 5,
        "ultimo_contato_at": datetime.now(UTC) - timedelta(days=5),
        "processos_ativos": [],
        "pior_score_risco": None,
        "escalacoes_pendentes": 0,
        "escalacoes_rejeitadas_30d": 0,
        "crm_nivel_anterior": None,
        "crm_score_anterior": None,
        "crm_analisado_em_anterior": None,
        "crm_resumo_anterior": None,
        "crm_acao_sugerida_anterior": None,
        "ultimas_mensagens": [
            UltimaMensagem(
                pergunta_cliente="Como está meu processo?",
                resposta_ia="Está na fase de instrução.",
                data=datetime.now(UTC) - timedelta(days=5),
            )
        ],
    }
    defaults.update(kwargs)
    return CRMContexto(**defaults)


def _mock_resposta(payload: str, tokens_in: int = 100, tokens_out: int = 50) -> MagicMock:
    msg = MagicMock()
    msg.content = [MagicMock(text=payload)]
    msg.usage = MagicMock(input_tokens=tokens_in, output_tokens=tokens_out)
    return msg


def _make_analyzer(resposta: MagicMock | None = None, db=None) -> tuple[CRMAnalyzer, MagicMock]:
    claude = MagicMock()
    claude._client = AsyncMock()
    if resposta is not None:
        claude._client.messages.create = AsyncMock(return_value=resposta)
    return CRMAnalyzer(claude_client=claude, db=db or AsyncMock()), claude


def _patch_contexto(ctx: CRMContexto):
    p = patch("feature_1_ia_personalizada.services.crm.analyzer.CRMDataAggregator")
    mock = p.start()
    mock.return_value.coletar_contexto_cliente = AsyncMock(return_value=ctx)
    return p


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_hit_nao_chama_claude():
    """Análise recente e sem contato posterior: reaproveita sem chamar o modelo."""
    agora = datetime.now(UTC)
    ctx = _ctx_base(
        crm_nivel_anterior="satisfeito",
        crm_score_anterior=68,
        crm_analisado_em_anterior=agora - timedelta(hours=1),
        crm_resumo_anterior="Cliente acompanha o processo de perto.",
        crm_acao_sugerida_anterior="Enviar atualização mensal",
        ultimo_contato_at=agora - timedelta(hours=3),  # anterior à análise
    )
    analyzer, claude = _make_analyzer()

    p = _patch_contexto(ctx)
    try:
        result = await analyzer.analisar_cliente(1, 1)
    finally:
        p.stop()

    assert result.cache_hit is True
    assert result.nivel == "satisfeito"
    assert result.score == 68
    assert result.resumo == "Cliente acompanha o processo de perto."
    assert result.tokens_input == 0
    claude._client.messages.create.assert_not_called()


@pytest.mark.asyncio
async def test_cache_expirado_chama_claude():
    """Análise com mais de 24h é refeita."""
    agora = datetime.now(UTC)
    ctx = _ctx_base(
        crm_nivel_anterior="satisfeito",
        crm_score_anterior=68,
        crm_analisado_em_anterior=agora - timedelta(hours=25),
        crm_resumo_anterior="Resumo antigo.",
        ultimo_contato_at=agora - timedelta(hours=30),
    )
    payload = json.dumps(
        {"nivel": "excelente", "score": 88, "resumo": "Muito satisfeito.", "acao_sugerida": "Nada"}
    )
    analyzer, claude = _make_analyzer(_mock_resposta(payload))

    p = _patch_contexto(ctx)
    try:
        result = await analyzer.analisar_cliente(1, 1)
    finally:
        p.stop()

    assert result.cache_hit is False
    assert result.nivel == "excelente"
    assert result.score == 88
    claude._client.messages.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_contato_novo_apos_analise_invalida_cache():
    """Houve conversa depois da última análise: precisa reclassificar."""
    agora = datetime.now(UTC)
    ctx = _ctx_base(
        crm_nivel_anterior="neutro",
        crm_score_anterior=40,
        crm_analisado_em_anterior=agora - timedelta(hours=2),
        crm_resumo_anterior="Resumo de duas horas atrás.",
        ultimo_contato_at=agora - timedelta(minutes=10),  # posterior à análise
    )
    payload = json.dumps(
        {
            "nivel": "em_risco",
            "score": 18,
            "resumo": "Reclamou da demora.",
            "acao_sugerida": "Ligar",
        }
    )
    analyzer, claude = _make_analyzer(_mock_resposta(payload))

    p = _patch_contexto(ctx)
    try:
        result = await analyzer.analisar_cliente(1, 1)
    finally:
        p.stop()

    assert result.cache_hit is False
    assert result.nivel == "em_risco"
    claude._client.messages.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_analise_anterior_incompleta_nao_usa_cache():
    """Sem nível anterior gravado, o cache não é considerado válido."""
    agora = datetime.now(UTC)
    ctx = _ctx_base(
        crm_nivel_anterior=None,
        crm_score_anterior=50,
        crm_analisado_em_anterior=agora - timedelta(minutes=30),
        crm_resumo_anterior="Resumo sem nível.",
        ultimo_contato_at=agora - timedelta(hours=5),
    )
    payload = json.dumps(
        {"nivel": "neutro", "score": 40, "resumo": "Relação morna.", "acao_sugerida": "Check-in"}
    )
    analyzer, claude = _make_analyzer(_mock_resposta(payload))

    p = _patch_contexto(ctx)
    try:
        result = await analyzer.analisar_cliente(1, 1)
    finally:
        p.stop()

    assert result.cache_hit is False
    claude._client.messages.create.assert_awaited_once()


# ---------------------------------------------------------------------------
# Parse e classificação
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_classificacao_completa_e_persistida():
    ctx = _ctx_base()
    payload = json.dumps(
        {
            "nivel": "critico",
            "score": 5,
            "resumo": "Cliente ameaçou trocar de escritório.",
            "acao_sugerida": "Contato imediato do advogado responsável",
        }
    )
    db = AsyncMock()
    analyzer, _ = _make_analyzer(_mock_resposta(payload), db=db)

    p = _patch_contexto(ctx)
    try:
        result = await analyzer.analisar_cliente(1, 1)
    finally:
        p.stop()

    assert (result.nivel, result.score) == ("critico", 5)
    assert result.resumo.startswith("Cliente ameaçou")
    assert result.tokens_input == 100
    assert result.custo > 0
    db.execute.assert_awaited_once()  # UPDATE do cliente
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_json_com_cerca_markdown_e_aceito():
    """O modelo às vezes embrulha o JSON em ```json — não pode quebrar."""
    ctx = _ctx_base()
    payload = (
        '```json\n{"nivel": "satisfeito", "score": 60, '
        '"resumo": "Tudo certo.", "acao_sugerida": "Nada"}\n```'
    )
    analyzer, _ = _make_analyzer(_mock_resposta(payload))

    p = _patch_contexto(ctx)
    try:
        result = await analyzer.analisar_cliente(1, 1)
    finally:
        p.stop()

    assert result.nivel == "satisfeito"
    assert result.score == 60


@pytest.mark.asyncio
async def test_score_fora_da_faixa_e_normalizado():
    """Score incoerente com o nível é puxado para dentro da faixa."""
    ctx = _ctx_base()
    payload = json.dumps(
        {"nivel": "critico", "score": 95, "resumo": "Insatisfeito.", "acao_sugerida": "Ligar"}
    )
    analyzer, _ = _make_analyzer(_mock_resposta(payload))

    p = _patch_contexto(ctx)
    try:
        result = await analyzer.analisar_cliente(1, 1)
    finally:
        p.stop()

    assert result.nivel == "critico"
    assert result.score <= 10  # teto da faixa "critico"


# ---------------------------------------------------------------------------
# Falhas — nada é persistido
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_claude_indisponivel_levanta_e_nao_persiste():
    ctx = _ctx_base()
    db = AsyncMock()
    analyzer, claude = _make_analyzer(db=db)
    claude._client.messages.create = AsyncMock(side_effect=RuntimeError("timeout"))

    p = _patch_contexto(ctx)
    try:
        with pytest.raises(RuntimeError, match="indisponível"):
            await analyzer.analisar_cliente(1, 1)
    finally:
        p.stop()

    db.execute.assert_not_awaited()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_nivel_invalido_levanta_e_nao_persiste():
    ctx = _ctx_base()
    payload = json.dumps({"nivel": "meia_boca", "score": 50, "resumo": "x", "acao_sugerida": "y"})
    db = AsyncMock()
    analyzer, _ = _make_analyzer(_mock_resposta(payload), db=db)

    p = _patch_contexto(ctx)
    try:
        with pytest.raises(RuntimeError):
            await analyzer.analisar_cliente(1, 1)
    finally:
        p.stop()

    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_palavra_proibida_bloqueia_persistencia():
    """Compliance OAB: promessa de resultado não pode ser gravada."""
    ctx = _ctx_base()
    payload = json.dumps(
        {
            "nivel": "satisfeito",
            "score": 60,
            "resumo": "Cliente confiante na vitória do caso.",
            "acao_sugerida": "Manter contato",
        }
    )
    db = AsyncMock()
    analyzer, _ = _make_analyzer(_mock_resposta(payload), db=db)

    p = _patch_contexto(ctx)
    try:
        with pytest.raises(RuntimeError):
            await analyzer.analisar_cliente(1, 1)
    finally:
        p.stop()

    db.commit.assert_not_awaited()


# ---------------------------------------------------------------------------
# Funções puras
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "nivel,score,esperado",
    [
        ("excelente", 90, 90),
        ("excelente", 10, 76),  # abaixo do piso → piso
        ("critico", 50, 10),  # acima do teto → teto
        ("neutro", 40, 40),
    ],
)
def test_normalizar_classificacao_respeita_faixas(nivel, score, esperado):
    assert _normalizar_classificacao({"nivel": nivel, "score": score}) == (nivel, esperado)


def test_normalizar_classificacao_score_ausente_usa_meio_da_faixa():
    nivel, score = _normalizar_classificacao({"nivel": "satisfeito"})
    assert nivel == "satisfeito"
    assert 51 <= score <= 75


def test_normalizar_classificacao_rejeita_nivel_desconhecido():
    with pytest.raises(ValueError, match="Nível inválido"):
        _normalizar_classificacao({"nivel": "otimo", "score": 80})


@pytest.mark.parametrize(
    "resumo,acao",
    [
        ("Cliente busca a vitória", "Nenhuma ação"),
        ("Tudo bem", "Dizer que vamos ganhar"),
        ("Alta probabilidade de êxito", "Nenhuma ação"),
    ],
)
def test_validar_output_rejeita_palavras_proibidas(resumo, acao):
    with pytest.raises(ValueError, match="compliance OAB"):
        _validar_output(resumo, acao)


def test_validar_output_aceita_texto_limpo():
    _validar_output("Cliente satisfeito com o atendimento.", "Enviar atualização mensal.")
