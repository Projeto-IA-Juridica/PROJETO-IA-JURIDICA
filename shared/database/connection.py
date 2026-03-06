"""
shared/database/connection.py
==============================
Módulo responsável por gerenciar a conexão com o banco de dados PostgreSQL.

Utiliza a engine assíncrona do SQLAlchemy (asyncpg) para garantir alta performance
na aplicação FastAPI, permitindo concorrência sem bloquear a thread principal.
"""

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

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
connect_args = {}
if "supabase.com" in db_url:
    connect_args["ssl"] = "require"

engine = create_async_engine(
    db_url,
    connect_args=connect_args,
    echo=(settings.ENVIRONMENT == "development"),  # Loga queries SQL no console apenas em dev
    pool_size=20,  # Mantém 20 conexões abertas no pool (prontas para uso)
    max_overflow=10,  # Se as 20 estiverem em uso, cria até mais 10 temporárias
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
