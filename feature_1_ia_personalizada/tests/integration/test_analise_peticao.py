# feature_1_ia_personalizada/tests/integration/test_analise_peticao.py
"""
Testes de integração — Hub do Advogado REST API
================================================
Cobre os critérios de aceite da task 4.3.

Critérios testados:
1. POST /hub/analisar-peticao com role cliente → 403
2. POST /hub/analisar-peticao com PDF válido → escalacao chamado + SessaoAdvogado salva
3. POST /hub/analisar-peticao com arquivo sem magic bytes PDF → 422
4. POST /hub/analisar-peticao com PDF acima de 10 MB → 422
5. POST /hub/analisar-peticao com texto > 15 000 chars → texto_truncado=True
6. POST /hub/consultar → resposta Claude Opus + SessaoAdvogado salva
7. POST /hub/consultar com cliente_id → contexto injeta nome do cliente
8. POST /hub/consultar com cliente_id de outro escritório → ignorado (multi-tenant)
"""

from __future__ import annotations

from decimal import Decimal
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from feature_1_ia_personalizada.api.routes.hub_advogado import _get_escalacao_client
from feature_1_ia_personalizada.services.ai.escalation_client import AnalisePecaResponse
from shared.models.sessao_advogado import SessaoAdvogado

# ---------------------------------------------------------------------------
# Constantes de teste
# ---------------------------------------------------------------------------

# Conteúdo mínimo com magic bytes válidos (%PDF-)
_FAKE_PDF = b"%PDF-1.4\n%%EOF\nfake pdf content"
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
    """Mock do EscalacaoClient com analisar_peca e gerar_resposta pré-configurados."""
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def advogado_setup(escritorio_factory, usuario_factory, auth_token, db_session):
    """Cria escritório + advogado e retorna (escritorio, usuario, headers_advogado)."""
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


async def test_analisar_peticao_sem_magic_bytes_retorna_422(
    async_client,
    advogado_setup,
):
    """Arquivo sem os magic bytes '%PDF-' deve ser rejeitado com 422."""
    _, _, headers = advogado_setup

    resp = await async_client.post(
        "/hub/analisar-peticao",
        headers=headers,
        files={"arquivo": ("doc.docx", BytesIO(b"PK\x03\x04word content"), "application/pdf")},
    )

    assert resp.status_code == 422
    assert "%PDF-" in resp.json()["detail"]


async def test_analisar_peticao_arquivo_grande_retorna_422(
    async_client,
    advogado_setup,
):
    """PDF com mais de 10 MB deve ser rejeitado com 422."""
    _, _, headers = advogado_setup
    conteudo_grande = b"%PDF-" + b"x" * (10 * 1024 * 1024 + 1)

    resp = await async_client.post(
        "/hub/analisar-peticao",
        headers=headers,
        files={"arquivo": ("grande.pdf", BytesIO(conteudo_grande), "application/pdf")},
    )

    assert resp.status_code == 422
    assert "10 MB" in resp.json()["detail"]


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
        "feature_1_ia_personalizada.services.rag.ingestion.DocumentoIngester._extrair_texto_pdf",
        return_value=_FAKE_TEXT,
    ):
        app.dependency_overrides[_get_escalacao_client] = lambda: mock_client
        try:
            resp = await async_client.post(
                "/hub/analisar-peticao",
                headers=headers,
                files={"arquivo": ("peticao.pdf", BytesIO(_FAKE_PDF), "application/pdf")},
            )
        finally:
            app.dependency_overrides.pop(_get_escalacao_client, None)

    assert resp.status_code == 200
    body = resp.json()

    # Campos estruturados da análise
    assert body["tipo_peca"] == "Petição Inicial"
    assert body["score_geral"] == 72
    assert len(body["pontos_fortes"]) == 1
    assert len(body["vulnerabilidades"]) == 1

    # Campos de rastreamento de custo
    assert body["tokens_input"] == 500
    assert body["tokens_output"] == 800

    # Campos de transparência sobre truncamento
    assert "texto_truncado" in body
    assert body["texto_truncado"] is False  # texto curto, não truncado
    assert body["percentual_analisado"] == 100.0

    # EscalacaoClient foi chamado uma vez com o texto extraído
    mock_client.analisar_peca.assert_called_once()
    call_kwargs = mock_client.analisar_peca.call_args.kwargs
    assert _FAKE_TEXT in call_kwargs["conteudo_peca"]

    # SessaoAdvogado salva no banco com campos corretos
    resultado = await db_session.execute(
        select(SessaoAdvogado).where(SessaoAdvogado.usuario_id == advogado.id)
    )
    sessao = resultado.scalar_one_or_none()
    assert sessao is not None
    assert sessao.intencao == "analise_peticao"
    assert sessao.modelo_ia == "claude_opus"
    assert sessao.tokens_input == 500
    assert sessao.tokens_output == 800
    assert sessao.custo_estimado == Decimal("0.002")
    assert sessao.metadata_json["texto_truncado"] is False


