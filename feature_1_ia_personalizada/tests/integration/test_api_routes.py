"""
PIJ-201: Testes HTTP das rotas FastAPI
Garante comportamento de rotas /health, /auth, /chat, /webhook e /metrics.
"""

from unittest.mock import patch

import pytest
from httpx import AsyncClient

from shared.config.settings import settings


@pytest.mark.asyncio
async def test_get_health(async_client: AsyncClient):
    """Testar GET /health → 200"""
    response = await async_client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_get_health_ready_up(async_client: AsyncClient):
    """Testar GET /health/ready → 200 (com DB/Redis mockados como up)"""
    with (
        patch(
            "feature_1_ia_personalizada.api.routes.health._check_postgresql",
            return_value={"status": "ok", "latency_ms": 10},
        ),
        patch(
            "feature_1_ia_personalizada.api.routes.health._check_redis",
            return_value={"status": "ok", "latency_ms": 5},
        ),
    ):
        response = await async_client.get("/health/ready")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_get_health_ready_down(async_client: AsyncClient):
    """Testar GET /health/ready → 503 (com DB mockado como down)"""
    with (
        patch(
            "feature_1_ia_personalizada.api.routes.health._check_postgresql",
            return_value={"status": "error", "detail": "Connection failed"},
        ),
        patch(
            "feature_1_ia_personalizada.api.routes.health._check_redis",
            return_value={"status": "ok", "latency_ms": 5},
        ),
    ):
        response = await async_client.get("/health/ready")
        assert response.status_code == 503
        assert response.json()["status"] == "error"


@pytest.mark.asyncio
async def test_post_auth_login_success(
    async_client: AsyncClient, usuario_factory, escritorio_factory
):
    """Testar POST /auth/login com credenciais válidas → 200 + tokens"""
    escritorio = await escritorio_factory()
    await usuario_factory(
        escritorio_id=escritorio.id,
        email="login_correto@api.com",
        senha_plana="Senha!123",
    )

    response = await async_client.post(
        "/auth/login", json={"email": "login_correto@api.com", "senha": "Senha!123"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data


@pytest.mark.asyncio
async def test_post_auth_login_invalid(
    async_client: AsyncClient, usuario_factory, escritorio_factory
):
    """Testar POST /auth/login com senha errada → 401"""
    escritorio = await escritorio_factory()
    await usuario_factory(
        escritorio_id=escritorio.id,
        email="login_errado@api.com",
        senha_plana="Senha!123",
    )

    response = await async_client.post(
        "/auth/login", json={"email": "login_errado@api.com", "senha": "SenhaErrada!"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_chat_history_unauthorized(async_client: AsyncClient):
    """Testar GET /chat/history/{id} sem token → 401"""
    response = await async_client.get("/chat/history/1")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_chat_history_authorized_not_found(
    async_client: AsyncClient, usuario_factory, escritorio_factory
):
    """Testar GET /chat/history/{id} com token válido mas cliente inexistente → 404"""
    escritorio = await escritorio_factory()
    await usuario_factory(
        escritorio_id=escritorio.id, email="chat_auth@api.com", senha_plana="Senha!123"
    )

    login = await async_client.post(
        "/auth/login", json={"email": "chat_auth@api.com", "senha": "Senha!123"}
    )
    token = login.json()["access_token"]

    response = await async_client.get(
        "/chat/history/9999", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 404
    assert "Cliente não encontrado" in response.json()["detail"]


@pytest.mark.asyncio
async def test_post_webhook_missing_apikey(async_client: AsyncClient):
    """Testar POST /webhook/whatsapp sem header apikey → 401"""
    response = await async_client.post("/webhook/whatsapp", json={"event": "status.ignored"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_post_webhook_valid_payload_and_apikey(async_client: AsyncClient):
    """Testar POST /webhook/whatsapp com payload válido e apikey correto → 200"""
    response = await async_client.post(
        "/webhook/whatsapp",
        headers={"apikey": settings.EVOLUTION_API_KEY},
        json={"event": "status.ignored"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"


@pytest.mark.asyncio
async def test_get_metrics(async_client: AsyncClient):
    """Testar GET /metrics → 200 com content-type Prometheus"""
    response = await async_client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "python_gc_objects" in response.text or "process_virtual_memory_bytes" in response.text


@pytest.mark.asyncio
async def test_get_admin_import_page(async_client: AsyncClient):
    """Testar GET /admin/import → 200 (servimento de HTML estático)"""
    # Nota: Assumindo que o arquivo static/import.html existe (foi visto no routes/admin_import.py)
    response = await async_client.get("/admin/import")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


@pytest.mark.asyncio
async def test_post_import_clientes_unauthorized(async_client: AsyncClient):
    """Testar POST /admin/import/clientes sem token → 401"""
    response = await async_client.post("/admin/import/clientes")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_post_import_clientes_success_preview(
    async_client: AsyncClient, usuario_factory, escritorio_factory
):
    """Testar POST /admin/import/clientes com token válido (modo preview) → 200"""
    escritorio = await escritorio_factory()
    usuario = await usuario_factory(escritorio_id=escritorio.id)

    login = await async_client.post(
        "/auth/login", json={"email": usuario.email, "senha": "Senha123!"}
    )
    token = login.json()["access_token"]

    csv_content = b"nome,telefone\nJoao,5511999999999\n"
    files = {"file": ("clientes.csv", csv_content, "text/csv")}

    with patch(
        "feature_1_ia_personalizada.api.routes.admin_import.processar_csv",
        return_value={"importados": 1, "preview": [{"nome": "Joao"}]},
    ):
        response = await async_client.post(
            "/admin/import/clientes?preview=true",
            headers={"Authorization": f"Bearer {token}"},
            files=files,
        )

    assert response.status_code == 200
    assert response.json()["importados"] == 1


@pytest.mark.asyncio
async def test_post_chat_send_proactive_success(
    async_client: AsyncClient, usuario_factory, escritorio_factory, cliente_factory
):
    """Testar POST /chat/send/{id} → 202 status enfileirado"""
    escritorio = await escritorio_factory()
    usuario = await usuario_factory(escritorio_id=escritorio.id)
    cliente = await cliente_factory(escritorio_id=escritorio.id)

    login = await async_client.post(
        "/auth/login", json={"email": usuario.email, "senha": "Senha123!"}
    )
    token = login.json()["access_token"]

    with patch(
        "feature_1_ia_personalizada.api.routes.chat.processar_mensagem_recebida"
    ) as mock_celery:
        response = await async_client.post(
            f"/chat/send/{cliente.id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"mensagem": "Olá, tudo bem?"},
        )
        assert response.status_code == 202
        assert response.json()["status"] == "enfileirado"
        mock_celery.delay.assert_called_once()


@pytest.mark.asyncio
async def test_get_chat_stats_dashboard(
    async_client: AsyncClient, usuario_factory, escritorio_factory
):
    """Testar GET /chat/stats/dashboard → 200"""
    escritorio = await escritorio_factory()
    usuario = await usuario_factory(escritorio_id=escritorio.id)

    login = await async_client.post(
        "/auth/login", json={"email": usuario.email, "senha": "Senha123!"}
    )
    token = login.json()["access_token"]

    response = await async_client.get(
        "/chat/stats/dashboard", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "total_interacoes" in data.get("resumo", data)
    assert "custo_total_usd" in data.get("eficiencia", data)
