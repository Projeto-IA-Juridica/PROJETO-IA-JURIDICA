"""
scripts/setup/init_db.py
=========================
Inicializa o banco de dados: aplica todas as migrations Alembic
e verifica se as tabelas foram criadas com sucesso.

Uso:
    python -m scripts.setup.init_db
    # ou via Makefile:
    make db-init
"""

import asyncio
import sys
from pathlib import Path

# Garante que a raiz do projeto está no PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from shared.database.connection import engine


def run_migrations() -> None:
    """Executa as migrations Alembic (equivale a `alembic upgrade head`)."""
    root = Path(__file__).resolve().parents[2]
    alembic_cfg = Config(str(root / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(root / "alembic"))

    print("Aplicando migrations...")
    command.upgrade(alembic_cfg, "head")
    print("Migrations aplicadas com sucesso.")


async def verify_tables() -> None:
    """Verifica se as 5 tabelas foram criadas no banco."""
    tabelas_esperadas = [
        "escritorios",
        "usuarios",
        "clientes",
        "processos",
        "interacoes",
    ]

    async with engine.connect() as conn:
        for tabela in tabelas_esperadas:
            result = await conn.execute(
                text(
                    "SELECT EXISTS ("
                    "  SELECT FROM information_schema.tables"
                    "  WHERE table_schema = 'public'"
                    "  AND table_name = :tabela"
                    ")"
                ),
                {"tabela": tabela},
            )
            existe = result.scalar()
            status = "OK" if existe else "FALTANDO"
            print(f"  [{status}] {tabela}")

    await engine.dispose()


def main() -> None:
    print("=" * 50, flush=True)
    print(" Inicializando banco de dados", flush=True)
    print("=" * 50, flush=True)

    run_migrations()

    print("\nVerificando tabelas criadas:", flush=True)
    asyncio.run(verify_tables())

    print("\nBanco de dados pronto.", flush=True)
    print("Próximo passo: python -m scripts.setup.seed_data")


if __name__ == "__main__":
    main()
