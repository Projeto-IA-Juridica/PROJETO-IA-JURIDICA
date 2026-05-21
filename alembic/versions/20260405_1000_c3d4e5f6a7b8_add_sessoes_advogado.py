"""add_sessoes_advogado

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-04-05 10:00:00.000000

"""

from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sessoes_advogado",
        sa.Column("id", sa.Integer(), nullable=False),
        # TenantMixin
        sa.Column("escritorio_id", sa.Integer(), nullable=False),
        # TimestampMixin
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
            nullable=False,
        ),
        # Campos da sessão
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("mensagem_advogado", sa.Text(), nullable=False),
        sa.Column("resposta_hub", sa.Text(), nullable=False),
        sa.Column("intencao", sa.String(50), nullable=False, server_default="duvida_juridica"),
        sa.Column("modelo_ia", sa.String(50), nullable=False, server_default="claude_opus"),
        sa.Column("tokens_input", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens_output", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "custo_estimado",
            sa.Numeric(10, 6),
            nullable=False,
            server_default="0",
        ),
        sa.Column("cliente_referenciado_id", sa.Integer(), nullable=True),
        sa.Column("processo_referenciado_id", sa.Integer(), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        # Chaves primária e estrangeiras
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["escritorio_id"],
            ["escritorios.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuarios.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["cliente_referenciado_id"],
            ["clientes.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["processo_referenciado_id"],
            ["processos.id"],
            ondelete="SET NULL",
        ),
    )

    # Índice composto: filtra por escritório + advogado, ordena por data
    op.create_index(
        "ix_sessoes_advogado_usuario",
        "sessoes_advogado",
        ["usuario_id", "escritorio_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_sessoes_advogado_usuario", table_name="sessoes_advogado")
    op.drop_table("sessoes_advogado")
