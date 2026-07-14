"""
Alembic environment — configurado para SQLAlchemy assíncrono (asyncpg).

Destaques:
  - Carrega .env via python-dotenv (necessário para o Alembic ler DATABASE_URL)
  - Usa create_async_engine + run_sync para suporte a async
  - Importa shared.models.Base para autogenerate detectar todos os models
  - Modo offline e online ambos suportados
"""

import asyncio
import os
import sys
from pathlib import Path

# Adiciona o diretório raiz do projeto ao sys.path
# para que o Alembic possa encontrar os módulos (como 'shared')
root_dir = Path(__file__).resolve().parents[1]
sys.path.append(str(root_dir))

from logging.config import fileConfig

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from alembic import context

# Carrega variáveis do .env antes de qualquer outra coisa
load_dotenv()

# Objeto de configuração do Alembic — acesso ao alembic.ini
config = context.config

# Configura logging conforme definido no alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ---------------------------------------------------------------------------
# Importa TODOS os models para o autogenerate detectar o schema completo.
# Se um model não for importado aqui, o Alembic não irá gerar a migration
# para ele. Adicione novos models conforme forem criados na Fase 1.
# ---------------------------------------------------------------------------
# fmt: off
from shared.models import Base  # noqa: F401 — importação obrigatória para autogenerate  # isort: skip
# fmt: on

target_metadata = Base.metadata


def get_database_url() -> str:
    """Lê DATABASE_URL do ambiente. Lança erro claro se ausente."""
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL não definida. " "Verifique seu arquivo .env ou variáveis de ambiente."
        )
    if not url.startswith("postgresql+asyncpg://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        
    from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
    _parsed = urlparse(url)
    _query = dict(parse_qsl(_parsed.query))
    for k in ["schema", "pgbouncer"]:
        _query.pop(k, None)
    url = urlunparse(_parsed._replace(query=urlencode(_query)))
        
    return url


# ===========================================================================
# MODO OFFLINE — gera SQL sem conectar ao banco
# Útil para revisar migrations antes de aplicar.
# Uso: alembic upgrade head --sql
# ===========================================================================
def run_migrations_offline() -> None:
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# ===========================================================================
# MODO ONLINE — conecta ao banco e aplica migrations
# ===========================================================================
def do_run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,  # detecta mudanças de tipo de coluna
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Cria engine assíncrona e executa migrations com run_sync."""
    url = get_database_url()

    connect_args = {}
    if "supabase.com" in url:
        connect_args["ssl"] = "require"

    connectable = create_async_engine(
        url, poolclass=NullPool, echo=False, connect_args=connect_args
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


# ---------------------------------------------------------------------------
# Ponto de entrada — Alembic chama este módulo diretamente
# ---------------------------------------------------------------------------
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
