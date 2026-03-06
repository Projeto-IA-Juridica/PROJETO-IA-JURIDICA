import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_login_success(
    async_client: AsyncClient,
    db_session: AsyncSession,
    usuario_factory,
    escritorio_factory,
):
    """Testa login com credenciais válidas retornando tokens."""
    escritorio = await escritorio_factory()
    await usuario_factory(
        escritorio_id=escritorio.id,
        email="login@teste.com",
        senha_plana="SenhaValida123",
    )

    response = await async_client.post(
        "/auth/login", json={"email": "login@teste.com", "senha": "SenhaValida123"}
    )

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_invalid_password(
    async_client: AsyncClient, usuario_factory, escritorio_factory
):
    """Testa login com senha incorreta."""
    escritorio = await escritorio_factory()
    await usuario_factory(
        escritorio_id=escritorio.id,
        email="login2@teste.com",
        senha_plana="SenhaValida123",
    )

    response = await async_client.post(
        "/auth/login", json={"email": "login2@teste.com", "senha": "SenhaErrada!"}
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "E-mail ou senha incorretos."


@pytest.mark.asyncio
async def test_login_nonexistent_user(async_client: AsyncClient):
    """Testa login com e-mail que não existe."""
    response = await async_client.post(
        "/auth/login", json={"email": "naoexiste@teste.com", "senha": "Qualquerso123"}
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_success(
    async_client: AsyncClient,
    db_session: AsyncSession,
    usuario_factory,
    escritorio_factory,
):
    """Testa a renovação do token de acesso usando um refresh token válido."""
    escritorio = await escritorio_factory()
    usuario = await usuario_factory(escritorio_id=escritorio.id)

    # 1. Faz login para pegar o refresh token original
    login_response = await async_client.post(
        "/auth/login", json={"email": usuario.email, "senha": "Senha123!"}
    )
    refresh_token = login_response.json()["refresh_token"]

    # 2. Bate na rota de refresh
    response = await async_client.post(
        "/auth/refresh", headers={"Authorization": f"Bearer {refresh_token}"}
    )

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data


@pytest.mark.asyncio
async def test_refresh_token_invalid_type(
    async_client: AsyncClient,
    db_session: AsyncSession,
    usuario_factory,
    escritorio_factory,
):
    """Testa endpoint de refresh usando um access_token no lugar de um refresh_token."""
    escritorio = await escritorio_factory()
    usuario = await usuario_factory(escritorio_id=escritorio.id)

    login_response = await async_client.post(
        "/auth/login", json={"email": usuario.email, "senha": "Senha123!"}
    )
    access_token = login_response.json()["access_token"]

    # Tenta usar o access_token onde deveria ser um refresh_token
    response = await async_client.post(
        "/auth/refresh", headers={"Authorization": f"Bearer {access_token}"}
    )

    assert response.status_code == 401
    assert "Token fornecido não é um Refresh Token" in response.json()["detail"]


@pytest.mark.asyncio
async def test_get_me_success(async_client: AsyncClient, usuario_factory, escritorio_factory):
    """Testa acesso à rota protegida /auth/me com token válido."""
    escritorio = await escritorio_factory()
    usuario = await usuario_factory(escritorio_id=escritorio.id, nome="João Advogado")

    login_response = await async_client.post(
        "/auth/login", json={"email": usuario.email, "senha": "Senha123!"}
    )
    access_token = login_response.json()["access_token"]

    response = await async_client.get(
        "/auth/me", headers={"Authorization": f"Bearer {access_token}"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["email"] == usuario.email
    assert data["nome"] == "João Advogado"


@pytest.mark.asyncio
async def test_get_me_unauthorized(async_client: AsyncClient):
    """Testa acesso à rota protegida /auth/me sem enviar token."""
    response = await async_client.get("/auth/me")
    assert response.status_code == 401
