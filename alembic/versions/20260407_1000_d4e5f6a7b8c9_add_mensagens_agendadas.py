"""add_mensagens_agendadas

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-04-07 10:00:00.000000

Cria a tabela mensagens_agendadas para persistir mensagens WhatsApp
que foram bloqueadas por horário comercial ou rate-limit diário,
permitindo reenvio pelo worker dispatcher_agendadas.
"""

from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mensagens_agendadas",
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
        # Campos
        sa.Column("cliente_id", sa.Integer(), nullable=False),
        sa.Column("processo_id", sa.Integer(), nullable=True),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("motivo", sa.String(50), nullable=False),
        sa.Column("enviar_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="pendente"),
        sa.Column("tentativas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("enviada_em", sa.DateTime(timezone=True), nullable=True),
        # Chaves
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["escritorio_id"], ["escritorios.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["cliente_id"], ["clientes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["processo_id"], ["processos.id"], ondelete="SET NULL"),
    )

    # Índice principal do dispatcher: busca pendentes ordenadas por enviar_em
    op.create_index(
        "ix_mensagens_agendadas_dispatcher",
        "mensagens_agendadas",
        ["escritorio_id", "status", "enviar_em"],
    )


def downgrade() -> None:
    op.drop_index("ix_mensagens_agendadas_dispatcher", table_name="mensagens_agendadas")
    op.drop_table("mensagens_agendadas")
