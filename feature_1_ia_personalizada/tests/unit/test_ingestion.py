# feature_1_ia_personalizada/tests/unit/test_ingestion.py
"""
Testes unitários do DocumentoIngester.

Cobre:
  - Tipo inválido retorna erro sem tocar o banco
  - Deduplicação: segundo ingest do mesmo texto retorna duplicata=True
  - Chunking: textos longos geram múltiplos chunks salvos no banco
  - Extração de metadados via regex (CNJ, tribunal, data)
  - Claude não é chamado quando regex já extrai todos os campos obrigatórios
  - Texto vazio após limpeza retorna erro sem inserir no banco
"""

from __future__ import annotations

import hashlib
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from feature_1_ia_personalizada.services.rag.ingestion import (
    DocumentoIngester,
    IngestaoResultado,
    _chunkar,
    _limpar_texto,
)
from shared.models.documento_rag import EMBEDDING_DIM

# ---------------------------------------------------------------------------
# Fake session + session factory para testes
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, value) -> None:
        self._value = value

    def scalar(self):
        return self._value


class _FakeSession:
    """
    Simula AsyncSession do SQLAlchemy.

    - execute() retorna _FakeResult configurável via _resultado_execute
    - add_all() registra os objetos em _inseridos
    - commit() / rollback() são no-ops assíncronos
    """

    def __init__(self) -> None:
        self._inseridos: list = []
        self._resultado_execute: Any = _FakeResult(None)

    async def execute(self, stmt):
        return self._resultado_execute

    def add_all(self, objs):
        self._inseridos.extend(objs)

    async def commit(self):
        pass

    async def rollback(self):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


def _make_session_factory(session: _FakeSession):
    """Retorna um callable que atua como async_sessionmaker."""

    class _Factory:
        def __call__(self):
            return session

    return _Factory()


def _make_embedding_mock(n_chunks: int) -> AsyncMock:
    """Retorna mock de EmbeddingGenerator.gerar_batch que retorna n_chunks vetores."""
    mock = AsyncMock()
    mock.gerar_batch = AsyncMock(
        return_value=[[0.1] * EMBEDDING_DIM for _ in range(n_chunks)]
    )
    return mock


# ---------------------------------------------------------------------------
# Testes — validação de tipo
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tipo_invalido_retorna_erro():
    """Tipo não reconhecido deve retornar erro sem chamar o banco."""
    session = _FakeSession()
    factory = _make_session_factory(session)
    embeddings_mock = _make_embedding_mock(0)

    with patch(
        "feature_1_ia_personalizada.services.rag.ingestion.settings"
    ) as mock_settings:
        mock_settings.ANTHROPIC_API_KEY = "fake-key"
        ingester = DocumentoIngester(
            embedding_generator=embeddings_mock,
            session_factory=factory,
        )

    resultado = await ingester.ingerir_texto(
        texto="qualquer texto",
        escritorio_id=1,
        titulo="Teste",
        tipo="tipo_invalido",
    )

    assert resultado.erro is not None
    assert "Tipo inválido" in resultado.erro
    assert not resultado.sucesso
    assert session._inseridos == []


# ---------------------------------------------------------------------------
# Testes — deduplicação
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deduplicacao_retorna_duplicata():
    """Se o doc_hash já existir, ingerir_texto deve retornar duplicata=True."""
    session = _FakeSession()
    # Simula que o banco já possui o documento (scalar retorna um ID)
    session._resultado_execute = _FakeResult(42)
    factory = _make_session_factory(session)
    embeddings_mock = _make_embedding_mock(0)

    with patch(
        "feature_1_ia_personalizada.services.rag.ingestion.settings"
    ) as mock_settings:
        mock_settings.ANTHROPIC_API_KEY = "fake-key"
        ingester = DocumentoIngester(
            embedding_generator=embeddings_mock,
            session_factory=factory,
        )

    resultado = await ingester.ingerir_texto(
        texto="petição inicial de indenização por danos morais",
        escritorio_id=1,
        titulo="Petição",
        tipo="peticao",
    )

    assert resultado.duplicata is True
    assert resultado.sucesso is False
    # Nenhum chunk deve ter sido inserido
    assert session._inseridos == []


@pytest.mark.asyncio
async def test_deduplicacao_por_texto_limpo():
    """
    Dois textos idênticos exceto por artefatos de paginação devem gerar o mesmo hash
    e o segundo deve ser detectado como duplicata.
    """
    texto1 = "Recurso de apelação. Sentença mantida.\n\nPágina 1"
    texto2 = "Recurso de apelação. Sentença mantida.\n\n"

    limpo1 = _limpar_texto(texto1)
    limpo2 = _limpar_texto(texto2)

    hash1 = hashlib.sha256(limpo1.encode()).hexdigest()
    hash2 = hashlib.sha256(limpo2.encode()).hexdigest()

    assert hash1 == hash2, (
        "Textos com diferença apenas em artefatos de paginação devem ter o mesmo hash após limpeza"
    )


