"""
feature_1_ia_personalizada/api/middleware/auth.py
=================================================
Middleware Global de Autenticação JWT.

Intercepta todas as requisições na API. Se a rota não for pública,
tenta extrair o token do header `Authorization: Bearer <token>`,
valida e injeta os dados do usuário em `request.state.current_user`.

Também expõe dependências FastAPI para controle de acesso por role:
- require_advogado: garante que o usuário seja advogado ou admin
- get_escritorio_id_advogado: retorna o escritorio_id do token
- get_advogado_id: retorna o user_id do token
"""

import secrets

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from starlette.middleware.base import BaseHTTPMiddleware

from shared.config.settings import settings
from shared.security.jwt import token_esta_revogado, validar_token

# Rotas que não exigem token JWT para serem acessadas
ROTAS_PUBLICAS = [
    "/health",  # O health check básico é open
    "/health/ready",  # O detailed também, para pods k8s conseguirem ler
    "/auth/login",  # Obviamente, pra gerar o token
    "/auth/refresh",  # Pra renovar
    "/auth/csrf-token",  # Pra buscar o token CSRF antes do login
    "/webhook/whatsapp",  # Evolution API manda pra cá (autenticado via Header X-API-Key depois)
    "/metrics",  # Prometheus scraper não usa JWT
]

# Rotas com match EXATO (não prefixo) — evita vazar proteção de sub-rotas.
# Ex: /admin/import (HTML) é público, mas /admin/import/clientes (POST) exige JWT.
# /onboarding/register é público; demais rotas /onboarding/* exigem JWT.
ROTAS_PUBLICAS_EXATAS = [
    "/admin/import",
    "/onboarding/register",
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
    senha_ok = secrets.compare_digest(password, DOCS_PASSWORD)
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

        # 2a. CORS preflight — OPTIONS nunca carrega JWT, deve passar livre
        if request.method == "OPTIONS":
            return await call_next(request)

        # 2b. Rotas públicas — passam direto
        if path in ROTAS_PUBLICAS_EXATAS:
            return await call_next(request)

        if any(path.startswith(rota) for rota in ROTAS_PUBLICAS):
            return await call_next(request)

        # 3. Demais rotas — exigem Bearer JWT
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={
                    "detail": (
                        "Token JWT ausente ou mal formatado." " Use 'Authorization: Bearer <token>'"
                    )
                },
            )

        token = auth_header.split(" ")[1]

        try:
            payload = validar_token(token)
        except ValueError as e:
            return JSONResponse(status_code=401, content={"detail": str(e)})
        except JWTError:
            return JSONResponse(status_code=401, content={"detail": "Token JWT inválido"})

        if token_esta_revogado(token):
            return JSONResponse(
                status_code=401,
                content={"detail": "Token revogado. Faça login novamente."},
            )

        request.state.user_payload = payload

        # 4.  Deixa a requisição seguir seu fluxo normal - fica autorizado
        response = await call_next(request)
        return response


# ---------------------------------------------------------------------------
# Dependências FastAPI para controle de acesso por role
# ---------------------------------------------------------------------------

_bearer = HTTPBearer(auto_error=False)


def _get_payload(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    """Extrai e valida o JWT da requisição, retornando o payload."""
    token: str | None = None
    if credentials:
        token = credentials.credentials
    elif hasattr(request.state, "user_payload"):
        # Já validado pelo middleware — reaproveita
        return request.state.user_payload

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token JWT ausente. Use 'Authorization: Bearer <token>'",
        )
    try:
        payload = validar_token(token)
    except (ValueError, JWTError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

    if token_esta_revogado(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token revogado. Faça login novamente.",
        )
    return payload


def require_advogado(payload: dict = Depends(_get_payload)) -> dict:
    """
    Garante que o usuário tem role 'advogado' ou 'admin'.
    Lança 403 para qualquer outro role (cliente, estagiario, assistente).
    """
    role = payload.get("role", "")
    if role not in ("advogado", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a advogados e administradores.",
        )
    return payload


def get_escritorio_id_advogado(
    payload: dict = Depends(require_advogado),
) -> int:
    """Retorna o escritorio_id do token JWT (já validado como advogado/admin)."""
    try:
        return int(payload["escritorio_id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token não contém escritorio_id válido.",
        ) from exc


def get_advogado_id(
    payload: dict = Depends(require_advogado),
) -> int:
    """Retorna o user_id (sub) do token JWT."""
    try:
        return int(payload["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token não contém user_id válido.",
        ) from exc
