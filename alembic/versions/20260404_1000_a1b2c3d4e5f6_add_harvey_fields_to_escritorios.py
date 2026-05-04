"""add_escalacao_fields_to_escritorios

Revision ID: a1b2c3d4e5f6
Revises: 35d8599fb2c0
Create Date: 2026-04-04 10:00:00.000000-03:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "35d8599fb2c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "escritorios",
        sa.Column("escalacao_habilitada", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "escritorios",
        sa.Column("escalacao_canal_advogado_numero", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "escritorios",
        sa.Column(
            "escalacao_quota_tokens_mes",
            sa.Integer(),
            server_default="500000",
            nullable=False,
        ),
    )
    op.add_column(
        "escritorios",
        sa.Column(
            "escalacao_tokens_usados_mes",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "escritorios",
        sa.Column(
            "escalacao_confidence_threshold",
            sa.Float(),
            server_default="0.70",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("escritorios", "escalacao_confidence_threshold")
    op.drop_column("escritorios", "escalacao_tokens_usados_mes")
    op.drop_column("escritorios", "escalacao_quota_tokens_mes")
    op.drop_column("escritorios", "escalacao_canal_advogado_numero")
    op.drop_column("escritorios", "escalacao_habilitada")
