"""
feature_1_ia_personalizada/api/app.py
======================================
Entry point principal do FastAPI para o Concierge Jurídico Digital.

Inicializa o aplicativo, configura middlewares (CORS),
registra todos os roteadores de domínio e define tratadores de eventos de ciclo de vida.
"""

from contextlib import asynccontextmanager

import redis.asyncio as redis
import sentry_sdk
import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

from shared.config.settings import settings

# ==========================================
# SENTRY — rastreamento de erros em produção
# ==========================================
if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.ENVIRONMENT,
        integrations=[
            FastApiIntegration(transaction_style="endpoint"),
            SqlalchemyIntegration(),
            CeleryIntegration(),
        ],
        traces_sample_rate=0.1,  # 10% das requisições para performance
        profiles_sample_rate=0.1,
        send_default_pii=False,  # LGPD — não enviar dados de usuário
    )

from feature_1_ia_personalizada.api.middleware.auth import JWTAuthMiddleware
from feature_1_ia_personalizada.api.middleware.rate_limit import RateLimitMiddleware
from feature_1_ia_personalizada.api.middleware.request_logging import (
    RequestLoggingMiddleware,
)

# Importando os roteadores das nossas subpastas
from feature_1_ia_personalizada.api.routes import (
    auth,
    chat,
    health,
    metrics,
    processos,
    webhook_whatsapp,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Executado ao iniciar o servidor (Startup)
    print("🚀 Iniciando o Concierge Jurídico Digital...")

    # 1. Ligando o Redis para o Rate Limit
    app.state.redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        await app.state.redis_client.ping()
        print("✅ Redis conectado com sucesso (Rate Limit Ativo).")
    except Exception as e:
        print(f"❌ Erro ao conectar no Redis: {e}")

    yield

    # Executado ao desligar o servidor (Shutdown)
    print("🛑 Encerrando o servidor de forma graciosa...")
    if hasattr(app.state, "redis_client"):
        await app.state.redis_client.aclose()


logger = structlog.get_logger(__name__)

# Instanciando o App com o ciclo de vida
app = FastAPI(
    title="Concierge Jurídico Digital",
    description="Backend central da Inteligência Artificial via WhatsApp para Escritórios.",
    version="0.2.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ==========================================
# MIDDLEWARES GLOBAIS
# ==========================================
# CORS: Permite que um frontend (ex: painel web Vue/React) consuma esta API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Em produção, trocar para domínios específicos
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)  

# if settings.ENVIRONMENT == "development": A SER IMPLEMENTADO, CORS ACIMA DEVE SER APAGADO ;
#     allowed_origins = ["*"]
# else:
#     allowed_origins = [
#         "https://app.conciergejuridico.com",
#         "https://admin.conciergejuridico.com",
#     ]

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=allowed_origins,
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# Registrando nossos custom middlewares (a ordem de registro importa, o último empilhado executa ANTES)
# Fluxo ideal ao receber requisição: 1. Rate Limit -> 2. Autenticação JWT -> 3. Rotas
app.add_middleware(JWTAuthMiddleware)
app.add_middleware(RateLimitMiddleware)
# RequestLoggingMiddleware adicionado por último = executa PRIMEIRO (outermost)
# Garante que request_id está disponível para todos os middlewares internos e rotas
app.add_middleware(RequestLoggingMiddleware)

# ==========================================
# REGISTRO DE ROTEADORES (ENDPOINTS)
# ==========================================
app.include_router(health)
app.include_router(metrics)
app.include_router(auth)
app.include_router(processos)
app.include_router(chat)
app.include_router(webhook_whatsapp)

# ==========================================
# INSTRUMENTAÇÃO HTTP (Prometheus)
# ==========================================
# Adiciona métricas HTTP automáticas:
#   http_requests_total{method, handler, status}
#   http_request_duration_seconds{method, handler, status}
#   http_requests_in_progress{method, handler}
Instrumentator(
    should_group_status_codes=False,  # separa 200, 201, 404, etc.
    excluded_handlers=["/metrics"],  # não mede o endpoint de métricas em si
).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)


# ==========================================
# ERROR HANDLER GLOBAL
# ==========================================
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # Captura explícita necessária: o handler impede que o Sentry capture automaticamente
    sentry_sdk.capture_exception(exc)
    logger.error(
        "erro_nao_tratado", path=request.url.path, erro=str(exc), exc_info=True
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Erro interno do servidor"},
    )
