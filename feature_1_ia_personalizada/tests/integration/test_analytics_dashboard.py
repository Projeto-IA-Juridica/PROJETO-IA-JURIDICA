"""
Testes de integração para GET /chat/stats/dashboard.

Estratégia:
  - CalculadoraAnalytics é mockada para evitar queries PostgreSQL-específicas
    (date_trunc) que não funcionam no SQLite de testes.
  - get_redis é substituído por FakeAnalyticsRedis em memória.
  - Testa: estrutura do payload, parâmetro ?dias=, cache hit/miss, 422 para
    parâmetros inválidos e exportação CSV.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from feature_1_ia_personalizada.api.routes.chat import get_redis


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


@pytest.fixture
async def client_com_auth(async_client: AsyncClient, escritorio_factory, auth_token):
    """Client autenticado com escritório criado."""
    escritorio = await escritorio_factory()
    token = auth_token(user_id=1, escritorio_id=escritorio.id)
    async_client.headers.update({"Authorization": f"Bearer {token}"})
    return async_client, escritorio


@pytest.fixture
def fake_redis():
    return _FakeAnalyticsRedis()


# ---------------------------------------------------------------------------
# Testes de estrutura do payload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dashboard_retorna_estrutura_completa(client_com_auth, fake_redis):
    """GET /chat/stats/dashboard retorna todos os campos esperados."""
    client, _ = client_com_auth

    from feature_1_ia_personalizada.api.app import app

    async def _override_redis():
        yield fake_redis

    app.dependency_overrides[get_redis] = _override_redis

    with (
        _patch_calculadora(),
        patch("feature_1_ia_personalizada.api.routes.chat._atualizar_metricas_prometheus"),
        patch(
            "feature_1_ia_personalizada.api.routes.chat.select",
            side_effect=Exception("skip score"),  # força degradação graciosa
        ),
    ):
        response = await client.get("/chat/stats/dashboard")

    app.dependency_overrides.pop(get_redis, None)

    assert response.status_code == 200
    data = response.json()

    assert "resumo" in data
    assert "eficiencia" in data
    assert "por_cliente" in data
    assert "tendencia_semanal" in data
    assert "score_risco_distribuicao" in data

    resumo = data["resumo"]
    assert resumo["total_interacoes"] == 100
    assert resumo["nps_medio"] == 4.1
    assert resumo["variacao_nps"] == "+0.2"

    eficiencia = data["eficiencia"]
    assert eficiencia["percentual_autonomia"] == 70.0

    assert len(data["tendencia_semanal"]) == 1
    assert data["tendencia_semanal"][0]["semana"] == "2026-W10"

    assert data["por_cliente"][0]["em_risco"] is True
    assert data["por_cliente"][0]["sem_avaliacao"] is False


# ---------------------------------------------------------------------------
# Testes de parâmetro ?dias=
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dashboard_dias_7(client_com_auth, fake_redis):
    """`?dias=7` é aceito e passado à calculadora."""
    client, _ = client_com_auth

    from feature_1_ia_personalizada.api.app import app

    async def _override_redis():
        yield fake_redis

    app.dependency_overrides[get_redis] = _override_redis

    with (
        _patch_calculadora() as mock_cls,
        patch("feature_1_ia_personalizada.api.routes.chat._atualizar_metricas_prometheus"),
        patch("feature_1_ia_personalizada.api.routes.chat.select", side_effect=Exception("skip")),
    ):
        response = await client.get("/chat/stats/dashboard?dias=7")
        # Verifica que CalculadoraAnalytics foi instanciada com dias=7
        mock_cls.assert_called_once()
        _, kwargs = mock_cls.call_args
        assert kwargs.get("dias") == 7 or mock_cls.call_args[0][2] == 7

    app.dependency_overrides.pop(get_redis, None)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_dashboard_dias_invalido_retorna_422(client_com_auth, fake_redis):
    """`?dias=15` não é valor permitido → 422."""
    client, _ = client_com_auth

    from feature_1_ia_personalizada.api.app import app

    async def _override_redis():
        yield fake_redis

    app.dependency_overrides[get_redis] = _override_redis

    response = await client.get("/chat/stats/dashboard?dias=15")

    app.dependency_overrides.pop(get_redis, None)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_dashboard_sem_autenticacao_retorna_401(async_client: AsyncClient, fake_redis):
    """Sem token → 401."""
    from feature_1_ia_personalizada.api.app import app

    async def _override_redis():
        yield fake_redis

    app.dependency_overrides[get_redis] = _override_redis

    response = await async_client.get("/chat/stats/dashboard")

    app.dependency_overrides.pop(get_redis, None)
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Testes de cache Redis
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dashboard_cache_miss_e_hit(client_com_auth):
    """Primeira chamada (miss) calcula; segunda (hit) retorna do cache."""
    client, escritorio = client_com_auth

    from feature_1_ia_personalizada.api.app import app

    redis_store = _FakeAnalyticsRedis()

    async def _override_redis():
        yield redis_store

    app.dependency_overrides[get_redis] = _override_redis

    with (
        _patch_calculadora() as mock_cls,
        patch("feature_1_ia_personalizada.api.routes.chat._atualizar_metricas_prometheus"),
        patch("feature_1_ia_personalizada.api.routes.chat.select", side_effect=Exception("skip")),
    ):
        # --- Cache miss ---
        r1 = await client.get("/chat/stats/dashboard?dias=30")
        assert r1.status_code == 200
        assert mock_cls.called  # calculadora foi chamada

        mock_cls.reset_mock()

        # --- Cache hit ---
        r2 = await client.get("/chat/stats/dashboard?dias=30")
        assert r2.status_code == 200
        assert not mock_cls.called  # calculadora NÃO foi chamada de novo

    app.dependency_overrides.pop(get_redis, None)

    # Payload idêntico nas duas chamadas
    assert r1.json()["resumo"]["total_interacoes"] == r2.json()["resumo"]["total_interacoes"]


@pytest.mark.asyncio
async def test_dashboard_cache_separado_por_dias(client_com_auth):
    """`?dias=7` e `?dias=30` usam chaves de cache distintas."""
    client, _ = client_com_auth

    from feature_1_ia_personalizada.api.app import app

    redis_store = _FakeAnalyticsRedis()

    async def _override_redis():
        yield redis_store

    app.dependency_overrides[get_redis] = _override_redis

    with (
        _patch_calculadora() as mock_cls,
        patch("feature_1_ia_personalizada.api.routes.chat._atualizar_metricas_prometheus"),
        patch("feature_1_ia_personalizada.api.routes.chat.select", side_effect=Exception("skip")),
    ):
        await client.get("/chat/stats/dashboard?dias=30")
        await client.get("/chat/stats/dashboard?dias=7")
        # Calculadora chamada duas vezes — chaves distintas, sem cache hit cruzado
        assert mock_cls.call_count == 2

    app.dependency_overrides.pop(get_redis, None)


# ---------------------------------------------------------------------------
# Testes de exportação CSV
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_csv_formato_invalido(client_com_auth):
    """formato=pdf → 422."""
    client, _ = client_com_auth
    response = await client.get("/chat/stats/export?mes=2026-03&formato=pdf")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_export_csv_mes_ausente(client_com_auth):
    """Sem ?mes → 422."""
    client, _ = client_com_auth
    response = await client.get("/chat/stats/export?formato=csv")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_export_csv_mes_invalido(client_com_auth):
    """?mes=2026-3 (sem zero) → 422."""
    client, _ = client_com_auth

    with patch(
        "feature_1_ia_personalizada.api.routes.chat.ExportadorAnalytics"
    ) as mock_exp:
        mock_exp.return_value.gerar_csv.side_effect = ValueError("Formato inválido")
        response = await client.get("/chat/stats/export?mes=2026-3")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_export_csv_retorna_arquivo(client_com_auth):
    """CSV gerado corretamente → Content-Disposition com nome do arquivo."""
    client, _ = client_com_auth

    csv_bytes = b"id,data\n1,2026-03-01\n"

    with patch(
        "feature_1_ia_personalizada.api.routes.chat.ExportadorAnalytics"
    ) as mock_exp:
        mock_exp.return_value.gerar_csv = AsyncMock(return_value=csv_bytes)
        response = await client.get("/chat/stats/export?mes=2026-03&formato=csv")

    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "relatorio_interacoes_2026-03.csv" in response.headers["content-disposition"]
    assert response.content == csv_bytes
