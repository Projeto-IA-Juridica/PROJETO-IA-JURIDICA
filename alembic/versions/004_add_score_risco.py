"""004_add_score_risco

Adiciona colunas de score de risco processual na tabela `processos`.

Score de complexidade/risco (0–100) para uso interno do advogado.
NÃO representa probabilidade de vitória — compliance OAB Provimento 205/2021.
Calculado pelo worker monitor_processos.py a cada ciclo de monitoramento.

Revision ID: 004
Revises: e4bcb5d405fa
Create Date: 2026-03-18
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = "004"
down_revision = "e4bcb5d405fa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "processos",
        sa.Column(
            "score_risco",
            sa.SmallInteger(),
            nullable=True,
            comment="Score de complexidade/risco 0–100 (uso interno do advogado)",
        ),
    )
    op.add_column(
        "processos",
        sa.Column(
            "score_nivel",
            sa.String(20),
            nullable=True,
            comment="baixo | moderado | alto | critico",
        ),
    )
    op.add_column(
        "processos",
        sa.Column(
            "score_componentes",
            JSONB(),
            nullable=True,
            comment="Detalhamento dos 5 componentes do score para o painel do advogado",
        ),
    )
    op.add_column(
        "processos",
        sa.Column(
            "score_interpretacao",
            sa.Text(),
            nullable=True,
            comment="Texto explicativo para o advogado — sem previsão de resultado",
        ),
    )
    op.add_column(
        "processos",
        sa.Column(
            "score_atualizado_em",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
        ),
    )

    # Índice parcial — apenas processos com score já calculado.
    # Evita bloat: processos novos (score IS NULL) ficam fora do índice.
    op.create_index(
        "ix_processos_escritorio_score_risco",
        "processos",
        ["escritorio_id", "score_risco"],
        postgresql_where=sa.text("score_risco IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_processos_escritorio_score_risco", table_name="processos")
    op.drop_column("processos", "score_atualizado_em")
    op.drop_column("processos", "score_interpretacao")
    op.drop_column("processos", "score_componentes")
    op.drop_column("processos", "score_nivel")
    op.drop_column("processos", "score_risco")