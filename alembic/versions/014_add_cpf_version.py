"""add cpf_version to clientes for encryption key rotation support

Revision ID: 014_add_cpf_version
Revises: 013_add_composite_indexes
Create Date: 2026-03-30

Adiciona coluna cpf_version à tabela clientes para suportar rotação segura
da ENCRYPTION_KEY sem quebrar todos os CPFs existentes.

Como fazer rotação de chave:
  1. Gere nova chave: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  2. Configure no .env:
       ENCRYPTION_KEY=<nova_chave>
       ENCRYPTION_KEY_PREVIOUS=<chave_atual>
  3. Execute script de re-criptografia (re-encrypts all CPFs with new key, bumps cpf_version)
  4. Quando todos os registros tiverem cpf_version=2, remova ENCRYPTION_KEY_PREVIOUS
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "014_add_cpf_version"
down_revision: Union[str, None] = "013_add_composite_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    col_exists = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name='clientes' AND column_name='cpf_version'"
        )
    ).fetchone()
    if not col_exists:
        op.add_column(
            "clientes",
            sa.Column(
                "cpf_version",
                sa.SmallInteger(),
                nullable=False,
                server_default="1",
                comment=(
                    "Versão da chave Fernet usada para criptografar o CPF. "
                    "Incrementar ao rotar ENCRYPTION_KEY."
                ),
            ),
        )


def downgrade() -> None:
    op.drop_column("clientes", "cpf_version")
