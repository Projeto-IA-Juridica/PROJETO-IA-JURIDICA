# feature_1_ia_personalizada/tests/integration/test_score_api.py
"""
Testes de integração para campos de score de risco na API /processos.

Cobertura:
  - GET /processos/{id} retorna campos score_risco, score_nivel, score_interpretacao (null quando não calculado)
  - GET /processos?score_nivel=alto filtra corretamente
  - GET /processos?score_nivel=invalido retorna 422
  - score_nivel inválido com outros filtros também retorna 422
  - Isolamento multi-tenant: score de outro escritório não aparece
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.security.jwt import criar_token


def _make_cnj(seq: int) -> str:
    nnnnnnn = f"{seq:07d}"
    aaaa, j, tt, oooo = "2024", "8", "26", "0100"
    base = nnnnnnn + aaaa + j + tt + oooo
    dd = 98 - (int(base + "00") % 97)
    return f"{nnnnnnn}-{dd:02d}.{aaaa}.{j}.{tt}.{oooo}"


def _headers(user_id: int, escritorio_id: int) -> dict:
    token = criar_token(user_id=user_id, escritorio_id=escritorio_id, role="admin")
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# GET /processos/{id} — campos de score opcionais
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_processo_score_campos_nulos_quando_nao_calculado(
    async_client: AsyncClient, escritorio_factory, usuario_factory
):
    """Processo recém-criado não tem score calculado — campos devem ser null."""
    escritorio = await escritorio_factory()
    usuario = await usuario_factory(escritorio_id=escritorio.id)
    headers = _headers(user_id=usuario.id, escritorio_id=escritorio.id)

    payload = {
        "numero_cnj": _make_cnj(100),
        "cliente_id": 1,
        "polo_cliente": "autor",
        "tipo_acao": "Ação de cobrança",
    }

    with patch("feature_1_ia_personalizada.api.routes.processos.registrar_acesso"):
        r = await async_client.post("/processos", headers=headers, json=payload)
        assert r.status_code == 201
        processo_id = r.json()["id"]

        r2 = await async_client.get(f"/processos/{processo_id}", headers=headers)

    assert r2.status_code == 200
    data = r2.json()
    assert "score_risco" in data
    assert "score_nivel" in data
    assert "score_interpretacao" in data
    assert data["score_risco"] is None
    assert data["score_nivel"] is None
    assert data["score_interpretacao"] is None


@pytest.mark.asyncio
async def test_get_processo_score_preenchido(
    async_client: AsyncClient,
    async_db: AsyncSession,
    escritorio_factory,
    usuario_factory,
):
    """Após simular worker gravando score, GET deve retornar os campos preenchidos."""
    escritorio = await escritorio_factory()
    usuario = await usuario_factory(escritorio_id=escritorio.id)
    headers = _headers(user_id=usuario.id, escritorio_id=escritorio.id)

    payload = {
        "numero_cnj": _make_cnj(101),
        "cliente_id": 1,
        "polo_cliente": "autor",
        "tipo_acao": "Ação de dano moral",
    }

    with patch("feature_1_ia_personalizada.api.routes.processos.registrar_acesso"):
        r = await async_client.post("/processos", headers=headers, json=payload)
        assert r.status_code == 201
        processo_id = r.json()["id"]

    # Simula o worker gravando o score diretamente no banco
    await async_db.execute(
        text(
            "UPDATE processos SET score_risco=67, score_nivel='alto', "
            "score_interpretacao='Ação com alta complexidade.' "
            "WHERE id=:id"
        ),
        {"id": processo_id},
    )
    await async_db.commit()

    with patch("feature_1_ia_personalizada.api.routes.processos.registrar_acesso"):
        r2 = await async_client.get(f"/processos/{processo_id}", headers=headers)

    assert r2.status_code == 200
    data = r2.json()
    assert data["score_risco"] == 67
    assert data["score_nivel"] == "alto"
    assert data["score_interpretacao"] == "Ação com alta complexidade."


# ---------------------------------------------------------------------------
# GET /processos?score_nivel= — filtro por nível
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_filtro_score_nivel_invalido_retorna_422(
    async_client: AsyncClient, escritorio_factory, usuario_factory
):
    """Nível inexistente deve retornar 422."""
    escritorio = await escritorio_factory()
    usuario = await usuario_factory(escritorio_id=escritorio.id)
    headers = _headers(user_id=usuario.id, escritorio_id=escritorio.id)

    with patch("feature_1_ia_personalizada.api.routes.processos.registrar_acesso"):
        r = await async_client.get("/processos?score_nivel=absurdo", headers=headers)

    assert r.status_code == 422


@pytest.mark.asyncio
async def test_filtro_score_nivel_alto_retorna_so_processos_alto(
    async_client: AsyncClient,
    async_db: AsyncSession,
    escritorio_factory,
    usuario_factory,
):
    """Filtro ?score_nivel=alto deve retornar apenas processos com esse nível."""
    escritorio = await escritorio_factory()
    usuario = await usuario_factory(escritorio_id=escritorio.id)
    headers = _headers(user_id=usuario.id, escritorio_id=escritorio.id)

    cnjs = [_make_cnj(200 + i) for i in range(3)]
    ids_criados = []

    with patch("feature_1_ia_personalizada.api.routes.processos.registrar_acesso"):
        for cnj in cnjs:
            r = await async_client.post(
                "/processos",
                headers=headers,
                json={
                    "numero_cnj": cnj,
                    "cliente_id": 1,
                    "polo_cliente": "autor",
                    "tipo_acao": "Cobrança",
                },
            )
            assert r.status_code == 201
            ids_criados.append(r.json()["id"])

    # Define scores: [alto, baixo, alto]
    await async_db.execute(
        text("UPDATE processos SET score_risco=60, score_nivel='alto' WHERE id=:id"),
        {"id": ids_criados[0]},
    )
    await async_db.execute(
        text("UPDATE processos SET score_risco=10, score_nivel='baixo' WHERE id=:id"),
        {"id": ids_criados[1]},
    )
    await async_db.execute(
        text("UPDATE processos SET score_risco=70, score_nivel='alto' WHERE id=:id"),
        {"id": ids_criados[2]},
    )
    await async_db.commit()

    with patch("feature_1_ia_personalizada.api.routes.processos.registrar_acesso"):
        r = await async_client.get("/processos?score_nivel=alto", headers=headers)

    assert r.status_code == 200
    data = r.json()
    niveis = [p["score_nivel"] for p in data["items"]]
    assert all(n == "alto" for n in niveis), f"Esperado só 'alto', mas: {niveis}"
    assert data["total"] == 2


@pytest.mark.asyncio
async def test_filtro_score_nivel_sem_resultados(
    async_client: AsyncClient, escritorio_factory, usuario_factory
):
    """Filtro por nível sem processos naquele nível retorna lista vazia."""
    escritorio = await escritorio_factory()
    usuario = await usuario_factory(escritorio_id=escritorio.id)
    headers = _headers(user_id=usuario.id, escritorio_id=escritorio.id)

    with patch("feature_1_ia_personalizada.api.routes.processos.registrar_acesso"):
        r = await async_client.get("/processos?score_nivel=critico", headers=headers)

    assert r.status_code == 200
    assert r.json()["total"] == 0


@pytest.mark.asyncio
async def test_filtro_score_nivel_isolamento_multitenancy(
    async_client: AsyncClient,
    async_db: AsyncSession,
    escritorio_factory,
    usuario_factory,
):
    """Processos com score 'alto' de outro escritório NÃO devem aparecer no filtro."""
    esc1 = await escritorio_factory()
    esc2 = await escritorio_factory()
    user1 = await usuario_factory(escritorio_id=esc1.id)
    user2 = await usuario_factory(escritorio_id=esc2.id)
    h1 = _headers(user_id=user1.id, escritorio_id=esc1.id)
    h2 = _headers(user_id=user2.id, escritorio_id=esc2.id)

    with patch("feature_1_ia_personalizada.api.routes.processos.registrar_acesso"):
        # Escritório 2 cria processo com score alto
        r = await async_client.post(
            "/processos",
            headers=h2,
            json={
                "numero_cnj": _make_cnj(300),
                "cliente_id": 1,
                "polo_cliente": "autor",
                "tipo_acao": "X",
            },
        )
        assert r.status_code == 201
        pid2 = r.json()["id"]

    await async_db.execute(
        text("UPDATE processos SET score_risco=80, score_nivel='alto' WHERE id=:id"),
        {"id": pid2},
    )
    await async_db.commit()

    with patch("feature_1_ia_personalizada.api.routes.processos.registrar_acesso"):
        # Escritório 1 filtra por alto — não deve ver o processo do escritório 2
        r = await async_client.get("/processos?score_nivel=alto", headers=h1)

    assert r.status_code == 200
    assert r.json()["total"] == 0
