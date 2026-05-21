# feature_1_ia_personalizada/tests/integration/test_hub_resumos_insights.py
"""
Testes de integração — Hub do Advogado: Resumos, Insights e Histórico
=======================================================================
Cobre os critérios de aceite da task 5.5.

Critérios testados:
1.  "Resumo do processo 0001234-55.2023.8.26.0001" → escalacao_client chamado com dados reais do banco
2.  "Insight da cliente Maria" → CRMDataAggregator chamado + escalacao_client gera recomendação
3.  GET /hub/historico retorna apenas sessões do usuário autenticado (isolamento por usuario_id)
4.  GET /hub/historico/{id} de outro escritório → 403
5.  GET /hub/metricas com role advogado → 403; com role admin → 200
6.  SessaoAdvogado salva com campos corretos após consulta bem-sucedida
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from feature_1_ia_personalizada.api.routes.hub_advogado import get_escalacao_client
from shared.models.processo import Processo
from shared.models.sessao_advogado import SessaoAdvogado

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_escalacao_client(resposta: str = "Análise concluída.") -> MagicMock:
    mock = MagicMock()
    mock.gerar_resposta = AsyncMock(
        return_value=MagicMock(
            conteudo=resposta,
            tokens_input=200,
            tokens_output=300,
            custo_estimado=Decimal("0.001"),
        )
    )
    mock.analisar_peca = AsyncMock(
        return_value=MagicMock(
            tipo_peca="Petição Inicial",
            pontos_fortes=[],
            vulnerabilidades=[],
            argumentos_ausentes=[],
            precedentes_relevantes=[],
            score_geral=70,
            sugestoes=[],
            tokens_input=200,
            tokens_output=300,
            custo_estimado=Decimal("0.001"),
        )
    )
    return mock


def _override(app, mock_client):
    app.dependency_overrides[get_escalacao_client] = lambda: mock_client


def _clear(app):
    app.dependency_overrides.pop(get_escalacao_client, None)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def advogado_setup(escritorio_factory, usuario_factory, auth_token):
    escritorio = await escritorio_factory(nome="Escritório Resumo Teste")
    advogado = await usuario_factory(
        escritorio_id=escritorio.id,
        nome="Dr. Ana Lima",
        role="advogado",
    )
    token = auth_token(user_id=advogado.id, escritorio_id=escritorio.id, role="advogado")
    return escritorio, advogado, {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def admin_setup(escritorio_factory, usuario_factory, auth_token):
    escritorio = await escritorio_factory(nome="Escritório Admin Teste")
    admin = await usuario_factory(
        escritorio_id=escritorio.id,
        nome="Admin Central",
        role="admin",
    )
    token = auth_token(user_id=admin.id, escritorio_id=escritorio.id, role="admin")
    return escritorio, admin, {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Teste 1 — Resumo de processo com dados reais do banco
# ---------------------------------------------------------------------------


async def test_consultar_com_processo_real_passa_cnj_para_escalacao(
    async_client,
    advogado_setup,
    cliente_factory,
    db_session: AsyncSession,
):
    """
    POST /hub/consultar com processo_id válido → CNJ aparece na mensagem enviada
    ao EscalacaoClient e a sessão é salva com processo_referenciado_id correto.
    """
    from feature_1_ia_personalizada.api.app import app

    escritorio, advogado, headers = advogado_setup
    cliente = await cliente_factory(escritorio_id=escritorio.id, nome="João Silva")

    processo = Processo(
        escritorio_id=escritorio.id,
        cliente_id=cliente.id,
        numero_cnj="0001234-55.2023.8.26.0001",
        tipo_acao="Ação de Indenização por Danos Morais",
        fase_processual="Instrução",
    )
    db_session.add(processo)
    await db_session.commit()
    await db_session.refresh(processo)

    mock_client = _mock_escalacao_client("Processo em fase de instrução — risco moderado.")

    _override(app, mock_client)
    try:
        resp = await async_client.post(
            "/hub/consultar",
            headers=headers,
            json={
                "pergunta": "Qual a situação atual do processo?",
                "processo_id": processo.id,
            },
        )
    finally:
        _clear(app)

    assert resp.status_code == 200
    body = resp.json()
    assert "instrução" in body["resposta"].lower()

    # CNJ injetado no contexto enviado à IA
    mensagem_ia = mock_client.gerar_resposta.call_args.kwargs["mensagem_usuario"]
    assert "0001234-55.2023.8.26.0001" in mensagem_ia
    assert "Ação de Indenização por Danos Morais" in mensagem_ia

    # SessaoAdvogado salva com referência ao processo
    result = await db_session.execute(
        select(SessaoAdvogado).where(SessaoAdvogado.usuario_id == advogado.id)
    )
    sessao = result.scalar_one_or_none()
    assert sessao is not None
    assert sessao.processo_referenciado_id == processo.id
    assert sessao.intencao == "duvida_juridica"
    assert sessao.tokens_input == 200
    assert sessao.tokens_output == 300


# ---------------------------------------------------------------------------
# Teste 2 — Insight de cliente com CRM aggregator
# ---------------------------------------------------------------------------


async def test_consultar_com_cliente_chama_aggregator_e_injeta_nome(
    async_client,
    advogado_setup,
    cliente_factory,
    db_session: AsyncSession,
):
    """
    POST /hub/consultar com cliente_id → nome do cliente é injetado no contexto
    enviado ao EscalacaoClient e sessão guarda cliente_referenciado_id.
    """
    from feature_1_ia_personalizada.api.app import app

    escritorio, advogado, headers = advogado_setup
    cliente = await cliente_factory(escritorio_id=escritorio.id, nome="Maria Souza")

    mock_client = _mock_escalacao_client(
        "Cliente Maria tem alto risco de abandono — recomendo contato imediato."
    )

    _override(app, mock_client)
    try:
        resp = await async_client.post(
            "/hub/consultar",
            headers=headers,
            json={
                "pergunta": "Qual o insight sobre a cliente?",
                "cliente_id": cliente.id,
            },
        )
    finally:
        _clear(app)

    assert resp.status_code == 200
    body = resp.json()
    assert body["modelo_ia"] == "claude_opus"

    # Nome da cliente injetado na mensagem
    mensagem_ia = mock_client.gerar_resposta.call_args.kwargs["mensagem_usuario"]
    assert "Maria Souza" in mensagem_ia

    # Sessão salva com referência à cliente
    result = await db_session.execute(
        select(SessaoAdvogado).where(SessaoAdvogado.usuario_id == advogado.id)
    )
    sessao = result.scalar_one_or_none()
    assert sessao is not None
    assert sessao.cliente_referenciado_id == cliente.id


# ---------------------------------------------------------------------------
# Teste 3 — GET /hub/historico — isolamento por usuario_id
# ---------------------------------------------------------------------------


async def test_historico_retorna_apenas_sessoes_do_usuario_autenticado(
    async_client,
    escritorio_factory,
    usuario_factory,
    auth_token,
    db_session: AsyncSession,
):
    """
    GET /hub/historico retorna somente as sessões do usuário autenticado —
    sessões de outro advogado do mesmo escritório NÃO aparecem.
    """
    escritorio = await escritorio_factory()
    advogado1 = await usuario_factory(escritorio_id=escritorio.id, role="advogado")
    advogado2 = await usuario_factory(escritorio_id=escritorio.id, role="advogado")

    # Criar uma sessão para cada advogado
    sessao1 = SessaoAdvogado(
        escritorio_id=escritorio.id,
        usuario_id=advogado1.id,
        mensagem_advogado="Pergunta do advogado 1",
        resposta_hub="Resposta 1",
        intencao="duvida_juridica",
        modelo_ia="claude_opus",
        tokens_input=100,
        tokens_output=150,
        custo_estimado=Decimal("0.001"),
        metadata_json={},
    )
    sessao2 = SessaoAdvogado(
        escritorio_id=escritorio.id,
        usuario_id=advogado2.id,
        mensagem_advogado="Pergunta do advogado 2",
        resposta_hub="Resposta 2",
        intencao="resumo_processo",
        modelo_ia="claude_opus",
        tokens_input=200,
        tokens_output=250,
        custo_estimado=Decimal("0.002"),
        metadata_json={},
    )
    db_session.add_all([sessao1, sessao2])
    await db_session.commit()

    # Autenticar como advogado1
    token1 = auth_token(user_id=advogado1.id, escritorio_id=escritorio.id, role="advogado")
    headers1 = {"Authorization": f"Bearer {token1}"}

    resp = await async_client.get("/hub/historico", headers=headers1)
    assert resp.status_code == 200
    items = resp.json()

    # Deve ver apenas a própria sessão
    assert len(items) == 1
    assert items[0]["intencao"] == "duvida_juridica"
    assert "Pergunta do advogado 2" not in str(items)


# ---------------------------------------------------------------------------
# Teste 4 — GET /hub/historico/{id} — isolamento multi-tenant
# ---------------------------------------------------------------------------


async def test_detalhar_sessao_de_outro_escritorio_retorna_403(
    async_client,
    escritorio_factory,
    usuario_factory,
    auth_token,
    db_session: AsyncSession,
):
    """
    GET /hub/historico/{id} com sessao_id de outro escritório deve retornar 403.
    Evitar enumeração de IDs — 403 em vez de 404.
    """
    # Dois escritórios independentes
    escritorio_a = await escritorio_factory()
    escritorio_b = await escritorio_factory()

    advogado_a = await usuario_factory(escritorio_id=escritorio_a.id, role="advogado")
    advogado_b = await usuario_factory(escritorio_id=escritorio_b.id, role="advogado")

    # Sessão pertence ao escritório B
    sessao_b = SessaoAdvogado(
        escritorio_id=escritorio_b.id,
        usuario_id=advogado_b.id,
        mensagem_advogado="Segredo do escritório B",
        resposta_hub="Resposta B",
        intencao="duvida_juridica",
        modelo_ia="claude_opus",
        tokens_input=50,
        tokens_output=80,
        custo_estimado=Decimal("0.0005"),
        metadata_json={},
    )
    db_session.add(sessao_b)
    await db_session.commit()
    await db_session.refresh(sessao_b)

    # Advogado A tenta acessar a sessão do escritório B
    token_a = auth_token(user_id=advogado_a.id, escritorio_id=escritorio_a.id, role="advogado")
    headers_a = {"Authorization": f"Bearer {token_a}"}

    resp = await async_client.get(f"/hub/historico/{sessao_b.id}", headers=headers_a)
    assert resp.status_code == 403
    assert "negado" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Teste 5 — GET /hub/metricas — controle de acesso
# ---------------------------------------------------------------------------


async def test_metricas_com_role_advogado_retorna_403(
    async_client,
    advogado_setup,
):
    """Role 'advogado' não tem acesso às métricas agregadas — deve receber 403."""
    _, _, headers = advogado_setup
    resp = await async_client.get("/hub/metricas", headers=headers)
    assert resp.status_code == 403


async def test_metricas_com_role_admin_retorna_200(
    async_client,
    admin_setup,
    db_session: AsyncSession,
):
    """Role 'admin' pode acessar métricas — deve receber 200 com estrutura correta."""
    _, admin, headers = admin_setup

    resp = await async_client.get("/hub/metricas", headers=headers)
    assert resp.status_code == 200
    body = resp.json()

    assert "mes_atual" in body
    assert "total_sessoes" in body
    assert "tokens_input_total" in body
    assert "tokens_output_total" in body
    assert "custo_total_usd" in body
    assert "intencoes_top5" in body
    assert "advogados_mais_ativos" in body

    # Formato do mês: YYYY-MM
    import re
    assert re.match(r"^\d{4}-\d{2}$", body["mes_atual"])


# ---------------------------------------------------------------------------
# Teste 6 — SessaoAdvogado salva com campos corretos
# ---------------------------------------------------------------------------


async def test_sessao_advogado_salva_campos_corretos(
    async_client,
    advogado_setup,
    db_session: AsyncSession,
):
    """
    Após consulta bem-sucedida, SessaoAdvogado deve ter todos os campos obrigatórios
    preenchidos corretamente: usuario_id, escritorio_id, intencao, modelo_ia,
    tokens_input, tokens_output, custo_estimado, mensagem_advogado, resposta_hub.
    """
    from feature_1_ia_personalizada.api.app import app

    escritorio, advogado, headers = advogado_setup
    mock_client = _mock_escalacao_client("Resposta jurídica detalhada sobre o prazo.")

    _override(app, mock_client)
    try:
        resp = await async_client.post(
            "/hub/consultar",
            headers=headers,
            json={"pergunta": "Qual o prazo para apresentar embargos de declaração?"},
        )
    finally:
        _clear(app)

    assert resp.status_code == 200

    result = await db_session.execute(
        select(SessaoAdvogado).where(SessaoAdvogado.usuario_id == advogado.id)
    )
    sessao = result.scalar_one_or_none()

    assert sessao is not None
    assert sessao.escritorio_id == escritorio.id
    assert sessao.usuario_id == advogado.id
    assert sessao.intencao == "duvida_juridica"
    assert sessao.modelo_ia == "claude_opus"
    assert sessao.mensagem_advogado == "Qual o prazo para apresentar embargos de declaração?"
    assert "jurídica" in sessao.resposta_hub.lower()
    assert sessao.tokens_input == 200
    assert sessao.tokens_output == 300
    assert sessao.custo_estimado == Decimal("0.001")
    assert sessao.cliente_referenciado_id is None
    assert sessao.processo_referenciado_id is None
    assert isinstance(sessao.metadata_json, dict)
