# feature_1_ia_personalizada/tests/unit/test_app_validation.py
"""
Testes unitários para _validar_config_no_startup e para os middlewares da API.
Testa a lógica de validação do startup sem inicializar o servidor completo.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# _validar_config_no_startup
# ---------------------------------------------------------------------------


class TestValidarConfigNoStartup:
    """Testa a função de validação de configuração que roda no startup."""

    def _rodar_validacao(self, **overrides):
        """Executa _validar_config_no_startup com settings mockados."""
        from cryptography.fernet import Fernet

        from feature_1_ia_personalizada.api.app import _validar_config_no_startup

        chave_fernet = Fernet.generate_key().decode()

        defaults = {
            "REDIS_URL": "redis://localhost:6379/0",
            "CELERY_BROKER_URL": "redis://localhost:6379/1",
            "CELERY_RESULT_BACKEND": "redis://localhost:6379/2",
            "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost/db",
            "JWT_SECRET_KEY": "chave-super-secreta-com-mais-de-32-chars-ok",
            "ENCRYPTION_KEY": chave_fernet,
            "EVOLUTION_API_URL": "http://localhost:8080",
            "EVOLUTION_API_KEY": "chave-evolution",
            "OPENAI_API_KEY": "sk-test-openai",
            "ANTHROPIC_API_KEY": "sk-ant-test-key",
        }
        defaults.update(overrides)

        mock_settings = MagicMock()
        for key, value in defaults.items():
            setattr(mock_settings, key, value)

        with patch("feature_1_ia_personalizada.api.app.settings", mock_settings):
            _validar_config_no_startup()

    def test_config_valida_nao_levanta(self):
        """Configuração válida não deve levantar exceção."""
        self._rodar_validacao()  # não deve levantar

    def test_redis_url_invalida_levanta(self):
        with pytest.raises(RuntimeError, match="REDIS_URL"):
            self._rodar_validacao(REDIS_URL="http://invalid")

    def test_database_url_invalida_levanta(self):
        with pytest.raises(RuntimeError, match="DATABASE_URL"):
            self._rodar_validacao(DATABASE_URL="mysql://user:pass@localhost/db")

    def test_jwt_secret_muito_curto_levanta(self):
        with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
            self._rodar_validacao(JWT_SECRET_KEY="curto")

    def test_openai_api_key_invalida_levanta(self):
        with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
            self._rodar_validacao(OPENAI_API_KEY="invalid-key")

    def test_anthropic_api_key_invalida_levanta(self):
        with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
            self._rodar_validacao(ANTHROPIC_API_KEY="sk-not-ant-key")

    def test_evolution_url_invalida_levanta(self):
        with pytest.raises(RuntimeError, match="EVOLUTION_API_URL"):
            self._rodar_validacao(EVOLUTION_API_URL="ftp://invalid")

    def test_celery_broker_invalido_levanta(self):
        with pytest.raises(RuntimeError, match="CELERY_BROKER_URL"):
            self._rodar_validacao(CELERY_BROKER_URL="amqp://localhost")

    def test_encryption_key_invalida_levanta(self):
        with pytest.raises(RuntimeError, match="ENCRYPTION_KEY"):
            self._rodar_validacao(ENCRYPTION_KEY="nao-e-uma-chave-fernet-valida")


# ---------------------------------------------------------------------------
# Middleware Auth — teste via imports diretos
# ---------------------------------------------------------------------------


class TestJWTAuthMiddleware:
    """Testa o middleware de autenticação diretamente."""

    def _criar_middleware(self):
        from feature_1_ia_personalizada.api.middleware.auth import JWTAuthMiddleware

        mock_app = MagicMock()
        return JWTAuthMiddleware(mock_app)

    async def _dispatch(self, middleware, path: str, headers: dict | None = None):
        """Helper para simular dispatch do middleware."""
        _headers = headers or {}
        mock_request = MagicMock()
        mock_request.url.path = path
        mock_request.headers.get = lambda key, default=None: _headers.get(key, default)

        responses = []

        async def call_next(req):
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            responses.append("called")
            return mock_resp

        return await middleware.dispatch(mock_request, call_next), responses

    async def test_rota_publica_health_bypassa_auth(self):
        middleware = self._criar_middleware()
        response, called = await self._dispatch(middleware, "/health")
        assert response.status_code == 200
        assert called  # call_next foi chamado

    async def test_rota_publica_docs_bypassa_auth(self):
        middleware = self._criar_middleware()
        with (
            patch("feature_1_ia_personalizada.api.middleware.auth.DOCS_PASSWORD", None),
            patch(
                "feature_1_ia_personalizada.api.middleware.auth.settings"
            ) as mock_settings,
        ):
            mock_settings.ENVIRONMENT = "development"
            response, called = await self._dispatch(middleware, "/docs")
        assert called

    async def test_rota_publica_auth_login_bypassa_auth(self):
        middleware = self._criar_middleware()
        response, called = await self._dispatch(middleware, "/auth/login")
        assert called

    async def test_rota_protegida_sem_token_retorna_401(self):
        from fastapi.responses import JSONResponse

        middleware = self._criar_middleware()
        response, called = await self._dispatch(middleware, "/chat/history/1")
        assert isinstance(response, JSONResponse)
        assert response.status_code == 401
        assert not called

    async def test_rota_protegida_com_bearer_mal_formatado_retorna_401(self):
        from fastapi.responses import JSONResponse

        middleware = self._criar_middleware()
        response, called = await self._dispatch(
            middleware,
            "/chat/history/1",
            headers={"Authorization": "Basic dXNlcjpwYXNz"},
        )
        assert isinstance(response, JSONResponse)
        assert response.status_code == 401

    async def test_rota_protegida_com_token_invalido_retorna_401(self):
        from fastapi.responses import JSONResponse

        middleware = self._criar_middleware()
        response, called = await self._dispatch(
            middleware,
            "/chat/history/1",
            headers={"Authorization": "Bearer token-invalido-xyz"},
        )
        assert isinstance(response, JSONResponse)
        assert response.status_code == 401

    async def test_rota_protegida_com_token_valido_passa(self):
        from shared.security.jwt import criar_token

        token = criar_token(user_id=1, escritorio_id=1, role="admin")
        middleware = self._criar_middleware()

        mock_request = MagicMock()
        mock_request.url.path = "/chat/history/1"
        mock_request.headers.get = lambda key, default=None: (
            f"Bearer {token}" if key == "Authorization" else default
        )
        mock_request.state = MagicMock()

        async def call_next(req):
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            return mock_resp

        response = await middleware.dispatch(mock_request, call_next)
        assert response.status_code == 200

    async def test_webhook_whatsapp_bypassa_auth(self):
        middleware = self._criar_middleware()
        response, called = await self._dispatch(middleware, "/webhook/whatsapp")
        assert called

    async def test_metrics_bypassa_auth(self):
        middleware = self._criar_middleware()
        response, called = await self._dispatch(middleware, "/metrics")
        assert called


# ---------------------------------------------------------------------------
# RequestLoggingMiddleware
# ---------------------------------------------------------------------------


class TestRequestLoggingMiddleware:
    async def test_adiciona_x_request_id_ao_response(self):
        from feature_1_ia_personalizada.api.middleware.request_logging import (
            RequestLoggingMiddleware,
        )

        mock_app = MagicMock()
        middleware = RequestLoggingMiddleware(mock_app)

        mock_request = MagicMock()
        mock_request.url.path = "/health"
        mock_request.method = "GET"
        mock_request.client.host = "127.0.0.1"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}

        async def call_next(req):
            return mock_response

        response = await middleware.dispatch(mock_request, call_next)
        assert "X-Request-ID" in response.headers
        assert len(response.headers["X-Request-ID"]) == 36  # UUID4

    async def test_request_4xx_loga_warning(self):
        from feature_1_ia_personalizada.api.middleware.request_logging import (
            RequestLoggingMiddleware,
        )

        mock_app = MagicMock()
        middleware = RequestLoggingMiddleware(mock_app)

        mock_request = MagicMock()
        mock_request.url.path = "/nao-existe"
        mock_request.method = "GET"
        mock_request.client.host = "127.0.0.1"

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.headers = {}

        async def call_next(req):
            return mock_response

        # Apenas verifica que não levanta exceção
        response = await middleware.dispatch(mock_request, call_next)
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# RateLimitMiddleware
# ---------------------------------------------------------------------------


class TestRateLimitMiddleware:
    async def test_sem_redis_no_estado_passa_direto(self):
        from feature_1_ia_personalizada.api.middleware.rate_limit import (
            RateLimitMiddleware,
        )

        mock_app = MagicMock()
        middleware = RateLimitMiddleware(mock_app)

        mock_request = MagicMock()
        mock_request.url.path = "/health"
        mock_request.app.state = MagicMock(spec=[])  # sem redis_client

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}

        async def call_next(req):
            return mock_response

        response = await middleware.dispatch(mock_request, call_next)
        assert response.status_code == 200

    async def test_com_redis_abaixo_do_limite_passa(self):
        from feature_1_ia_personalizada.api.middleware.rate_limit import (
            RateLimitMiddleware,
        )

        mock_app = MagicMock()
        middleware = RateLimitMiddleware(mock_app)

        mock_redis = AsyncMock()
        mock_redis.incr = AsyncMock(return_value=1)
        mock_redis.expire = AsyncMock(return_value=True)

        mock_request = MagicMock()
        mock_request.url.path = "/health"
        mock_request.app.state.redis_client = mock_redis
        mock_request.client.host = "127.0.0.1"
        mock_request.state = MagicMock(spec=[])  # sem user_payload

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}

        async def call_next(req):
            return mock_response

        response = await middleware.dispatch(mock_request, call_next)
        assert response.status_code == 200

    async def test_com_redis_acima_do_limite_retorna_429(self):
        from fastapi.responses import JSONResponse

        from feature_1_ia_personalizada.api.middleware.rate_limit import (
            LIMIT_API_GERAL,
            RateLimitMiddleware,
        )

        mock_app = MagicMock()
        middleware = RateLimitMiddleware(mock_app)

        mock_redis = AsyncMock()
        mock_redis.incr = AsyncMock(return_value=LIMIT_API_GERAL + 1)
        mock_redis.expire = AsyncMock(return_value=True)

        mock_request = MagicMock()
        mock_request.url.path = "/chat/message"
        mock_request.app.state.redis_client = mock_redis
        mock_request.client.host = "192.168.1.1"
        mock_request.state = MagicMock(spec=[])

        async def call_next(req):
            return MagicMock(status_code=200)

        response = await middleware.dispatch(mock_request, call_next)
        assert isinstance(response, JSONResponse)
        assert response.status_code == 429

    async def test_webhook_usa_limite_de_webhook(self):
        from feature_1_ia_personalizada.api.middleware.rate_limit import (
            LIMIT_WEBHOOK,
            RateLimitMiddleware,
        )

        mock_app = MagicMock()
        middleware = RateLimitMiddleware(mock_app)

        mock_redis = AsyncMock()
        mock_redis.incr = AsyncMock(return_value=1)
        mock_redis.expire = AsyncMock(return_value=True)

        mock_request = MagicMock()
        mock_request.url.path = "/webhook/whatsapp"
        mock_request.app.state.redis_client = mock_redis
        mock_request.client.host = "10.0.0.1"
        mock_request.state = MagicMock(spec=[])

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}

        async def call_next(req):
            return mock_response

        response = await middleware.dispatch(mock_request, call_next)
        assert response.status_code == 200
        # Verifica que o limite de webhook é retornado nos headers
        assert mock_response.headers.get("X-RateLimit-Limit") == str(LIMIT_WEBHOOK)

    async def test_redis_error_nao_derruba_api(self):
        from feature_1_ia_personalizada.api.middleware.rate_limit import (
            RateLimitMiddleware,
        )

        mock_app = MagicMock()
        middleware = RateLimitMiddleware(mock_app)

        mock_redis = AsyncMock()
        mock_redis.incr = AsyncMock(side_effect=Exception("Redis connection lost"))

        mock_request = MagicMock()
        mock_request.url.path = "/health"
        mock_request.app.state.redis_client = mock_redis
        mock_request.client.host = "127.0.0.1"
        mock_request.state = MagicMock(spec=[])

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}

        async def call_next(req):
            return mock_response

        # Não deve levantar exceção mesmo com Redis falhando
        response = await middleware.dispatch(mock_request, call_next)
        assert response.status_code == 200
