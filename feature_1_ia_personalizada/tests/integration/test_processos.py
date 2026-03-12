# feature_1_ia_personalizada/tests/integration/test_processos.py
"""
Testes de integração para as rotas /processos.
Usa async_client com DB in-memory SQLite, autenticado via JWT.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import AsyncClient

from shared.security.jwt import criar_token


def _make_cnj(seq: int = 1) -> str:
    """Gera um CNJ com dígito verificador válido."""
    nnnnnnn = f"{seq:07d}"
    aaaa, j, tt, oooo = "2024", "8", "26", "0100"
    base = nnnnnnn + aaaa + j + tt + oooo
    dd = 98 - (int(base + "00") % 97)
    return f"{nnnnnnn}-{dd:02d}.{aaaa}.{j}.{tt}.{oooo}"


def _auth_headers(user_id: int, escritorio_id: int) -> dict:
    token = criar_token(user_id=user_id, escritorio_id=escritorio_id, role="admin")
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_list_processos_sem_auth_retorna_401(async_client: AsyncClient):
    response = await async_client.get("/processos")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_processos_vazio(async_client: AsyncClient, escritorio_factory, usuario_factory):
    escritorio = await escritorio_factory()
    usuario = await usuario_factory(escritorio_id=escritorio.id)
    headers = _auth_headers(user_id=usuario.id, escritorio_id=escritorio.id)

    with patch("feature_1_ia_personalizada.api.routes.processos.registrar_acesso"):
        response = await async_client.get("/processos", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_create_processo_sucesso(
    async_client: AsyncClient, escritorio_factory, usuario_factory
):
    escritorio = await escritorio_factory()
    usuario = await usuario_factory(escritorio_id=escritorio.id)
    headers = _auth_headers(user_id=usuario.id, escritorio_id=escritorio.id)

    payload = {
        "numero_cnj": _make_cnj(1),
        "cliente_id": 999,
        "polo_cliente": "autor",
        "tipo_acao": "Ação de cobrança",
    }

    with patch("feature_1_ia_personalizada.api.routes.processos.registrar_acesso"):
        response = await async_client.post("/processos", headers=headers, json=payload)

    assert response.status_code == 201
    data = response.json()
    assert data["numero_cnj"] == payload["numero_cnj"]
    assert data["status"] == "ativo"


@pytest.mark.asyncio
async def test_create_processo_duplicado_retorna_400(
    async_client: AsyncClient, escritorio_factory, usuario_factory
):
    escritorio = await escritorio_factory()
    usuario = await usuario_factory(escritorio_id=escritorio.id)
    headers = _auth_headers(user_id=usuario.id, escritorio_id=escritorio.id)

    cnj = _make_cnj(2)
    payload = {
        "numero_cnj": cnj,
        "cliente_id": 999,
        "polo_cliente": "autor",
        "tipo_acao": "Cobrança",
    }

    with patch("feature_1_ia_personalizada.api.routes.processos.registrar_acesso"):
        # Primeiro cadastro
        r1 = await async_client.post("/processos", headers=headers, json=payload)
        assert r1.status_code == 201

        # Tentativa duplicada
        r2 = await async_client.post("/processos", headers=headers, json=payload)
        assert r2.status_code == 400
        assert "CNJ" in r2.json()["detail"] or "cadastrado" in r2.json()["detail"]


@pytest.mark.asyncio
async def test_get_processo_existente(
    async_client: AsyncClient, escritorio_factory, usuario_factory
):
    escritorio = await escritorio_factory()
    usuario = await usuario_factory(escritorio_id=escritorio.id)
    headers = _auth_headers(user_id=usuario.id, escritorio_id=escritorio.id)

    cnj = _make_cnj(3)
    payload = {
        "numero_cnj": cnj,
        "cliente_id": 999,
        "polo_cliente": "reu",
        "tipo_acao": "Dano moral",
    }

    with patch("feature_1_ia_personalizada.api.routes.processos.registrar_acesso"):
        criado = await async_client.post("/processos", headers=headers, json=payload)
        processo_id = criado.json()["id"]

        response = await async_client.get(f"/processos/{processo_id}", headers=headers)

    assert response.status_code == 200
    assert response.json()["id"] == processo_id


@pytest.mark.asyncio
async def test_get_processo_nao_encontrado_retorna_404(
    async_client: AsyncClient, escritorio_factory, usuario_factory
):
    escritorio = await escritorio_factory()
    usuario = await usuario_factory(escritorio_id=escritorio.id)
    headers = _auth_headers(user_id=usuario.id, escritorio_id=escritorio.id)

    with patch("feature_1_ia_personalizada.api.routes.processos.registrar_acesso"):
        response = await async_client.get("/processos/99999", headers=headers)

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_processo_de_outro_escritorio_retorna_404(
    async_client: AsyncClient, escritorio_factory, usuario_factory
):
    """Multi-tenant: não pode ver processos de outro escritório."""
    esc1 = await escritorio_factory()
    esc2 = await escritorio_factory()
    user1 = await usuario_factory(escritorio_id=esc1.id)
    user2 = await usuario_factory(escritorio_id=esc2.id)
    headers1 = _auth_headers(user_id=user1.id, escritorio_id=esc1.id)
    headers2 = _auth_headers(user_id=user2.id, escritorio_id=esc2.id)

    cnj = _make_cnj(10)
    payload = {
        "numero_cnj": cnj,
        "cliente_id": 1,
        "polo_cliente": "autor",
        "tipo_acao": "Teste",
    }

    with patch("feature_1_ia_personalizada.api.routes.processos.registrar_acesso"):
        criado = await async_client.post("/processos", headers=headers1, json=payload)
        processo_id = criado.json()["id"]

        # Usuário do escritório 2 não deve ver processo do escritório 1
        response = await async_client.get(f"/processos/{processo_id}", headers=headers2)

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_processo(async_client: AsyncClient, escritorio_factory, usuario_factory):
    escritorio = await escritorio_factory()
    usuario = await usuario_factory(escritorio_id=escritorio.id)
    headers = _auth_headers(user_id=usuario.id, escritorio_id=escritorio.id)

    cnj = _make_cnj(4)
    payload = {
        "numero_cnj": cnj,
        "cliente_id": 1,
        "polo_cliente": "autor",
        "tipo_acao": "Cobrança",
    }

    with patch("feature_1_ia_personalizada.api.routes.processos.registrar_acesso"):
        criado = await async_client.post("/processos", headers=headers, json=payload)
        processo_id = criado.json()["id"]

        response = await async_client.put(
            f"/processos/{processo_id}",
            headers=headers,
            json={"polo_cliente": "reu"},
        )

    assert response.status_code == 200
    assert response.json()["polo_cliente"] == "reu"


@pytest.mark.asyncio
async def test_update_processo_nao_encontrado_retorna_404(
    async_client: AsyncClient, escritorio_factory, usuario_factory
):
    escritorio = await escritorio_factory()
    usuario = await usuario_factory(escritorio_id=escritorio.id)
    headers = _auth_headers(user_id=usuario.id, escritorio_id=escritorio.id)

    with patch("feature_1_ia_personalizada.api.routes.processos.registrar_acesso"):
        response = await async_client.put(
            "/processos/99999", headers=headers, json={"polo_cliente": "reu"}
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_processo_soft_delete(
    async_client: AsyncClient, escritorio_factory, usuario_factory
):
    escritorio = await escritorio_factory()
    usuario = await usuario_factory(escritorio_id=escritorio.id)
    headers = _auth_headers(user_id=usuario.id, escritorio_id=escritorio.id)

    cnj = _make_cnj(5)
    payload = {
        "numero_cnj": cnj,
        "cliente_id": 1,
        "polo_cliente": "autor",
        "tipo_acao": "Teste",
    }

    with patch("feature_1_ia_personalizada.api.routes.processos.registrar_acesso"):
        criado = await async_client.post("/processos", headers=headers, json=payload)
        processo_id = criado.json()["id"]

        response = await async_client.delete(f"/processos/{processo_id}", headers=headers)

    assert response.status_code == 204


@pytest.mark.asyncio
async def test_delete_processo_nao_encontrado_retorna_404(
    async_client: AsyncClient, escritorio_factory, usuario_factory
):
    escritorio = await escritorio_factory()
    usuario = await usuario_factory(escritorio_id=escritorio.id)
    headers = _auth_headers(user_id=usuario.id, escritorio_id=escritorio.id)

    with patch("feature_1_ia_personalizada.api.routes.processos.registrar_acesso"):
        response = await async_client.delete("/processos/99999", headers=headers)

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_processos_com_filtro_status(
    async_client: AsyncClient, escritorio_factory, usuario_factory
):
    escritorio = await escritorio_factory()
    usuario = await usuario_factory(escritorio_id=escritorio.id)
    headers = _auth_headers(user_id=usuario.id, escritorio_id=escritorio.id)

    cnj = _make_cnj(6)
    payload = {
        "numero_cnj": cnj,
        "cliente_id": 1,
        "polo_cliente": "autor",
        "tipo_acao": "Teste",
    }

    with patch("feature_1_ia_personalizada.api.routes.processos.registrar_acesso"):
        await async_client.post("/processos", headers=headers, json=payload)

        response = await async_client.get("/processos?status=ativo", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert all(p["status"] == "ativo" for p in data["items"])


@pytest.mark.asyncio
async def test_list_processos_com_busca_cnj(
    async_client: AsyncClient, escritorio_factory, usuario_factory
):
    escritorio = await escritorio_factory()
    usuario = await usuario_factory(escritorio_id=escritorio.id)
    headers = _auth_headers(user_id=usuario.id, escritorio_id=escritorio.id)

    cnj = _make_cnj(7)
    payload = {
        "numero_cnj": cnj,
        "cliente_id": 1,
        "polo_cliente": "autor",
        "tipo_acao": "Teste",
    }

    with patch("feature_1_ia_personalizada.api.routes.processos.registrar_acesso"):
        await async_client.post("/processos", headers=headers, json=payload)

        # busca pelos primeiros 7 dígitos do CNJ
        parcial = cnj[:7]
        response = await async_client.get(f"/processos?search={parcial}", headers=headers)
        assert response.status_code == 200
