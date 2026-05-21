"""
feature_1_ia_personalizada/api/middleware/csrf.py
==================================================
Proteção CSRF (Cross-Site Request Forgery) para a API.

Estratégia: Double Submit Cookie Pattern
- No primeiro acesso (GET /auth/csrf-token) o servidor gera um token aleatório
  e o devolve tanto no cookie `csrf_token` (HttpOnly=False, para o JS ler)
  quanto no corpo da resposta.
- Nas requisições que alteram estado (POST, PUT, PATCH, DELETE) o frontend deve
  enviar o mesmo token no header `X-CSRF-Token`.
- O middleware compara o valor do header com o cookie usando `secrets.compare_digest`
  (comparação em tempo constante — previne timing attacks).

Rotas isentas:
- Webhook do WhatsApp — autenticado via HMAC, sem sessão de browser.
- /health e /metrics — apenas leitura, sem cookie.
- /auth/csrf-token — endpoint que emite o token.
- /docs, /redoc, /openapi.json — documentação.

Tokens:
- 32 bytes hex (64 chars) gerados com `secrets.token_hex`.
- TTL: 24h (armazenado em cookie com Max-Age).
- Não é armazenado no servidor (stateless) — validade garantida pela assinatura
  do cookie + comparação com o header.
"""

import secrets

import structlog
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = structlog.get_logger(__name__)

# Métodos HTTP que alteram estado e exigem validação CSRF
_METODOS_MUTANTES = {"POST", "PUT", "PATCH", "DELETE"}

# Prefixos de rota isentos de CSRF (não envolvem sessão de browser)
_ROTAS_ISENTAS = (
    "/webhook/",  # WhatsApp — autenticado via HMAC
    "/health",  # leitura
    "/metrics",  # leitura
    "/auth/csrf-token",  # emissão do token
    "/auth/login",  # login inicial (sem sessão prévia para proteger)
    "/auth/refresh",  # refresh usa JWT, não sessão
    "/onboarding/register",  # registro inicial (sem sessão prévia)
    "/docs",
    "/redoc",
    "/openapi.json",
)

_COOKIE_NAME = "csrf_token"
_HEADER_NAME = "x-csrf-token"
_TOKEN_BYTES = 32  # 64 chars hex
_COOKIE_MAX_AGE = 86400  # 24h em segundos


def _rota_isenta(path: str) -> bool:
    return any(path.startswith(prefixo) for prefixo in _ROTAS_ISENTAS)


class CSRFMiddleware(BaseHTTPMiddleware):
    """
    Valida o token CSRF em todas as requisições mutantes que não estão na lista de isenção.
    """

    async def dispatch(self, request: Request, call_next):
        if request.method in _METODOS_MUTANTES and not _rota_isenta(request.url.path):
            token_cookie = request.cookies.get(_COOKIE_NAME)
            token_header = request.headers.get(_HEADER_NAME)

            # Rejeita se qualquer um estiver ausente
            if not token_cookie or not token_header:
                logger.warning(
                    "csrf.token_ausente",
                    path=request.url.path,
                    method=request.method,
                    tem_cookie=bool(token_cookie),
                    tem_header=bool(token_header),
                )
                return JSONResponse(
                    status_code=403,
                    content={"detail": "CSRF token ausente. Inclua o header X-CSRF-Token."},
                )

            # Comparação em tempo constante — previne timing attack
            if not secrets.compare_digest(token_cookie, token_header):
                logger.warning(
                    "csrf.token_invalido",
                    path=request.url.path,
                    method=request.method,
                )
                return JSONResponse(
                    status_code=403,
                    content={"detail": "CSRF token inválido."},
                )

        return await call_next(request)


def gerar_csrf_token() -> str:
    """Gera um novo token CSRF seguro (32 bytes = 64 chars hex)."""
    return secrets.token_hex(_TOKEN_BYTES)
