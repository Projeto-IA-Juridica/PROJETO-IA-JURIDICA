"""
Testes de integração para GET /chat/stats/dashboard.

Estratégia:
  - CalculadoraAnalytics é mockada para evitar queries PostgreSQL-específicas
    (date_trunc) que não funcionam no SQLite de testes.
  - get_redis é substituído por FakeAnalyticsRedis em memória.
  - get_db é substituído por AsyncMock — evita criar tabelas JSONB no SQLite.
  - Testa: estrutura do payload, parâmetro ?dias=, cache hit/miss, 422 para
    parâmetros inválidos e exportação CSV.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from feature_1_ia_personalizada.api.routes.chat import get_redis
from shared.database.session import get_db

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeAnalyticsRedis:
    """Redis em memória mínimo para testar cache do dashboard."""

    def __init__(self):
        self._store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self._store[key] = value

    async def aclose(self) -> None:
        pass


_RESUMO_FAKE = {
    "total_interacoes": 100,
    "clientes_ativos": 15,
    "nps_medio": 4.1,
    "nps_anterior": 3.9,
    "variacao_nps": "+0.2",
}

_EFICIENCIA_FAKE = {
    "tempo_resposta_medio_ms": 1200,
    "interacoes_sem_humano": 70,
    "percentual_autonomia": 70.0,
    "horas_economizadas_estimadas": 9.3,
    "custo_total_usd": 0.85,
}

_TENDENCIA_FAKE = [
    {"semana": "2026-W10", "total_interacoes": 25, "nps_medio": 4.0, "autonomia_pct": 68.0},
]

_RANKING_FAKE = [
    {
        "cliente_id": 1,
        "nome": "João",
        "nps_medio": 2.5,
        "total_interacoes": 5,
        "ultimo_contato": "2026-01-01T00:00:00+00:00",
        "em_risco": True,
        "sem_avaliacao": False,
    }
]


def _patch_calculadora(monkeypatch=None):
    """Retorna context managers que mocka CalculadoraAnalytics."""
    mock_calc = AsyncMock()
    mock_calc.obter_resumo.return_value = _RESUMO_FAKE
    mock_calc.obter_eficiencia.return_value = _EFICIENCIA_FAKE
    mock_calc.tendencia_semanal.return_value = _TENDENCIA_FAKE
    mock_calc.ranking_clientes.return_value = _RANKING_FAKE

    return patch(
        "feature_1_ia_personalizada.api.routes.chat.CalculadoraAnalytics",
        return_value=mock_calc,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_ESCRITORIO_ID = 42  # ID fixo — sem banco real nestes testes


@pytest.fixture
async def app_client():
    """
    AsyncClient sem banco real — get_db e get_redis completamente mockados.
    Evita criar tabelas JSONB incompatíveis com SQLite.
    """
    from feature_1_ia_personalizada.api.app import app
    from shared.security.jwt import criar_token

    mock_db = AsyncMock()
    mock_db.execute.return_value = AsyncMock(all=lambda: [])
    mock_escritorio = MagicMock()
    mock_escritorio.assinatura_status = "trialing"
    mock_db.get.return_value = mock_escritorio
    redis_store = _FakeAnalyticsRedis()

    async def _override_db():
        yield mock_db

    async def _override_redis():
        yield redis_store

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_redis] = _override_redis

    token = criar_token(user_id=1, escritorio_id=_ESCRITORIO_ID, role="admin")

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {token}"},
    ) as client:
        yield client, redis_store

    app.dependency_overrides.clear()


@pytest.fixture
async def app_client_sem_auth():
    """Client sem token de autenticação."""
    from feature_1_ia_personalizada.api.app import app

    mock_db = AsyncMock()
    redis_store = _FakeAnalyticsRedis()

    async def _override_db():
        yield mock_db

    async def _override_redis():
        yield redis_store

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_redis] = _override_redis

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Testes de estrutura do payload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dashboard_retorna_estrutura_completa(app_client):
    """GET /chat/stats/dashboard retorna todos os campos esperados."""
    client, _ = app_client

    with (
        _patch_calculadora(),
        patch("feature_1_ia_personalizada.api.routes.chat._atualizar_metricas_prometheus"),
    ):
        response = await client.get("/chat/stats/dashboard")

    assert response.status_code == 200
    data = response.json()

    assert "resumo" in data
    assert "eficiencia" in data
    assert "por_cliente" in data
    assert "tendencia_semanal" in data
    assert "score_risco_distribuicao" in data

    assert data["resumo"]["total_interacoes"] == 100
    assert data["resumo"]["nps_medio"] == 4.1
    assert data["resumo"]["variacao_nps"] == "+0.2"
    assert data["eficiencia"]["percentual_autonomia"] == 70.0
    assert data["tendencia_semanal"][0]["semana"] == "2026-W10"
    assert data["por_cliente"][0]["em_risco"] is True
    assert data["por_cliente"][0]["sem_avaliacao"] is False


# ---------------------------------------------------------------------------
# Testes de parâmetro ?dias=
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dashboard_dias_7(app_client):
    """`?dias=7` é aceito e passado à calculadora."""
    client, _ = app_client

    with (
        _patch_calculadora() as mock_cls,
        patch("feature_1_ia_personalizada.api.routes.chat._atualizar_metricas_prometheus"),
    ):
        response = await client.get("/chat/stats/dashboard?dias=7")
        mock_cls.assert_called_once()
        # Terceiro argumento posicional ou kwarg dias=7
        call_args = mock_cls.call_args
        dias_passado = call_args.kwargs.get("dias") or call_args.args[2]
        assert dias_passado == 7

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_dashboard_dias_invalido_retorna_422(app_client):
    """`?dias=15` não é valor permitido → 422."""
    client, _ = app_client
    response = await client.get("/chat/stats/dashboard?dias=15")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_dashboard_sem_autenticacao_retorna_401(app_client_sem_auth):
    """Sem token → 401."""
    response = await app_client_sem_auth.get("/chat/stats/dashboard")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Testes de cache Redis
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dashboard_cache_miss_e_hit(app_client):
    """Primeira chamada (miss) calcula; segunda (hit) retorna do cache."""
    client, _ = app_client

    with (
        _patch_calculadora() as mock_cls,
        patch("feature_1_ia_personalizada.api.routes.chat._atualizar_metricas_prometheus"),
    ):
        r1 = await client.get("/chat/stats/dashboard?dias=30")
        assert r1.status_code == 200
        assert mock_cls.called

        mock_cls.reset_mock()

        r2 = await client.get("/chat/stats/dashboard?dias=30")
        assert r2.status_code == 200
        assert not mock_cls.called  # cache hit — calculadora não chamada

    assert r1.json()["resumo"]["total_interacoes"] == r2.json()["resumo"]["total_interacoes"]


@pytest.mark.asyncio
async def test_dashboard_cache_separado_por_dias(app_client):
    """`?dias=7` e `?dias=30` usam chaves de cache distintas."""
    client, _ = app_client

    with (
        _patch_calculadora() as mock_cls,
        patch("feature_1_ia_personalizada.api.routes.chat._atualizar_metricas_prometheus"),
    ):
        await client.get("/chat/stats/dashboard?dias=30")
        await client.get("/chat/stats/dashboard?dias=7")
        assert mock_cls.call_count == 2  # chaves distintas, sem cache hit cruzado


# ---------------------------------------------------------------------------
# Testes de exportação CSV
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_csv_formato_invalido(app_client):
    """formato=pdf → 422."""
    client, _ = app_client
    response = await client.get("/chat/stats/export?mes=2026-03&formato=pdf")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_export_csv_mes_ausente(app_client):
    """Sem ?mes → 422."""
    client, _ = app_client
    response = await client.get("/chat/stats/export?formato=csv")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_export_csv_mes_invalido(app_client):
    """?mes=2026-3 (sem zero) → 422."""
    client, _ = app_client

    with patch("feature_1_ia_personalizada.api.routes.chat.ExportadorAnalytics") as mock_exp:
        mock_exp.return_value.gerar_csv.side_effect = ValueError("Formato inválido")
        response = await client.get("/chat/stats/export?mes=2026-3")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_export_csv_retorna_arquivo(app_client):
    """CSV gerado corretamente → Content-Disposition com nome do arquivo."""
    client, _ = app_client
    csv_bytes = b"id,data\n1,2026-03-01\n"

    with patch("feature_1_ia_personalizada.api.routes.chat.ExportadorAnalytics") as mock_exp:
        mock_exp.return_value.gerar_csv = AsyncMock(return_value=csv_bytes)
        response = await client.get("/chat/stats/export?mes=2026-03&formato=csv")

    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "resumo_clientes_2026-03.csv" in response.headers["content-disposition"]
    assert response.content == csv_bytes
