"""
feature_1_ia_personalizada/api/app.py
======================================
Entry point principal do FastAPI para o Concierge Jurídico Digital.

Inicializa o aplicativo, configura middlewares (CORS),
registra todos os roteadores de domínio e define tratadores de eventos de ciclo de vida.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import redis.asyncio as redis

from shared.config.settings import settings
from feature_1_ia_personalizada.api.middleware.rate_limit import RateLimitMiddleware
from feature_1_ia_personalizada.api.middleware.auth import JWTAuthMiddleware
from feature_1_ia_personalizada.api.middleware.request_logging import RequestLoggingMiddleware

# Importando os roteadores das nossas subpastas
from feature_1_ia_personalizada.api.routes import (
    auth,
    health,
    metrics,
    processos,
    chat,
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
