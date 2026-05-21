"""add_leads_prospeccao

Revision ID: 011_add_leads_prospeccao
Revises: 010_add_escalacao_status_index
Create Date: 2026-03-23

Cria a tabela leads_prospeccao para a Feature 3 — Prospecção Inteligente.
Armazena leads qualificados por CNPJ com dados da Receita Federal, DataJud
e LinkedIn, além do score de afinidade gerado pelo MatchingService.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "011_add_leads_prospeccao"
down_revision: Union[str, None] = "010_add_escalacao_status_index"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "leads_prospeccao",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("escritorio_id", sa.Integer(), nullable=False),
        sa.Column("cnpj", sa.String(18), nullable=False),
        sa.Column("empresa_nome", sa.String(500), nullable=False),
        sa.Column("empresa_setor", sa.String(200), nullable=True),
        sa.Column("empresa_porte", sa.String(50), nullable=True),
        sa.Column("socios", JSONB(), server_default="[]", nullable=False),
        sa.Column("processos_publicos", JSONB(), server_default="[]", nullable=False),
        sa.Column("contatos_linkedin", JSONB(), server_default="[]", nullable=False),
        sa.Column("score_match", sa.SmallInteger(), nullable=True),
        sa.Column("score_motivo", sa.Text(), nullable=True),
        sa.Column("abordagem_sugerida", sa.Text(), nullable=True),
        sa.Column("status", sa.String(50), server_default="novo", nullable=False),
        sa.Column("notas_advogado", sa.Text(), nullable=True),
        sa.Column("fonte_descoberta", sa.String(100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["escritorio_id"], ["escritorios.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("escritorio_id", "cnpj", name="uq_lead_escritorio_cnpj"),
    )

    # Índice para listar pipeline ranqueado por score
    op.execute(
        """
        CREATE INDEX ix_leads_score
        ON leads_prospeccao (escritorio_id, score_match DESC)
        WHERE score_match IS NOT NULL
        """
    )

    # Índice para filtrar por status (novo / contatado / qualificado / descartado)
    op.create_index(
        "ix_leads_status",
        "leads_prospeccao",
        ["escritorio_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_leads_status", table_name="leads_prospeccao")
    op.execute("DROP INDEX IF EXISTS ix_leads_score")
    op.drop_table("leads_prospeccao")
