"""add performance indexes

Revision ID: 002_add_performance_indexes
Revises: 001_create_initial_tables
Create Date: 2026-03-08

Adiciona índices para queries críticas de performance:
  - processos.numero_cnj       → busca por CNJ sem escritorio_id (monitoramento)
  - processos.monitoramento_ativo → filtro do worker Celery
  - clientes.ativo             → filtro de clientes ativos (boas-vindas, notificações)
"""

from alembic import op

revision = "002_add_performance_indexes"
down_revision = "001_create_initial_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Busca de processo por número CNJ (webhook DataJud, lookup direto)
    op.create_index("ix_processos_numero_cnj", "processos", ["numero_cnj"])

    # Filtro do worker Celery que busca processos ativos para monitoramento
    op.create_index(
        "ix_processos_monitoramento_ativo",
        "processos",
        ["monitoramento_ativo"],
        postgresql_where="monitoramento_ativo = TRUE",
    )

    # Filtro de clientes ativos (boas-vindas em lote, notificações automáticas)
    op.create_index(
        "ix_clientes_ativo",
        "clientes",
        ["ativo"],
        postgresql_where="ativo = TRUE",
    )


def downgrade() -> None:
    op.drop_index("ix_clientes_ativo", table_name="clientes")
    op.drop_index("ix_processos_monitoramento_ativo", table_name="processos")
    op.drop_index("ix_processos_numero_cnj", table_name="processos")