async def test_analisar_peticao_texto_longo_truncado(
    async_client,
    advogado_setup,
):
    """Texto com > 15 000 chars deve retornar texto_truncado=True e percentual_analisado < 100."""
    from feature_1_ia_personalizada.api.app import app

    _, _, headers = advogado_setup
    texto_longo = "Considerando que " * 1_000  # ~17 000 chars

    mock_client = _mock_escalacao_client()

    with patch(
        "feature_1_ia_personalizada.services.rag.ingestion.DocumentoIngester._extrair_texto_pdf",
        return_value=texto_longo,
    ):
        app.dependency_overrides[_get_escalacao_client] = lambda: mock_client
        try:
            resp = await async_client.post(
                "/hub/analisar-peticao",
                headers=headers,
                files={"arquivo": ("longa.pdf", BytesIO(_FAKE_PDF), "application/pdf")},
            )
        finally:
            app.dependency_overrides.pop(_get_escalacao_client, None)

    assert resp.status_code == 200
    body = resp.json()
    assert body["texto_truncado"] is True
    assert body["percentual_analisado"] < 100.0

    # Confirma que o texto enviado à IA foi truncado em 15 000 chars
    call_kwargs = mock_client.analisar_peca.call_args.kwargs
    assert len(call_kwargs["conteudo_peca"]) <= 15_000


# ---------------------------------------------------------------------------
# POST /hub/consultar
# ---------------------------------------------------------------------------


async def test_consultar_retorna_resposta_e_salva_sessao(
    async_client,
    advogado_setup,
    db_session: AsyncSession,
):
    """Consulta jurídica deve retornar resposta Claude Opus e salvar SessaoAdvogado."""
    from feature_1_ia_personalizada.api.app import app

    _, advogado, headers = advogado_setup
    mock_client = _mock_escalacao_client(
        resposta_consulta="Art. 485 CPC — extinção sem resolução do mérito."
    )

    app.dependency_overrides[_get_escalacao_client] = lambda: mock_client
    try:
        resp = await async_client.post(
            "/hub/consultar",
            headers=headers,
            json={"pergunta": "Quais os casos do CPC art. 485?"},
        )
    finally:
        app.dependency_overrides.pop(_get_escalacao_client, None)

    assert resp.status_code == 200
    body = resp.json()
    assert "485" in body["resposta"]
    assert body["modelo_ia"] == "claude_opus"
    assert body["tokens_input"] == 300
    assert body["tokens_output"] == 400

    resultado = await db_session.execute(
        select(SessaoAdvogado).where(SessaoAdvogado.usuario_id == advogado.id)
    )
    sessao = resultado.scalar_one_or_none()
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
    """Consulta com cliente_id: nome do cliente aparece no contexto e sessão guarda a referência."""
    from feature_1_ia_personalizada.api.app import app

    escritorio, advogado, headers = advogado_setup
    cliente = await cliente_factory(escritorio_id=escritorio.id, nome="Maria Oliveira")
    mock_client = _mock_escalacao_client()

    app.dependency_overrides[_get_escalacao_client] = lambda: mock_client
    try:
        resp = await async_client.post(
            "/hub/consultar",
            headers=headers,
            json={"pergunta": "Qual a situação atual?", "cliente_id": cliente.id},
        )
    finally:
        app.dependency_overrides.pop(_get_escalacao_client, None)

    assert resp.status_code == 200

    # Nome do cliente deve estar no argumento mensagem_usuario passado à IA
    call_kwargs = mock_client.gerar_resposta.call_args.kwargs
    assert "Maria Oliveira" in call_kwargs["mensagem_usuario"]

    # SessaoAdvogado deve ter cliente_referenciado_id preenchido
    resultado = await db_session.execute(
        select(SessaoAdvogado).where(SessaoAdvogado.usuario_id == advogado.id)
    )
    sessao = resultado.scalar_one_or_none()
    assert sessao is not None
    assert sessao.cliente_referenciado_id == cliente.id


async def test_consultar_cliente_outro_escritorio_ignorado(
    async_client,
    advogado_setup,
    escritorio_factory,
    cliente_factory,
    db_session: AsyncSession,
):
    """cliente_id pertencente a outro escritório é silenciosamente ignorado (multi-tenant)."""
    from feature_1_ia_personalizada.api.app import app

    _, advogado, headers = advogado_setup
    outro_escritorio = await escritorio_factory()
    cliente_alheio = await cliente_factory(
        escritorio_id=outro_escritorio.id, nome="Carlos Alheio"
    )
    mock_client = _mock_escalacao_client()

    app.dependency_overrides[_get_escalacao_client] = lambda: mock_client
    try:
        resp = await async_client.post(
            "/hub/consultar",
            headers=headers,
            json={"pergunta": "Teste isolamento.", "cliente_id": cliente_alheio.id},
        )
    finally:
        app.dependency_overrides.pop(_get_escalacao_client, None)

    assert resp.status_code == 200

    # Nome do cliente alheio NÃO deve aparecer no contexto enviado à IA
    call_kwargs = mock_client.gerar_resposta.call_args.kwargs
    assert "Carlos Alheio" not in call_kwargs["mensagem_usuario"]

    # Sessão não deve referenciar o cliente de outro escritório
    resultado = await db_session.execute(
        select(SessaoAdvogado).where(SessaoAdvogado.usuario_id == advogado.id)
    )
    sessao = resultado.scalar_one_or_none()
    assert sessao is not None
    assert sessao.cliente_referenciado_id is None
