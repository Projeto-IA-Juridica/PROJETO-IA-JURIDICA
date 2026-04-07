# feature_1_ia_personalizada/tests/integration/test_analise_peticao.py
"""
Testes de integração — Hub do Advogado REST API
================================================
Cobre os critérios de aceite da task 4.3.

Critérios testados:
1.  POST /hub/analisar-peticao com role cliente → 403
2.  POST /hub/analisar-peticao com arquivo sem magic bytes PDF → 422
3.  POST /hub/analisar-peticao com PDF acima de 10 MB → 422
4.  POST /hub/analisar-peticao com falha na extração de texto → 422
5.  POST /hub/analisar-peticao com PDF válido → escalacao chamado + SessaoAdvogado salva
6.  POST /hub/analisar-peticao com texto > 15 000 chars → texto_truncado=True
7.  POST /hub/analisar-peticao com EscalacaoIndisponivelError → 503
8.  POST /hub/consultar → resposta Claude Opus + SessaoAdvogado salva
9.  POST /hub/consultar com cliente_id → contexto injeta nome + sessão guarda referência
10. POST /hub/consultar com processo_id → contexto injeta CNJ + sessão guarda referência
11. POST /hub/consultar com cliente_id de outro escritório → ignorado (multi-tenant)
12. POST /hub/consultar com EscalacaoIndisponivelError → 503
"""

from __future__ import annotations

from decimal import Decimal
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from feature_1_ia_personalizada.api.routes.hub_advogado import get_escalacao_client
from feature_1_ia_personalizada.services.ai.escalation_client import (
    AnalisePecaResponse,
    EscalacaoIndisponivelError,
)
from shared.models.processo import Processo
from shared.models.sessao_advogado import SessaoAdvogado

# ---------------------------------------------------------------------------
# Constantes de teste
# ---------------------------------------------------------------------------

