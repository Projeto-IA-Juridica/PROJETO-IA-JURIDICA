"""
feature_1_ia_personalizada/api/middleware/rate_limit.py
=======================================================
Protege a API contra ataques de força bruta, flood ou spam.
Usa Redis para criar um Sliding Window / Fixed Window counter.
"""

import redis.asyncio as redis
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

# Pool global de redis pro middleware
# (Não usa o mesmo motor SQLAlchemy, conecta direto rápido)
redis_client = None

# Limites por minuto
LIMIT_WEBHOOK = 100
LIMIT_API_GERAL = 60
LIMIT_CHAT = 30


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Controla o limite de requisições por IP ou por Usuário.
    """

    def __init__(self, app):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        # Se o redis não estiver instanciado pelas configurações do app no startup, skipa
        if not hasattr(request.app.state, "redis_client"):
            return await call_next(request)

        r: redis.Redis = request.app.state.redis_client
        path = request.url.path

        # Estratégia de chave: IP para rotas públicas, User_ID para autenticados
        identifier = request.client.host
        if hasattr(request.state, "user_payload"):
            identifier = request.state.user_payload.get("sub", identifier)

        # Seleciona o limite com base na rota
        limit = LIMIT_API_GERAL
        prefix = "rate_limit:api:"

        if path.startswith("/webhook/whatsapp"):
            limit = LIMIT_WEBHOOK
            prefix = "rate_limit:webhook:"
            # Para webhook, garantimos que travemos por IP ou Instance Name
        elif path.startswith("/chat"):
            limit = LIMIT_CHAT
            prefix = "rate_limit:chat:"

        redis_key = f"{prefix}{identifier}"

        # Lógica atômica no Redis: incrementa e seta expiração se for nova
        try:
            current_count = await r.incr(redis_key)
            if current_count == 1:
                # Expira em 60 segundos (1 minuto)
                await r.expire(redis_key, 60)

            if current_count > limit:
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": "Muitas requisições. Rate limit excedido para sua conta/IP.",
                        "limit": limit,
                    },
                )
        except Exception:
            # Se o Redis cair por algum motivo, não vamos derrubar a API inteira
            # Deixa passar, mas faríamos log disso idealmente
            pass

        # Segue a request
        response = await call_next(request)

        # Retorna nos headers quantos faltam pra estourar
        try:
            remaining = str(max(0, limit - int(current_count)))
            response.headers["X-RateLimit-Limit"] = str(limit)
            response.headers["X-RateLimit-Remaining"] = remaining
        except Exception:
            pass

        return response