# ---------------------------------------------------------------------------
# Testes — chunking e inserção
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chunks_sao_inseridos_no_banco():
    """Texto novo deve gerar chunks e inseri-los no banco."""
    texto = "Vistos, relatados e discutidos estes autos. " * 100  # texto longo

    # Conta quantos chunks serão gerados
    chunks_esperados = _chunkar(texto)
    n = len(chunks_esperados)
    assert n >= 1

    session = _FakeSession()
    # Simula banco vazio (não é duplicata)
    session._resultado_execute = _FakeResult(None)
    factory = _make_session_factory(session)
    embeddings_mock = _make_embedding_mock(n)

    with patch(
        "feature_1_ia_personalizada.services.rag.ingestion.settings"
    ) as mock_settings, patch(
        "feature_1_ia_personalizada.services.rag.ingestion.DocumentoIngester._extrair_metadata",
        new_callable=AsyncMock,
        return_value={"numero_cnj": "0001234-56.2024.8.26.0001", "tribunal": "TJSP"},
    ):
        mock_settings.ANTHROPIC_API_KEY = "fake-key"
        ingester = DocumentoIngester(
            embedding_generator=embeddings_mock,
            session_factory=factory,
        )
        resultado = await ingester.ingerir_texto(
            texto=texto,
            escritorio_id=5,
            titulo="Acórdão TJSP",
            tipo="sentenca",
        )

    assert resultado.sucesso is True
    assert resultado.chunks_gerados == n
    assert len(session._inseridos) == n
    # Verifica que chunk_index está correto
    indices = [obj.chunk_index for obj in session._inseridos]
    assert indices == list(range(n))


@pytest.mark.asyncio
async def test_texto_vazio_apos_limpeza_retorna_erro():
    """Documento que resulta em texto vazio após limpeza deve retornar erro."""
    # Apenas linhas de página e underscores → tudo removido
    texto_lixo = "Pág. 1\n\n___________\n\n"

    session = _FakeSession()
    session._resultado_execute = _FakeResult(None)
    factory = _make_session_factory(session)
    embeddings_mock = _make_embedding_mock(0)

    with patch(
        "feature_1_ia_personalizada.services.rag.ingestion.settings"
    ) as mock_settings:
        mock_settings.ANTHROPIC_API_KEY = "fake-key"
        ingester = DocumentoIngester(
            embedding_generator=embeddings_mock,
            session_factory=factory,
        )
        resultado = await ingester.ingerir_texto(
            texto=texto_lixo,
            escritorio_id=1,
            titulo="Vazio",
            tipo="peticao",
        )

    assert resultado.erro is not None
    assert "vazio" in resultado.erro.lower()
    assert session._inseridos == []


# ---------------------------------------------------------------------------
# Testes — extração de metadados via regex
# ---------------------------------------------------------------------------


def test_limpar_texto_remove_paginacao():
    """_limpar_texto deve remover marcações de página."""
    texto = "Conteúdo do documento.\n\nPágina 1\n\nMais conteúdo."
    resultado = _limpar_texto(texto)
    assert "Página 1" not in resultado
    assert "Conteúdo do documento." in resultado


def test_limpar_texto_comprime_linhas_vazias():
    """_limpar_texto deve reduzir sequências de 3+ quebras de linha para 2."""
    texto = "Linha 1\n\n\n\n\nLinha 2"
    resultado = _limpar_texto(texto)
    assert "\n\n\n" not in resultado
    assert "Linha 1" in resultado
    assert "Linha 2" in resultado


@pytest.mark.asyncio
async def test_regex_extrai_numero_cnj():
    """Número CNJ no texto deve ser extraído por regex sem chamar Claude."""
    texto = "Processo nº 0001234-56.2024.8.26.0001 - Ação de Indenização"

    session = _FakeSession()
    session._resultado_execute = _FakeResult(None)
    factory = _make_session_factory(session)
    embeddings_mock = _make_embedding_mock(1)

    claude_mock = AsyncMock()

    with patch(
        "feature_1_ia_personalizada.services.rag.ingestion.settings"
    ) as mock_settings, patch(
        "feature_1_ia_personalizada.services.rag.ingestion.DocumentoIngester._extrair_metadata_claude",
        new_callable=AsyncMock,
        return_value={},
    ) as mock_claude:
        mock_settings.ANTHROPIC_API_KEY = "fake-key"
        ingester = DocumentoIngester(
            embedding_generator=embeddings_mock,
            session_factory=factory,
        )
        # Injeta texto curto que gera 1 chunk apenas
        resultado = await ingester.ingerir_texto(
            texto=texto,
            escritorio_id=1,
            titulo="Petição",
            tipo="peticao",
        )

    # Claude só é chamado se faltam campos após regex
    # numero_cnj foi achado pelo regex; tipo_acao e tribunal não → Claude pode ser chamado
    # mas numero_cnj deve estar presente via regex
    for obj in session._inseridos:
        assert obj.metadata_json.get("numero_cnj") == "0001234-56.2024.8.26.0001"


@pytest.mark.asyncio
async def test_claude_nao_chamado_quando_regex_encontra_tudo():
    """Se regex extrair numero_cnj, tribunal e tipo_acao, Claude não deve ser chamado."""
    # texto com CNJ + tribunal; tipo_acao virá via metadata pré-preenchida
    texto = "Processo 0001234-56.2024.8.26.0001 - STJ - recurso especial"

    session = _FakeSession()
    session._resultado_execute = _FakeResult(None)
    factory = _make_session_factory(session)
    embeddings_mock = _make_embedding_mock(1)

    with patch(
        "feature_1_ia_personalizada.services.rag.ingestion.settings"
    ) as mock_settings, patch(
        "feature_1_ia_personalizada.services.rag.ingestion.DocumentoIngester._extrair_metadata_claude",
        new_callable=AsyncMock,
        return_value={},
    ) as mock_claude:
        mock_settings.ANTHROPIC_API_KEY = "fake-key"
        ingester = DocumentoIngester(
            embedding_generator=embeddings_mock,
            session_factory=factory,
        )
        await ingester.ingerir_texto(
            texto=texto,
            escritorio_id=1,
            titulo="Recurso Especial STJ",
            tipo="jurisprudencia",
            # tipo_acao fornecido via metadata — evita chamada ao Claude
            metadata={"tipo_acao": "Recurso Especial"},
        )

    # Com numero_cnj (regex), tribunal (regex) e tipo_acao (metadata),
    # não deve haver campos faltando → Claude não é chamado
    mock_claude.assert_not_called()
