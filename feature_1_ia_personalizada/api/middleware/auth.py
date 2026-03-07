"""
feature_1_ia_personalizada/api/middleware/auth.py
=================================================
Middleware Global de Autenticação JWT.

Intercepta todas as requisições na API. Se a rota não for pública,
tenta extrair o token do header `Authorization: Bearer <token>`,
valida e injeta os dados do usuário em `request.state.current_user`.
"""

import secrets

from fastapi import Request
from fastapi.responses import JSONResponse
from jose import JWTError
from starlette.middleware.base import BaseHTTPMiddleware

from shared.config.settings import settings
from shared.security.jwt import validar_token

# Rotas que não exigem token JWT para serem acessadas
ROTAS_PUBLICAS = [
    "/health",            # O health check básico é open
    "/health/ready",      # O detailed também, para pods k8s conseguirem ler
    "/auth/login",        # Obviamente, pra gerar o token
    "/auth/refresh",      # Pra renovar
    "/webhook/whatsapp",  # Evolution API manda pra cá (autenticado via Header X-API-Key depois)
    "/metrics",           # Prometheus scraper não usa JWT
]


# Em produção são bloqueados (403). Em outros ambientes, protegidos
# por HTTP Basic Auth via DOCS_USERNAME / DOCS_PASSWORD no .env.
ROTAS_DOCS = ["/docs", "/redoc", "/openapi.json"]

DOCS_USERNAME: str = getattr(settings, "DOCS_USERNAME", "admin")
DOCS_PASSWORD: str | None = getattr(settings, "DOCS_PASSWORD", None)


def _checar_basic_auth(request: Request) -> bool:
    """
    Valida HTTP Basic Auth para as rotas de documentação.
    Retorna True se autorizado, False caso contrário.
    """
    # Dev/staging sem senha configurada → libera
    if not DOCS_PASSWORD:
        return True

    import base64
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Basic "):
        return False

    try:
        decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
        username, _, password = decoded.partition(":")
    except Exception:
        return False

    # secrets.compare_digest evita timing attack
    usuario_ok = secrets.compare_digest(username, DOCS_USERNAME)
    senha_ok   = secrets.compare_digest(password, DOCS_PASSWORD)
    return usuario_ok and senha_ok


class JWTAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # 1. Rotas de documentação — controle próprio por ambiente
        if any(path.startswith(rota) for rota in ROTAS_DOCS):
            is_producao = settings.ENVIRONMENT == "production"

            # Produção sem senha configurada → bloqueia completamente
            if is_producao and not DOCS_PASSWORD:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Documentação desabilitada em produção."},
                )

            # Dev/staging ou produção com senha → exige Basic Auth
            if not _checar_basic_auth(request):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Autenticação necessária para acessar a documentação."},
                    headers={"WWW-Authenticate": "Basic"},
                )

            return await call_next(request)

        # 2. Rotas públicas — passam direto
        if any(path.startswith(rota) for rota in ROTAS_PUBLICAS):
            return await call_next(request)

        # 3. Demais rotas — exigem Bearer JWT
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={
                    "detail": "Token JWT ausente ou mal formatado. Use 'Authorization: Bearer <token>'"
                },
            )

        token = auth_header.split(" ")[1]

        try:
            payload = validar_token(token)
            request.state.user_payload = payload
        except ValueError as e:
            return JSONResponse(status_code=401, content={"detail": str(e)})
        except JWTError:
            return JSONResponse(
                status_code=401, content={"detail": "Token JWT inválido"}
            )

        # 4.  Deixa a requisição seguir seu fluxo normal - fica autorizado 
        response = await call_next(request)
        return response