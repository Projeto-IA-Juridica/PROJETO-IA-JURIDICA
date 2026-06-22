"""
feature_1_ia_personalizada/api/middleware/rate_limit.py
=======================================================
Protege a API contra ataques de força bruta, flood ou spam.
Usa Redis para criar um Sliding Window / Fixed Window counter.
"""

from typing import Any

import redis.asyncio as redis
import structlog
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

logger = structlog.get_logger(__name__)

# Pool global de redis pro middleware
# (Não usa o mesmo motor SQLAlchemy, conecta direto rápido)
redis_client = None

# Limites por minuto
LIMIT_WEBHOOK = 100
LIMIT_API_GERAL = 60
LIMIT_CHAT = 30
LIMIT_LOGIN = 5  # anti-brute-force


def _get_client_ip(request: Request) -> str:
    """
    Extrai o IP real do cliente respeitando proxies reversos (Railway, Nginx, Cloudflare).

    Ordem de prioridade:
      1. X-Forwarded-For — cabeçalho padrão de proxies (primeiro IP = cliente original)
      2. X-Real-IP       — cabeçalho alternativo (Nginx)
      3. request.client  — conexão direta (sem proxy)
      4. "unknown"       — fallback (nunca agrupa todos num único bucket)

    Segurança: X-Forwarded-For pode ser forjado pelo cliente se o proxy não o sanitizar.
    Em produção, configure o proxy para sobrescrever (não apenas adicionar) o header.
    Railway faz isso por padrão — o primeiro IP da lista é confiável.
    """
    # X-Forwarded-For: client, proxy1, proxy2 — pega sempre o primeiro (cliente original)
    x_forwarded = request.headers.get("x-forwarded-for", "").strip()
    if x_forwarded:
        first_ip = x_forwarded.split(",")[0].strip()
        if first_ip:
            return first_ip

    # X-Real-IP: cabeçalho alternativo usado pelo Nginx
    x_real_ip = request.headers.get("x-real-ip", "").strip()
    if x_real_ip:
        return x_real_ip

    # Conexão direta (sem proxy) — pode ser None em alguns ambientes ASGI
    if request.client and request.client.host:
        return request.client.host

    return "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Controla o limite de requisições por IP ou por Usuário.
    """

    def __init__(self, app: Any) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Se o redis não estiver instanciado pelas configurações do app no startup, skipa
        if not hasattr(request.app.state, "redis_client"):
            return await call_next(request)

        r: redis.Redis = request.app.state.redis_client
        path = request.url.path

        # Estratégia de chave: IP para rotas públicas, User_ID para autenticados
        identifier = _get_client_ip(request)
        if hasattr(request.state, "user_payload"):
            identifier = request.state.user_payload.get("sub", identifier)

        # Seleciona o limite com base na rota
        limit = LIMIT_API_GERAL
        prefix = "rate_limit:api:"

        if path == "/auth/login":
            # Proteção anti-brute-force: sempre usa IP, nunca user_id.
            identifier = _get_client_ip(request)
            limit = LIMIT_LOGIN
            prefix = "rate_limit:login:"
        elif path.startswith("/webhook/whatsapp"):
            limit = LIMIT_WEBHOOK
            prefix = "rate_limit:webhook:"
        elif path.startswith("/chat"):
            limit = LIMIT_CHAT
            prefix = "rate_limit:chat:"

        redis_key = f"{prefix}{identifier}"

        # Lógica atômica no Redis: incrementa e seta expiração se for nova
        current_count = 0
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
        except Exception as e:
            #  CORREÇÃO: Redis indisponível não derruba a API, mas agora logamos
            # o erro para que o problema seja visível no monitoramento.
            logger.warning(
                "rate_limit.redis_unavailable",
                error=str(e),
                path=path,
                identifier=identifier,
            )

        # Segue a request
        response = await call_next(request)

        # Retorna nos headers quantos faltam pra estourar
        try:
            remaining = str(max(0, limit - int(current_count)))
            response.headers["X-RateLimit-Limit"] = str(limit)
            response.headers["X-RateLimit-Remaining"] = remaining
        except Exception as e:
            # ✅ CORREÇÃO: falha ao setar headers também merece log (nível debug,
            # pois não afeta o fluxo principal)
            logger.debug(
                "rate_limit.headers_error",
                error=str(e),
                path=path,
            )

        return response
