"""add documentos_cliente table

Revision ID: 20260628_2000
Revises: 20260628_1000_make_cpf_nullable_in_clientes
Create Date: 2026-06-28 20:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260628_2000"
down_revision = "20260628_1000_make_cpf_nullable_in_clientes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "documentos_cliente",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("escritorio_id", sa.Integer(), nullable=False),
        sa.Column("cliente_id", sa.Integer(), nullable=False),
        sa.Column("processo_id", sa.Integer(), nullable=True),
        sa.Column("nome", sa.String(length=500), nullable=False),
        sa.Column("arquivo_nome", sa.String(length=500), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("tamanho_bytes", sa.Integer(), nullable=False),
        sa.Column("tipo", sa.String(length=50), server_default="outro", nullable=False),
        sa.Column("conteudo", sa.LargeBinary(), nullable=False),
        sa.Column("ativo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
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
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["cliente_id"], ["clientes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["escritorio_id"], ["escritorios.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["processo_id"], ["processos.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_documentos_cliente_escritorio_id",
        "documentos_cliente",
        ["escritorio_id"],
    )
    op.create_index(
        "ix_documentos_cliente_cliente_id",
        "documentos_cliente",
        ["cliente_id"],
    )
    op.create_index(
        "ix_documentos_cliente_processo_id",
        "documentos_cliente",
        ["processo_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_documentos_cliente_processo_id", table_name="documentos_cliente")
    op.drop_index("ix_documentos_cliente_cliente_id", table_name="documentos_cliente")
    op.drop_index("ix_documentos_cliente_escritorio_id", table_name="documentos_cliente")
    op.drop_table("documentos_cliente")
