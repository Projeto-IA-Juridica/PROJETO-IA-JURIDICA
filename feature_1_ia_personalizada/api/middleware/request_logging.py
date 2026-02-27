"""
feature_1_ia_personalizada/api/middleware/request_logging.py
=============================================================
Middleware de logging estruturado por requisição.

O que faz:
  - Gera um request_id único (UUID4) por requisição
  - Limpa o contexto structlog anterior (evita vazamento entre requests)
  - Injeta request_id, method, path no contexto → todos os logs desse
    request herdam esses campos automaticamente
  - Loga início e fim de cada request com: método, path, status, latência
  - Devolve o request_id no header X-Request-ID (facilita rastreio no cliente)

Uso do request_id:
  Qualquer logger structlog chamado durante o processamento do request
  (em services, workers iniciados sincronamente, etc.) vai incluir
  request_id automaticamente graças ao bind_contextvars.
"""

import time
import uuid

import structlog
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from structlog.contextvars import bind_contextvars, clear_contextvars

logger = structlog.get_logger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 1. Limpa contexto do request anterior (contextvars são por task asyncio)
        clear_contextvars()

        # 2. Gera e injeta request_id em todo log deste request
        request_id = str(uuid.uuid4())
        bind_contextvars(
            request_id=request_id,
            http_method=request.method,
            http_path=request.url.path,
        )

        client_ip = request.client.host if request.client else "unknown"
        inicio = time.perf_counter()

        logger.info(
            "http_request_start",
            client_ip=client_ip,
        )

        # 3. Processa o request
        response = await call_next(request)

        # 4. Loga fim com status e latência
        duracao_ms = round((time.perf_counter() - inicio) * 1000, 2)
        nivel = "warning" if response.status_code >= 400 else "info"
        getattr(logger, nivel)(
            "http_request_end",
            status_code=response.status_code,
            duracao_ms=duracao_ms,
            client_ip=client_ip,
        )

        # 5. Devolve request_id ao cliente (útil para correlacionar logs com suporte)
        response.headers["X-Request-ID"] = request_id
        return response
