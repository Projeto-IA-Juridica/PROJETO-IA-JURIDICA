"""add_modelo_ia_to_interacoes

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-04 10:01:00.000000-03:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "interacoes",
        sa.Column(
            "modelo_ia",
            sa.String(length=50),
            server_default="claude",
            nullable=False,
            comment="IA que gerou a resposta: claude | claude_opus | claude_opus_fallback",
        ),
    )


def downgrade() -> None:
    op.drop_column("interacoes", "modelo_ia")
