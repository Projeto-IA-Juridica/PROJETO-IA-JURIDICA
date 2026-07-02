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

if "supabase.com" in db_url:
    # Supabase Free tier limita a 15 conexões simultâneas no pooler de sessão
    # (compartilhado entre esta API, os workers Celery e qualquer outra sessão
    # conectada ao projeto) — por isso o pool aqui precisa ser bem enxuto.
    _pool_size, _max_overflow = 3, 2
else:
    # Postgres dedicado (CI com container próprio, docker-compose local,
    # self-hosted) não tem esse teto artificial. Um pool de 5 conexões totais
    # virava gargalo sob carga concorrente — visto no smoke load test do CI,
    # onde /health/ready enfileirava atrás de outras requisições e estourava
    # o SLA de latência mesmo sem nenhum erro real.
    _pool_size, _max_overflow = 10, 10

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
