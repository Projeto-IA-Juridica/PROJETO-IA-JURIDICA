"""add processo state columns

Revision ID: 003_add_processo_state
Revises: 002_add_performance_indexes
Create Date: 2026-03-17

Adiciona colunas de estado processual à tabela processos:
  - estado_atual JSONB — snapshot do estado: fase, andamentos recentes, próximo passo esperado
  - fase_processual VARCHAR(100) — fase atual do processo no ciclo judicial
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "003_add_processo_state"
down_revision = "002_add_performance_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Snapshot do estado atual do processo (fase, últimos andamentos, próximo passo)
    op.add_column(
        "processos",
        sa.Column(
            "estado_atual",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment=(
                "Snapshot do estado processual: fase, ultimos_andamentos, "
                "proximo_passo_esperado. Atualizado a cada novo andamento detectado."
            ),
        ),
    )

    # Fase processual textual para indexação e filtragem eficiente
    op.add_column(
        "processos",
        sa.Column(
            "fase_processual",
            sa.String(100),
            nullable=True,
            comment=(
                "Fase atual do processo: conhecimento | instrucao | saneamento | "
                "julgamento | recurso | execucao | encerrado"
            ),
        ),
    )

    # Índice composto para queries do worker e dashboard do escritório
    op.create_index(
        "ix_processos_escritorio_fase",
        "processos",
        ["escritorio_id", "fase_processual"],
        postgresql_where=sa.text("fase_processual IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_processos_escritorio_fase", table_name="processos")
    op.drop_column("processos", "fase_processual")
    op.drop_column("processos", "estado_atual")
