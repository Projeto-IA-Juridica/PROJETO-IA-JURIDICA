"""
shared/database/connection.py
==============================
Módulo responsável por gerenciar a conexão com o banco de dados PostgreSQL.

Utiliza a engine assíncrona do SQLAlchemy (asyncpg) para garantir alta performance
na aplicação FastAPI, permitindo concorrência sem bloquear a thread principal.
"""

from typing import Any

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from shared.config.settings import settings

# ⚠️ O SQLAlchemy + asyncpg exige que a URL comece com "postgresql+asyncpg://"
# Caso a variável de ambiente não inclua "+asyncpg", fazemos o replace garantindo
# que o driver correto seja usado.
db_url = settings.DATABASE_URL
if not db_url.startswith("postgresql+asyncpg://"):
    db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

# =====================================================================
# ENGINE: O "motor" principal que gerencia o pool de conexões com o BD.
# =====================================================================
connect_args: dict[str, Any] = {}
if "supabase.com" in db_url:
    connect_args["ssl"] = "require"

# Limita o pool a 1 conexão por worker para evitar estourar limites
# de PgBouncer em provedores durante deploys Blue/Green.
_pool_size, _max_overflow = 1, 1

engine = create_async_engine(
    db_url,
    connect_args=connect_args,
    echo=(settings.ENVIRONMENT == "development"),  # Loga queries SQL no console apenas em dev
    pool_size=_pool_size,
    max_overflow=_max_overflow,
    pool_timeout=30,  # Espera até 30s por uma conexão livre antes de dar erro
)

# =====================================================================
# SESSION MAKER: Fábrica de sessões. A sessão é o "carrinho de compras"
# onde preparamos queries, inserts e updates antes do commit final.
# =====================================================================
async_session_factory = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,  # Evita expirar objetos da memória após o commit
    autoflush=False,  # Só envia as mudanças pro banco quando damos commit() explícito
)


# =====================================================================
# WORKER SESSION FACTORY (global): sessões seguras para Celery.
#
# Tasks Celery rodam corrotinas com asyncio.run(), que cria um event loop
# NOVO por execução. Conexões asyncpg ficam amarradas ao loop em que
# nasceram — reaproveitar o pool da API entre loops gera
# "Future attached to a different loop".
#
# NullPool resolve na raiz: nenhuma conexão sobrevive entre usos, então
# nenhuma cruza event loops. A engine em si é apenas configuração
# (thread/loop-safe) — não precisa de dispose por task.
# Em Supabase, usa transaction mode (porta 6543), que suporta centenas de
# conexões curtas; prepared statements desabilitados (exigência PgBouncer).
# =====================================================================
_worker_url = db_url
_worker_connect_args: dict[str, Any] = dict(connect_args)
if "supabase.com" in _worker_url:
    _worker_url = _worker_url.replace(":5432/", ":6543/")
    _worker_connect_args["prepared_statement_cache_size"] = 0
    _worker_connect_args["statement_cache_size"] = 0

worker_engine = create_async_engine(
    _worker_url,
    connect_args=_worker_connect_args,
    poolclass=NullPool,
)

worker_session_factory = async_sessionmaker(
    bind=worker_engine,
    expire_on_commit=False,
    autoflush=False,
)


def create_worker_session_factory() -> tuple[async_sessionmaker, Any]:
    """
    Cria engine + session factory frescos para uso em Celery workers.

    Dois problemas resolvidos aqui:
    1. asyncio.run() cria um novo event loop a cada task — NullPool evita
       "Future attached to a different loop" (sem conexões reaproveitadas).
    2. Supabase session mode (5432) tem limite de 15 conexões; workers usam
       transaction mode (6543), que suporta centenas. PgBouncer em transaction
       mode não suporta prepared statements — desabilitados via connect_args.
    """
    worker_url = db_url
    worker_connect_args = dict(connect_args)

    if "supabase.com" in worker_url:
        worker_url = worker_url.replace(":5432/", ":6543/")
        worker_connect_args["prepared_statement_cache_size"] = 0
        worker_connect_args["statement_cache_size"] = 0

    worker_engine = create_async_engine(
        worker_url,
        connect_args=worker_connect_args,
        poolclass=NullPool,
    )
    factory = async_sessionmaker(
        bind=worker_engine,
        expire_on_commit=False,
        autoflush=False,
    )
    return factory, worker_engine
