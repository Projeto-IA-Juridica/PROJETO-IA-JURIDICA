# feature_1_ia_personalizada/tests/integration/test_health_detailed.py
"""
Testes de integração para /health/detailed e funções de validação de startup do app.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_detailed_todos_ok(async_client: AsyncClient):
    """GET /health/detailed → 200 com todos os serviços mockados como ok."""
    checks_ok = {"status": "ok", "latency_ms": 5}

    with (
        patch(
            "feature_1_ia_personalizada.api.routes.health._check_postgresql",
            return_value=checks_ok,
        ),
        patch(
            "feature_1_ia_personalizada.api.routes.health._check_redis",
            return_value=checks_ok,
        ),
        patch(
            "feature_1_ia_personalizada.api.routes.health._check_claude_api",
            return_value=checks_ok,
        ),
        patch(
            "feature_1_ia_personalizada.api.routes.health._check_evolution_api",
            return_value=checks_ok,
        ),
        patch(
            "feature_1_ia_personalizada.api.routes.health._check_celery_workers",
            return_value=checks_ok,
        ),
        patch(
            "feature_1_ia_personalizada.api.routes.health._check_google_sheets",
            return_value={"status": "skipped", "detail": "not configured"},
        ),
    ):
        response = await async_client.get("/health/detailed")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "checks" in data
    assert "total_ms" in data


@pytest.mark.asyncio
async def test_health_detailed_critico_falha_retorna_503(async_client: AsyncClient):
    """GET /health/detailed → 503 quando PostgreSQL falha."""
    with (
        patch(
            "feature_1_ia_personalizada.api.routes.health._check_postgresql",
            return_value={"status": "error", "detail": "Connection failed"},
        ),
        patch(
            "feature_1_ia_personalizada.api.routes.health._check_redis",
            return_value={"status": "ok", "latency_ms": 5},
        ),
        patch(
            "feature_1_ia_personalizada.api.routes.health._check_claude_api",
            return_value={"status": "ok", "latency_ms": 5},
        ),
        patch(
            "feature_1_ia_personalizada.api.routes.health._check_evolution_api",
            return_value={"status": "ok", "latency_ms": 5},
        ),
        patch(
            "feature_1_ia_personalizada.api.routes.health._check_celery_workers",
            return_value={"status": "ok"},
        ),
        patch(
            "feature_1_ia_personalizada.api.routes.health._check_google_sheets",
            return_value={"status": "skipped"},
        ),
    ):
        response = await async_client.get("/health/detailed")

    assert response.status_code == 503
    assert response.json()["status"] == "error"


@pytest.mark.asyncio
async def test_health_detailed_externo_degradado_retorna_200(async_client: AsyncClient):
    """GET /health/detailed → 200 degraded quando serviços externos falham."""
    with (
        patch(
            "feature_1_ia_personalizada.api.routes.health._check_postgresql",
            return_value={"status": "ok", "latency_ms": 5},
        ),
        patch(
            "feature_1_ia_personalizada.api.routes.health._check_redis",
            return_value={"status": "ok", "latency_ms": 5},
        ),
        patch(
            "feature_1_ia_personalizada.api.routes.health._check_claude_api",
            return_value={"status": "error", "detail": "API unavailable"},
        ),
        patch(
            "feature_1_ia_personalizada.api.routes.health._check_evolution_api",
            return_value={"status": "ok", "latency_ms": 5},
        ),
        patch(
            "feature_1_ia_personalizada.api.routes.health._check_celery_workers",
            return_value={"status": "degraded", "detail": "No workers"},
        ),
        patch(
            "feature_1_ia_personalizada.api.routes.health._check_google_sheets",
            return_value={"status": "skipped"},
        ),
    ):
        response = await async_client.get("/health/detailed")

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"


@pytest.mark.asyncio
async def test_health_detailed_redis_critico_falha_retorna_503(
    async_client: AsyncClient,
):
    """503 quando Redis falha (serviço crítico)."""
    with (
        patch(
            "feature_1_ia_personalizada.api.routes.health._check_postgresql",
            return_value={"status": "ok", "latency_ms": 3},
        ),
        patch(
            "feature_1_ia_personalizada.api.routes.health._check_redis",
            return_value={"status": "timeout", "detail": "Redis não respondeu em 5s"},
        ),
        patch(
            "feature_1_ia_personalizada.api.routes.health._check_claude_api",
            return_value={"status": "ok"},
        ),
        patch(
            "feature_1_ia_personalizada.api.routes.health._check_evolution_api",
            return_value={"status": "ok"},
        ),
        patch(
            "feature_1_ia_personalizada.api.routes.health._check_celery_workers",
            return_value={"status": "ok"},
        ),
        patch(
            "feature_1_ia_personalizada.api.routes.health._check_google_sheets",
            return_value={"status": "skipped"},
        ),
    ):
        response = await async_client.get("/health/detailed")

    assert response.status_code == 503
    assert response.json()["status"] == "error"


@pytest.mark.asyncio
async def test_health_basic_sempre_ok(async_client: AsyncClient):
    """GET /health → 200 independente de qualquer serviço externo."""
    response = await async_client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "concierge" in body["service"]
