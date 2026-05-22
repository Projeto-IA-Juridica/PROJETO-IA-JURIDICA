# feature_1_ia_personalizada/tests/integration/test_rag_pipeline.py
"""
Teste de integração do pipeline RAG Jurisprudencial.

Cobre:
  1. Validações de erro no upload (tipo inválido, extensão proibida)
  2. Busca semântica via /rag/buscar → retorna contexto ou placeholder
  3. Listagem de documentos e status sem auth → 401
  4. Pipeline de ingestão de texto completo (serviço, sem HTTP)
  5. Deduplicação no pipeline de ingestão

Nota sobre os testes HTTP:
  O async_client do conftest usa SQLite in-memory que não suporta pgvector.
  Os testes HTTP usam um cliente isolado (sem criação de tabelas) e sobrepõem
  as dependências do FastAPI que precisam de banco via dependency_overrides.

Dependências externas (Redis, Celery, Embeddings, DB vetorial) são
substituídas por mocks/fakes para que os testes rodem sem infraestrutura.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from feature_1_ia_personalizada.api.routes.rag import (
    get_rag_retriever,
    get_redis,
)
from shared.models.documento_rag import EMBEDDING_DIM

# ---------------------------------------------------------------------------
# Helpers de setup
# ---------------------------------------------------------------------------


_CSRF_TEST_TOKEN = "a" * 64


class _FakeRedis:
    """Redis em memória simples para integração."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def set(self, key: str, value: str, *, ex: int | None = None, nx: bool = False) -> bool:
        if nx and key in self._store:
            return False
        self._store[key] = str(value)
        return True

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self._store[key] = value

    async def mget(self, *keys: str) -> list[str | None]:
        return [self._store.get(k) for k in keys]

    async def incr(self, key: str) -> int:
        current = int(self._store.get(key, "0"))
        current += 1
        self._store[key] = str(current)
        return current

    async def expire(self, key: str, seconds: int) -> int:
        return 1

    async def aclose(self) -> None:
        pass

    def pipeline(self):
        return _FakePipeline(self)


class _FakePipeline:
    def __init__(self, redis: _FakeRedis) -> None:
        self._redis = redis
        self._ops: list[tuple] = []

    def setex(self, key: str, ttl: int, value: str) -> _FakePipeline:
        self._ops.append((key, ttl, value))
        return self

    async def execute(self) -> None:
        for key, _ttl, value in self._ops:
            self._redis._store[key] = value


def _pdf_fake() -> bytes:
    return b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF"


def _fake_retriever_com_resultado():
    mock = AsyncMock()
    mock.buscar = AsyncMock(
        return_value=(
            "<contexto_juridico_escritorio>\n"
            "[1] Sentenca — Acórdão TJSP\n"
            "Conteúdo jurídico relevante.\n"
            "</contexto_juridico_escritorio>"
        )
    )
    return mock


def _fake_retriever_vazio():
    mock = AsyncMock()
    mock.buscar = AsyncMock(return_value="")
    return mock


# ---------------------------------------------------------------------------
# Fixture: cliente HTTP isolado sem SQLite/pgvector
# ---------------------------------------------------------------------------


@pytest.fixture
async def rag_http_client():
    """
    AsyncClient apontando para o app FastAPI com:
    - Redis fake em memória
    - JWT real (gerado com criar_token) no header Authorization

    token_esta_revogado faz fail-open quando Redis está offline → token aceito.
    Não usa o async_client do conftest (que tenta criar tabelas SQLite/pgvector).
    """
    from feature_1_ia_personalizada.api.app import app
    from shared.security.jwt import criar_token

    fake_redis = _FakeRedis()
    token = criar_token(user_id=99, escritorio_id=1, role="admin")

    app.dependency_overrides[get_redis] = lambda: fake_redis

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {token}", "x-csrf-token": _CSRF_TEST_TOKEN},
        cookies={"csrf_token": _CSRF_TEST_TOKEN},
    ) as client:
        # Re-inject after lifespan startup overwrites app.state.redis_client with real Redis
        _original_redis = getattr(app.state, "redis_client", None)
        app.state.redis_client = fake_redis
        yield client, fake_redis
        app.state.redis_client = _original_redis

    app.dependency_overrides.pop(get_redis, None)


