"""
feature_1_ia_personalizada/api/middleware/auth.py
=================================================
Middleware Global de Autenticação JWT.

Intercepta todas as requisições na API. Se a rota não for pública,
tenta extrair o token do header `Authorization: Bearer <token>`,
valida e injeta os dados do usuário em `request.state.current_user`.
"""

from fastapi import Request
from fastapi.responses import JSONResponse
from jose import JWTError
from starlette.middleware.base import BaseHTTPMiddleware

from shared.security.jwt import validar_token

# Rotas que não exigem token JWT para serem acessadas
ROTAS_PUBLICAS = [
    "/docs",
    "/redoc",
    "/openapi.json",
    "/health",  # O health check básico é open
    "/health/ready",  # O detailed também, para pods k8s conseguirem ler
    "/auth/login",  # Obviamente, pra gerar o token
    "/auth/refresh",  # Pra renovar
    "/webhook/whatsapp",  # Evolution API manda pra cá (autenticado via Header X-API-Key depois)
    "/metrics",  # Prometheus scraper não usa JWT
]


class JWTAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 1. Verifica se a rota atual é pública
        path = request.url.path
        if any(path.startswith(rota) for rota in ROTAS_PUBLICAS):
            # Se for, deixa passar direto pro endpoint
            return await call_next(request)

        # 2. Se não for pública, busca o Header de Authorization
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={
                    "detail": "Token JWT ausente ou mal formatado. Use 'Authorization: Bearer <token>'"
                },
            )

        token = auth_header.split(" ")[1]

        # 3. Valida o Token usando nossa função de shared/security
        try:
            payload = validar_token(token)
            # Injeta os dados do payload no request state para as rotas usarem (se precisarem)
            request.state.user_payload = payload
        except ValueError as e:
            return JSONResponse(status_code=401, content={"detail": str(e)})
        except JWTError:
            return JSONResponse(
                status_code=401, content={"detail": "Token JWT inválido"}
            )

        # 4. Autorizado! Deixa a requisição seguir seu fluxo normal
        response = await call_next(request)
        return response
