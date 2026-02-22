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

# Importando os roteadores das nossas subpastas
from feature_1_ia_personalizada.api.routes import (
    auth,
    health,
    processos,
    chat,
    webhook_whatsapp,
)

# TODO: Fase 3/4 - Inicialização do Banco e Conexões Externas
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Executado ao iniciar o servidor (Startup)
    print("🚀 Iniciando o Concierge Jurídico Digital...")
    # Aqui vamos conectar ao PostgreSQL e Redis no futuro próximo
    yield
    # Executado ao desligar o servidor (Shutdown)
    print("🛑 Encerrando o servidor de forma graciosa...")
    # Aqui vamos fechar pools do PostgreSQL e Redis no futuro próximo


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

# ==========================================
# REGISTRO DE ROTEADORES (ENDPOINTS)
# ==========================================
app.include_router(health)
app.include_router(auth)
app.include_router(processos)
app.include_router(chat)
app.include_router(webhook_whatsapp)