# ---------------------------------------------------------------------------
# Testes — Upload: validação de erros sem banco
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_tipo_invalido_retorna_422(rag_http_client):
    client, _ = rag_http_client
    response = await client.post(
        "/rag/upload?titulo=Teste&tipo=tipo_invalido",
        files={"file": ("doc.pdf", _pdf_fake(), "application/pdf")},
    )
    assert response.status_code == 422
    assert "Tipo inválido" in response.json()["detail"]


@pytest.mark.asyncio
async def test_upload_extensao_invalida_retorna_422(rag_http_client):
    client, _ = rag_http_client
    response = await client.post(
        "/rag/upload?titulo=Teste&tipo=peticao",
        files={"file": ("doc.exe", b"binary", "application/octet-stream")},
    )
    assert response.status_code == 422
    assert "Extensão" in response.json()["detail"]


@pytest.mark.asyncio
async def test_upload_titulo_ausente_retorna_422(rag_http_client):
    client, _ = rag_http_client
    response = await client.post(
        "/rag/upload?tipo=peticao",
        files={"file": ("doc.pdf", _pdf_fake(), "application/pdf")},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Testes — Status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_status_job_nao_encontrado_retorna_404(rag_http_client):
    client, _ = rag_http_client
    response = await client.get("/rag/status/job-inexistente-xpto-abc-123")
    assert response.status_code == 404
    assert "não encontrado" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_status_job_existente_retorna_dados(rag_http_client):
    client, redis = rag_http_client
    job_id = "test-job-id-abc"
    job_data = {
        "status": "pendente",
        "escritorio_id": 1,
        "titulo": "Petição",
        "tipo": "peticao",
        "arquivo": "doc.pdf",
        "chunks": 0,
        "erro": None,
    }
    await redis.setex(f"f1:rag:job:{job_id}", 86400, json.dumps(job_data))

    response = await client.get(f"/rag/status/{job_id}")
    assert response.status_code == 200
    assert response.json()["status"] == "pendente"
    assert response.json()["titulo"] == "Petição"


@pytest.mark.asyncio
async def test_status_job_outro_escritorio_retorna_404(rag_http_client):
    """Job de escritório 99 não deve ser visível para escritório 1."""
    client, redis = rag_http_client
    job_id = "test-job-outro-escritorio"
    job_data = {"status": "concluido", "escritorio_id": 99, "titulo": "X", "tipo": "peticao"}
    await redis.setex(f"f1:rag:job:{job_id}", 86400, json.dumps(job_data))

    response = await client.get(f"/rag/status/{job_id}")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Testes — Busca semântica
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_buscar_sem_auth_retorna_401():
    """POST /rag/buscar sem autenticação deve retornar 401."""
    from feature_1_ia_personalizada.api.app import app

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"x-csrf-token": _CSRF_TEST_TOKEN},
        cookies={"csrf_token": _CSRF_TEST_TOKEN},
    ) as client:
        response = await client.post(
            "/rag/buscar",
            json={"query": "prazo recursal"},
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_buscar_retorna_contexto(rag_http_client):
    """POST /rag/buscar com retriever mockado deve retornar bloco XML."""
    from feature_1_ia_personalizada.api.app import app

    client, _ = rag_http_client
    app.dependency_overrides[get_rag_retriever] = _fake_retriever_com_resultado

    try:
        response = await client.post(
            "/rag/buscar",
            json={"query": "prazo recursal apelação"},
        )
    finally:
        app.dependency_overrides.pop(get_rag_retriever, None)

    assert response.status_code == 200
    assert "contexto_juridico_escritorio" in response.json()["contexto"]


@pytest.mark.asyncio
async def test_buscar_sem_resultado_retorna_placeholder(rag_http_client):
    """Quando retriever retorna vazio, endpoint retorna placeholder."""
    from feature_1_ia_personalizada.api.app import app

    client, _ = rag_http_client
    app.dependency_overrides[get_rag_retriever] = _fake_retriever_vazio

    try:
        response = await client.post(
            "/rag/buscar",
            json={"query": "tema completamente irrelevante"},
        )
    finally:
        app.dependency_overrides.pop(get_rag_retriever, None)

    assert response.status_code == 200
    assert response.json()["contexto"] == "(nenhum resultado acima do threshold)"


# ---------------------------------------------------------------------------
# Testes — Pipeline de ingestão (serviço puro, sem HTTP)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_ingestao_texto_completo():
    """
    Pipeline de ingestão de ponta a ponta com fakes de DB e embeddings.
    Verifica: texto → chunks → embeddings → inserção no banco com metadados.
    """
    from feature_1_ia_personalizada.services.rag.ingestion import DocumentoIngester

    inseridos = []

    class _FakeSession:
        async def execute(self, stmt):
            class _R:
                def scalar(self):
                    return None  # não é duplicata

            return _R()

        def add_all(self, objs):
            inseridos.extend(objs)

        async def commit(self):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    class _FakeFactory:
        def __call__(self):
            return _FakeSession()

    # Texto com número CNJ e sigla TJSP explícita (para o regex bater)
    texto = (
        "PODER JUDICIÁRIO. TJSP - TRIBUNAL DE JUSTIÇA DO ESTADO DE SÃO PAULO.\n"
        "Processo nº 1001234-56.2024.8.26.0001\n"
        "Ação de Indenização por Danos Morais.\n"
        "SENTENÇA. Vistos. Trata-se de ação movida pelo autor em face do réu.\n"
        "Isto posto, JULGO PROCEDENTE o pedido para condenar o réu ao pagamento.\n"
        "São Paulo, 17 de março de 2026.\n"
    )

    emb_mock = AsyncMock()
    emb_mock.gerar_batch = AsyncMock(
        side_effect=lambda textos: [[0.1] * EMBEDDING_DIM for _ in textos]
    )

    with (
        patch("feature_1_ia_personalizada.services.rag.ingestion.settings") as mock_settings,
        patch(
            "feature_1_ia_personalizada.services.rag.ingestion.DocumentoIngester._extrair_metadata_claude",
            new_callable=AsyncMock,
            return_value={},
        ),
        patch(
            "feature_1_ia_personalizada.services.rag.ingestion._chunkar",
            return_value=["chunk1 do texto jurídico", "chunk2 do texto jurídico"],
        ),
    ):
        mock_settings.ANTHROPIC_API_KEY = "fake-key"
        ingester = DocumentoIngester(
            embedding_generator=emb_mock,
            session_factory=_FakeFactory(),
        )
        resultado = await ingester.ingerir_texto(
            texto=texto,
            escritorio_id=42,
            titulo="Sentença TJSP - Danos Morais",
            tipo="sentenca",
        )

    assert resultado.sucesso is True
    assert resultado.tipo == "sentenca"
    assert resultado.escritorio_id == 42
    assert resultado.chunks_gerados >= 1
    assert len(inseridos) == resultado.chunks_gerados

    # Metadados extraídos pelo regex
    assert resultado.metadata_extraida.get("numero_cnj") == "1001234-56.2024.8.26.0001"
    assert resultado.metadata_extraida.get("tribunal") == "TJSP"

    # Todos os chunks com dados corretos
    for obj in inseridos:
        assert obj.escritorio_id == 42
        assert obj.tipo == "sentenca"
        assert len(obj.embedding) == EMBEDDING_DIM


@pytest.mark.asyncio
async def test_pipeline_deduplicacao_segundo_ingest():
    """
    Segunda ingestão do mesmo texto retorna duplicata=True sem inserir no banco
    e sem chamar gerar_batch.
    """
    from feature_1_ia_personalizada.services.rag.ingestion import DocumentoIngester

    inseridos = []

    class _FakeSessionComDocumento:
        async def execute(self, stmt):
            class _R:
                def scalar(self):
                    return 99  # ID existente — é duplicata

            return _R()

        def add_all(self, objs):
            inseridos.extend(objs)

        async def commit(self):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    class _FakeFactory:
        def __call__(self):
            return _FakeSessionComDocumento()

    emb_mock = AsyncMock()

    with patch("feature_1_ia_personalizada.services.rag.ingestion.settings") as mock_settings:
        mock_settings.ANTHROPIC_API_KEY = "fake-key"
        ingester = DocumentoIngester(
            embedding_generator=emb_mock,
            session_factory=_FakeFactory(),
        )
        resultado = await ingester.ingerir_texto(
            texto="Texto jurídico qualquer sobre contrato de locação.",
            escritorio_id=1,
            titulo="Contrato",
            tipo="peticao",
        )

    assert resultado.duplicata is True
    assert resultado.sucesso is False
    assert inseridos == []
    emb_mock.gerar_batch.assert_not_called()
