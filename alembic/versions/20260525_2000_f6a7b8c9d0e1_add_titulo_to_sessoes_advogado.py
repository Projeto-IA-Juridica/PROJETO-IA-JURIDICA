"""add titulo to sessoes_advogado for AI-generated conversation titles

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-05-25
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    col_exists = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name='sessoes_advogado' AND column_name='titulo'"
        )
    ).fetchone()
    if not col_exists:
        op.add_column(
            "sessoes_advogado",
            sa.Column(
                "titulo",
                sa.String(120),
                nullable=True,
                comment="Título gerado por Claude Haiku para exibição no histórico.",
            ),
        )


def downgrade() -> None:
    op.drop_column("sessoes_advogado", "titulo")
