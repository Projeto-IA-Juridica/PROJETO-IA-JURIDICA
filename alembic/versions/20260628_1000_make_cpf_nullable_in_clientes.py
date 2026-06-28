"""make_cpf_nullable_in_clientes

Revision ID: 20260628_cpf_nullable
Revises: 20260621_fix_leads
Create Date: 2026-06-28

Torna o campo `cpf` opcional em `clientes` para permitir cadastro manual
pelo advogado sem CPF disponível no momento do cadastro.

PostgreSQL permite múltiplos NULLs na unique constraint existente
(uq_clientes_escritorio_cpf), portanto não é necessário alterar o índice.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260628_cpf_nullable"
down_revision: Union[str, None] = "20260621_fix_leads"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "clientes",
        "cpf",
        existing_type=sa.String(100),
        nullable=True,
    )
    op.alter_column(
        "clientes",
        "cpf_version",
        existing_type=sa.SmallInteger(),
        nullable=True,
    )


def downgrade() -> None:
    # Preenche NULLs com placeholder antes de tornar NOT NULL novamente
    op.execute("UPDATE clientes SET cpf = '' WHERE cpf IS NULL")
    op.execute("UPDATE clientes SET cpf_version = 1 WHERE cpf_version IS NULL")
    op.alter_column(
        "clientes",
        "cpf",
        existing_type=sa.String(100),
        nullable=False,
    )
    op.alter_column(
        "clientes",
        "cpf_version",
        existing_type=sa.SmallInteger(),
        nullable=False,
    )