_FAKE_PDF = b"%PDF-1.4\n%%EOF\nfake pdf content for testing"
_FAKE_TEXT = (
    "Excelentíssimo Senhor Juiz de Direito. "
    "Vem o autor, por seu advogado, propor ação de indenização por danos morais. "
    "Fundamentos: art. 186 e 927 do Código Civil."
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_analise() -> AnalisePecaResponse:
    return AnalisePecaResponse(
        tipo_peca="Petição Inicial",
        pontos_fortes=["Fundamentação sólida no art. 186 CC"],
        vulnerabilidades=["Ausência de quantificação do dano moral"],
        argumentos_ausentes=["Nexo causal não demonstrado"],
        precedentes_relevantes=["STJ REsp 123456/SP — dano moral configurado"],
        score_geral=72,
        sugestoes=["Incluir laudo pericial para dano moral"],
        tokens_input=500,
        tokens_output=800,
        custo_estimado=Decimal("0.002"),
    )


def _mock_escalacao_client(
    analise: AnalisePecaResponse | None = None,
    resposta_consulta: str = "Art. 485 CPC — extinção sem resolução do mérito.",
) -> MagicMock:
    mock = MagicMock()
    mock.analisar_peca = AsyncMock(return_value=analise or _mock_analise())
    mock.gerar_resposta = AsyncMock(
        return_value=MagicMock(
            conteudo=resposta_consulta,
            tokens_input=300,
            tokens_output=400,
            custo_estimado=Decimal("0.001"),
        )
    )
    return mock


def _override(app, mock_client):
    """Context manager-like helper: aplica e remove override do EscalacaoClient."""
    app.dependency_overrides[get_escalacao_client] = lambda: mock_client
    return mock_client


def _clear(app):
    app.dependency_overrides.pop(get_escalacao_client, None)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def advogado_setup(escritorio_factory, usuario_factory, auth_token):
    escritorio = await escritorio_factory(nome="Escritório Hub Teste")
    advogado = await usuario_factory(
        escritorio_id=escritorio.id,
        nome="Dr. João Silva",
        role="advogado",
    )
    token = auth_token(user_id=advogado.id, escritorio_id=escritorio.id, role="advogado")
    return escritorio, advogado, {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# POST /hub/analisar-peticao
# ---------------------------------------------------------------------------


async def test_analisar_peticao_cliente_retorna_403(
    async_client,
    escritorio_factory,
    usuario_factory,
    auth_token,
):
    """Role 'cliente' não tem acesso ao Hub — deve receber 403."""
    escritorio = await escritorio_factory()
    usuario = await usuario_factory(escritorio_id=escritorio.id, role="cliente")
    token = auth_token(user_id=usuario.id, escritorio_id=escritorio.id, role="cliente")

    resp = await async_client.post(
        "/hub/analisar-peticao",
        headers={"Authorization": f"Bearer {token}"},
        files={"arquivo": ("doc.pdf", BytesIO(_FAKE_PDF), "application/pdf")},
    )

    assert resp.status_code == 403


async def test_analisar_peticao_sem_magic_bytes_retorna_422(async_client, advogado_setup):
    """Arquivo sem magic bytes '%PDF-' deve ser rejeitado com 422."""
    _, _, headers = advogado_setup

    resp = await async_client.post(
        "/hub/analisar-peticao",
        headers=headers,
        files={"arquivo": ("doc.docx", BytesIO(b"PK\x03\x04word content"), "application/pdf")},
    )

    assert resp.status_code == 422
    assert "%PDF-" in resp.json()["detail"]


async def test_analisar_peticao_arquivo_grande_retorna_422(async_client, advogado_setup):
    """PDF acima de 10 MB deve ser rejeitado com 422."""
    _, _, headers = advogado_setup
    conteudo_grande = b"%PDF-" + b"x" * (10 * 1024 * 1024 + 1)

    resp = await async_client.post(
        "/hub/analisar-peticao",
        headers=headers,
        files={"arquivo": ("grande.pdf", BytesIO(conteudo_grande), "application/pdf")},
    )

    assert resp.status_code == 422
    assert "10 MB" in resp.json()["detail"]


async def test_analisar_peticao_falha_extracao_retorna_422(async_client, advogado_setup):
    """Erro na extração de texto do PDF deve retornar 422."""
    _, _, headers = advogado_setup

    with patch(
        "feature_1_ia_personalizada.api.routes.hub_advogado._extrair_texto_pdf",
        side_effect=RuntimeError("PDF corrompido ou protegido"),
    ):
        resp = await async_client.post(
            "/hub/analisar-peticao",
            headers=headers,
            files={"arquivo": ("corrompido.pdf", BytesIO(_FAKE_PDF), "application/pdf")},
        )

    assert resp.status_code == 422
    assert "extrair" in resp.json()["detail"].lower()


async def test_analisar_peticao_escalacao_indisponivel_retorna_503(
    async_client, advogado_setup
):
    """EscalacaoIndisponivelError deve retornar 503."""
    from feature_1_ia_personalizada.api.app import app

    _, _, headers = advogado_setup
    mock_client = MagicMock()
    mock_client.analisar_peca = AsyncMock(
        side_effect=EscalacaoIndisponivelError("timeout após 3 tentativas")
    )

    with patch(
        "feature_1_ia_personalizada.api.routes.hub_advogado._extrair_texto_pdf",
        return_value=_FAKE_TEXT,
    ):
        _override(app, mock_client)
        try:
            resp = await async_client.post(
                "/hub/analisar-peticao",
                headers=headers,
                files={"arquivo": ("peticao.pdf", BytesIO(_FAKE_PDF), "application/pdf")},
            )
        finally:
            _clear(app)

    assert resp.status_code == 503
    assert "indisponível" in resp.json()["detail"].lower()


async def test_analisar_peticao_sucesso_chama_escalacao_e_salva_sessao(
    async_client,
    advogado_setup,
    db_session: AsyncSession,
):
    """PDF válido: EscalacaoClient.analisar_peca é chamado e SessaoAdvogado é salva."""
    from feature_1_ia_personalizada.api.app import app

    _, advogado, headers = advogado_setup
    mock_client = _mock_escalacao_client()

    with patch(
        "feature_1_ia_personalizada.api.routes.hub_advogado._extrair_texto_pdf",
        return_value=_FAKE_TEXT,
    ):
        _override(app, mock_client)
        try:
            resp = await async_client.post(
                "/hub/analisar-peticao",
                headers=headers,
                files={"arquivo": ("peticao.pdf", BytesIO(_FAKE_PDF), "application/pdf")},
            )
        finally:
            _clear(app)

    assert resp.status_code == 200
    body = resp.json()

    # Campos estruturados da análise
    assert body["tipo_peca"] == "Petição Inicial"
    assert body["score_geral"] == 72
    assert len(body["pontos_fortes"]) == 1

    # Campos de rastreamento de custo propagados do EscalacaoClient
    assert body["tokens_input"] == 500
    assert body["tokens_output"] == 800

    # Campos de transparência sobre truncamento
    assert body["texto_truncado"] is False
    assert body["percentual_analisado"] == 100.0

    # EscalacaoClient foi chamado com o texto extraído
    mock_client.analisar_peca.assert_called_once()
    assert _FAKE_TEXT in mock_client.analisar_peca.call_args.kwargs["conteudo_peca"]

    # SessaoAdvogado salva com tokens e custo corretos
    result = await db_session.execute(
        select(SessaoAdvogado).where(SessaoAdvogado.usuario_id == advogado.id)
    )
    sessao = result.scalar_one_or_none()
    assert sessao is not None
    assert sessao.intencao == "analise_peticao"
    assert sessao.modelo_ia == "claude_opus"
    assert sessao.tokens_input == 500
    assert sessao.tokens_output == 800
    assert sessao.custo_estimado == Decimal("0.002")
    assert sessao.metadata_json["texto_truncado"] is False


async def test_analisar_peticao_texto_longo_truncado(async_client, advogado_setup):
    """Texto com > 15 000 chars retorna texto_truncado=True e texto enviado à IA ≤ 15 000."""
    from feature_1_ia_personalizada.api.app import app

    _, _, headers = advogado_setup
    texto_longo = "Considerando que " * 1_000  # ~17 000 chars
    mock_client = _mock_escalacao_client()

    with patch(
        "feature_1_ia_personalizada.api.routes.hub_advogado._extrair_texto_pdf",
        return_value=texto_longo,
    ):
        _override(app, mock_client)
        try:
            resp = await async_client.post(
                "/hub/analisar-peticao",
                headers=headers,
                files={"arquivo": ("longa.pdf", BytesIO(_FAKE_PDF), "application/pdf")},
            )
        finally:
            _clear(app)

    assert resp.status_code == 200
    body = resp.json()
    assert body["texto_truncado"] is True
    assert body["percentual_analisado"] < 100.0

    # Texto passado à IA foi truncado
    conteudo_enviado = mock_client.analisar_peca.call_args.kwargs["conteudo_peca"]
    assert len(conteudo_enviado) <= 15_000


# ---------------------------------------------------------------------------
# POST /hub/consultar
# ---------------------------------------------------------------------------


async def test_consultar_retorna_resposta_e_salva_sessao(
    async_client,
    advogado_setup,
    db_session: AsyncSession,
):
    """Consulta jurídica retorna resposta Claude Opus e salva SessaoAdvogado."""
    from feature_1_ia_personalizada.api.app import app

    _, advogado, headers = advogado_setup
    mock_client = _mock_escalacao_client(
        resposta_consulta="Art. 485 CPC — extinção sem resolução do mérito."
    )

    _override(app, mock_client)
    try:
        resp = await async_client.post(
            "/hub/consultar",
            headers=headers,
            json={"pergunta": "Quais os casos do CPC art. 485?"},
        )
    finally:
        _clear(app)

    assert resp.status_code == 200
    body = resp.json()
    assert "485" in body["resposta"]
    assert body["modelo_ia"] == "claude_opus"
    assert body["tokens_input"] == 300
    assert body["tokens_output"] == 400

    result = await db_session.execute(
        select(SessaoAdvogado).where(SessaoAdvogado.usuario_id == advogado.id)
    )
    sessao = result.scalar_one_or_none()
    assert sessao is not None
    assert sessao.intencao == "duvida_juridica"
    assert sessao.mensagem_advogado == "Quais os casos do CPC art. 485?"
    assert sessao.tokens_input == 300
    assert sessao.cliente_referenciado_id is None
    assert sessao.processo_referenciado_id is None


async def test_consultar_com_cliente_injeta_contexto_e_salva_referencia(
    async_client,
    advogado_setup,
    cliente_factory,
    db_session: AsyncSession,
):
    """cliente_id válido: nome aparece no contexto da IA e sessão guarda a referência."""
    from feature_1_ia_personalizada.api.app import app

    escritorio, advogado, headers = advogado_setup
    cliente = await cliente_factory(escritorio_id=escritorio.id, nome="Maria Oliveira")
    mock_client = _mock_escalacao_client()

    _override(app, mock_client)
    try:
        resp = await async_client.post(
            "/hub/consultar",
            headers=headers,
            json={"pergunta": "Qual a situação atual?", "cliente_id": cliente.id},
        )
    finally:
        _clear(app)

    assert resp.status_code == 200
    assert "Maria Oliveira" in mock_client.gerar_resposta.call_args.kwargs["mensagem_usuario"]

    result = await db_session.execute(
        select(SessaoAdvogado).where(SessaoAdvogado.usuario_id == advogado.id)
    )
    sessao = result.scalar_one_or_none()
    assert sessao is not None
    assert sessao.cliente_referenciado_id == cliente.id


async def test_consultar_com_processo_injeta_contexto_e_salva_referencia(
    async_client,
    advogado_setup,
    cliente_factory,
    db_session: AsyncSession,
):
    """processo_id válido: CNJ aparece no contexto da IA e sessão guarda a referência."""
    from feature_1_ia_personalizada.api.app import app

    escritorio, advogado, headers = advogado_setup
    cliente = await cliente_factory(escritorio_id=escritorio.id)

    processo = Processo(
        escritorio_id=escritorio.id,
        cliente_id=cliente.id,
        numero_cnj="0001234-56.2024.8.26.0001",
        tipo_acao="Ação de Indenização",
        fase_processual="Instrução",
    )
    db_session.add(processo)
    await db_session.commit()
    await db_session.refresh(processo)

    mock_client = _mock_escalacao_client()

    _override(app, mock_client)
    try:
        resp = await async_client.post(
            "/hub/consultar",
            headers=headers,
            json={"pergunta": "Como está o processo?", "processo_id": processo.id},
        )
    finally:
        _clear(app)

    assert resp.status_code == 200
    mensagem = mock_client.gerar_resposta.call_args.kwargs["mensagem_usuario"]
    assert "0001234-56.2024.8.26.0001" in mensagem
    assert "Ação de Indenização" in mensagem

    result = await db_session.execute(
        select(SessaoAdvogado).where(SessaoAdvogado.usuario_id == advogado.id)
    )
    sessao = result.scalar_one_or_none()
    assert sessao is not None
    assert sessao.processo_referenciado_id == processo.id


async def test_consultar_cliente_outro_escritorio_ignorado(
    async_client,
    advogado_setup,
    escritorio_factory,
    cliente_factory,
    db_session: AsyncSession,
):
    """cliente_id de outro escritório é ignorado — nome não aparece no contexto (multi-tenant)."""
    from feature_1_ia_personalizada.api.app import app

    _, advogado, headers = advogado_setup
    outro_escritorio = await escritorio_factory()
    cliente_alheio = await cliente_factory(
        escritorio_id=outro_escritorio.id, nome="Carlos Alheio"
    )
    mock_client = _mock_escalacao_client()

    _override(app, mock_client)
    try:
        resp = await async_client.post(
            "/hub/consultar",
            headers=headers,
            json={"pergunta": "Teste isolamento.", "cliente_id": cliente_alheio.id},
        )
    finally:
        _clear(app)

    assert resp.status_code == 200
    mensagem = mock_client.gerar_resposta.call_args.kwargs["mensagem_usuario"]
    assert "Carlos Alheio" not in mensagem

    result = await db_session.execute(
        select(SessaoAdvogado).where(SessaoAdvogado.usuario_id == advogado.id)
    )
    sessao = result.scalar_one_or_none()
    assert sessao is not None
    assert sessao.cliente_referenciado_id is None


async def test_consultar_escalacao_indisponivel_retorna_503(
    async_client, advogado_setup
):
    """EscalacaoIndisponivelError em /consultar deve retornar 503."""
    from feature_1_ia_personalizada.api.app import app

    _, _, headers = advogado_setup
    mock_client = MagicMock()
    mock_client.gerar_resposta = AsyncMock(
        side_effect=EscalacaoIndisponivelError("modelo indisponível")
    )

    _override(app, mock_client)
    try:
        resp = await async_client.post(
            "/hub/consultar",
            headers=headers,
            json={"pergunta": "Dúvida sobre recurso."},
        )
    finally:
        _clear(app)

    assert resp.status_code == 503
    assert "indisponível" in resp.json()["detail"].lower()
