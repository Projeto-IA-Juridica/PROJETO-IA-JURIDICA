# feature_1_ia_personalizada/tests/unit/test_health_checks.py
"""
Testes unitários das funções de verificação de saúde (health check helpers).
Todas as dependências externas (DB, Redis, httpx, Celery, Google Sheets) são mockadas.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from feature_1_ia_personalizada.api.routes.health import (
    _check_celery_workers,
    _check_claude_api,
    _check_evolution_api,
    _check_google_sheets,
    _check_postgresql,
    _check_redis,
)

# ---------------------------------------------------------------------------
# _check_postgresql
# ---------------------------------------------------------------------------


class TestCheckPostgresql:
    async def test_sucesso_retorna_ok(self):
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=None)

        result = await _check_postgresql(mock_session)

        assert result["status"] == "ok"
        assert "latency_ms" in result

    async def test_timeout_retorna_timeout(self):
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=TimeoutError())

        with patch(
            "feature_1_ia_personalizada.api.routes.health.asyncio.wait_for",
            side_effect=TimeoutError(),
        ):
            result = await _check_postgresql(mock_session)

        assert result["status"] == "timeout"

    async def test_erro_generico_retorna_error(self):
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=Exception("connection refused"))

        result = await _check_postgresql(mock_session)

        assert result["status"] == "error"
        assert "connection refused" in result["detail"]


# ---------------------------------------------------------------------------
# _check_redis
# ---------------------------------------------------------------------------


class TestCheckRedis:
    async def test_sucesso_retorna_ok(self):
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)
        mock_redis.aclose = AsyncMock()

        with patch("feature_1_ia_personalizada.api.routes.health.redis") as mock_redis_module:
            mock_redis_module.from_url.return_value = mock_redis
            with patch(
                "feature_1_ia_personalizada.api.routes.health.asyncio.wait_for",
                return_value=True,
            ):
                result = await _check_redis()

        assert result["status"] == "ok"
        assert "latency_ms" in result

    async def test_timeout_retorna_timeout(self):
        mock_redis = AsyncMock()
        mock_redis.aclose = AsyncMock()

        with patch("feature_1_ia_personalizada.api.routes.health.redis") as mock_redis_module:
            mock_redis_module.from_url.return_value = mock_redis
            with patch(
                "feature_1_ia_personalizada.api.routes.health.asyncio.wait_for",
                side_effect=TimeoutError(),
            ):
                result = await _check_redis()

        assert result["status"] == "timeout"

    async def test_erro_generico_retorna_error(self):
        with patch("feature_1_ia_personalizada.api.routes.health.redis") as mock_redis_module:
            mock_redis_module.from_url.side_effect = Exception("redis unavailable")
            result = await _check_redis()

        assert result["status"] == "error"
        assert "redis unavailable" in result["detail"]


# ---------------------------------------------------------------------------
# _check_claude_api
# ---------------------------------------------------------------------------


class TestCheckClaudeApi:
    async def test_sucesso_retorna_ok(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "feature_1_ia_personalizada.api.routes.health.httpx.AsyncClient",
            return_value=mock_client,
        ):
            result = await _check_claude_api()

        assert result["status"] == "ok"
        assert result["http_status"] == 200

    async def test_resposta_400_ainda_ok(self):
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "feature_1_ia_personalizada.api.routes.health.httpx.AsyncClient",
            return_value=mock_client,
        ):
            result = await _check_claude_api()

        assert result["status"] == "ok"

    async def test_timeout_retorna_timeout(self):
        import httpx

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "feature_1_ia_personalizada.api.routes.health.httpx.AsyncClient",
            return_value=mock_client,
        ):
            result = await _check_claude_api()

        assert result["status"] == "timeout"

    async def test_erro_generico_retorna_error(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("network error"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "feature_1_ia_personalizada.api.routes.health.httpx.AsyncClient",
            return_value=mock_client,
        ):
            result = await _check_claude_api()

        assert result["status"] == "error"


# ---------------------------------------------------------------------------
# _check_evolution_api
# ---------------------------------------------------------------------------


class TestCheckEvolutionApi:
    async def test_sucesso_200_retorna_ok(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "feature_1_ia_personalizada.api.routes.health.httpx.AsyncClient",
            return_value=mock_client,
        ):
            result = await _check_evolution_api()

        assert result["status"] == "ok"

    async def test_status_500_retorna_degraded(self):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "feature_1_ia_personalizada.api.routes.health.httpx.AsyncClient",
            return_value=mock_client,
        ):
            result = await _check_evolution_api()

        assert result["status"] == "degraded"

    async def test_timeout_retorna_timeout(self):
        import httpx

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "feature_1_ia_personalizada.api.routes.health.httpx.AsyncClient",
            return_value=mock_client,
        ):
            result = await _check_evolution_api()

        assert result["status"] == "timeout"

    async def test_erro_generico_retorna_error(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "feature_1_ia_personalizada.api.routes.health.httpx.AsyncClient",
            return_value=mock_client,
        ):
            result = await _check_evolution_api()

        assert result["status"] == "error"


# ---------------------------------------------------------------------------
# _check_celery_workers
# ---------------------------------------------------------------------------


class TestCheckCeleryWorkers:
    async def test_workers_ativos_retorna_ok(self):
        mock_inspector = MagicMock()
        mock_inspector.ping.return_value = {"celery@worker1": {"ok": "pong"}}
        mock_app = MagicMock()
        mock_app.control.inspect.return_value = mock_inspector

        with patch(
            "feature_1_ia_personalizada.api.routes.health.asyncio.wait_for",
            side_effect=lambda coro, timeout: coro,
        ):
            with patch(
                "feature_1_ia_personalizada.api.routes.health.asyncio.to_thread",
            ) as mock_to_thread:
                mock_to_thread.return_value = {
                    "status": "ok",
                    "workers": ["celery@worker1"],
                }
                with patch(
                    "feature_1_ia_personalizada.api.routes.health.asyncio.wait_for",
                    return_value={"status": "ok", "workers": ["celery@worker1"]},
                ):
                    result = await _check_celery_workers()

        assert result["status"] == "ok"

    async def test_sem_workers_retorna_degraded(self):
        with patch(
            "feature_1_ia_personalizada.api.routes.health.asyncio.wait_for",
            return_value={
                "status": "degraded",
                "detail": "Nenhum worker respondeu ao ping",
            },
        ):
            result = await _check_celery_workers()

        assert result["status"] == "degraded"

    async def test_timeout_retorna_timeout(self):
        with patch(
            "feature_1_ia_personalizada.api.routes.health.asyncio.wait_for",
            side_effect=TimeoutError(),
        ):
            result = await _check_celery_workers()

        assert result["status"] == "timeout"


# ---------------------------------------------------------------------------
# _check_google_sheets
# ---------------------------------------------------------------------------


class TestCheckGoogleSheets:
    async def test_sem_credenciais_retorna_skipped(self):
        with patch("feature_1_ia_personalizada.api.routes.health.settings") as mock_settings:
            mock_settings.GOOGLE_CREDENTIALS_PATH = ""
            mock_settings.GOOGLE_SHEETS_ID = ""
            result = await _check_google_sheets()

        assert result["status"] == "skipped"

    async def test_sem_sheets_id_retorna_skipped(self):
        with patch("feature_1_ia_personalizada.api.routes.health.settings") as mock_settings:
            mock_settings.GOOGLE_CREDENTIALS_PATH = "/path/creds.json"
            mock_settings.GOOGLE_SHEETS_ID = ""
            result = await _check_google_sheets()

        assert result["status"] == "skipped"

    async def test_sucesso_retorna_ok(self):
        with patch("feature_1_ia_personalizada.api.routes.health.settings") as mock_settings:
            mock_settings.GOOGLE_CREDENTIALS_PATH = "/path/creds.json"
            mock_settings.GOOGLE_SHEETS_ID = "sheet-id-123"

            with patch(
                "feature_1_ia_personalizada.api.routes.health.asyncio.wait_for",
                return_value={"status": "ok", "latency_ms": 100},
            ):
                result = await _check_google_sheets()

        assert result["status"] == "ok"

    async def test_timeout_retorna_timeout(self):
        with patch("feature_1_ia_personalizada.api.routes.health.settings") as mock_settings:
            mock_settings.GOOGLE_CREDENTIALS_PATH = "/path/creds.json"
            mock_settings.GOOGLE_SHEETS_ID = "sheet-id-123"

            with patch(
                "feature_1_ia_personalizada.api.routes.health.asyncio.wait_for",
                side_effect=TimeoutError(),
            ):
                result = await _check_google_sheets()

        assert result["status"] == "timeout"
