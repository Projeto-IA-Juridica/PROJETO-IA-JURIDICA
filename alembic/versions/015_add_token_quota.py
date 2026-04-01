"""add token quota fields to escritorios

Revision ID: 015_add_token_quota
Revises: 014_add_cpf_version
Create Date: 2026-04-01

Adiciona controle de quota mensal de tokens Claude por escritório.
Limites padrão por plano:
  - basico:        500_000 tokens/mês
  - profissional: 2_000_000 tokens/mês
  - enterprise:   NULL (ilimitado)

Para ajustar o limite de um escritório específico:
  UPDATE escritorios SET quota_tokens_mes = 1000000 WHERE id = <id>;

Para resetar manualmente o contador:
  UPDATE escritorios SET tokens_usados_mes = 0, tokens_reset_em = NOW() WHERE id = <id>;
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "015_add_token_quota"
down_revision: Union[str, None] = "014_add_cpf_version"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "escritorios",
        sa.Column(
            "quota_tokens_mes",
            sa.BigInteger(),
            nullable=True,
            comment="Limite mensal de tokens Claude (input+output). NULL = ilimitado.",
        ),
    )
    op.add_column(
        "escritorios",
        sa.Column(
            "tokens_usados_mes",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
            comment="Total de tokens consumidos no mês corrente.",
        ),
    )
    op.add_column(
        "escritorios",
        sa.Column(
            "tokens_reset_em",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
            comment="Timestamp do último reset mensal do contador de tokens.",
        ),
    )

    # Popula quota_tokens_mes de acordo com o plano atual de cada escritório.
    # enterprise fica NULL (sem limite).
    op.execute("""
        UPDATE escritorios
        SET quota_tokens_mes = CASE plano
            WHEN 'basico'        THEN 500000
            WHEN 'profissional'  THEN 2000000
            ELSE NULL
        END
    """)


def downgrade() -> None:
    op.drop_column("escritorios", "tokens_reset_em")
    op.drop_column("escritorios", "tokens_usados_mes")
    op.drop_column("escritorios", "quota_tokens_mes")
