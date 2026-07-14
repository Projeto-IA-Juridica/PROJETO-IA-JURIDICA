"""add alvos_vendas (máquina de vendas)

Revision ID: 20260714_1000
Revises: 20260707_1000
Create Date: 2026-07-14 10:00:00.000000

Cria a tabela alvos_vendas — pipeline de prospecção INTERNA (feature_vendas).
Aditiva e inerte: nenhuma tabela ou coluna existente é alterada. Quando a
máquina de vendas está desligada, a tabela apenas existe, sem uso.

O model vive em feature_vendas/models/alvo_vendas.py (fora de shared/) para
manter o código de vendas isolado; esta migração é escrita à mão e não importa
o model — só o DDL, já que há um único banco e uma única cadeia alembic.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "20260714_1000"
down_revision = "20260707_1000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alvos_vendas",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("escritorio_id", sa.Integer(), nullable=False),
        sa.Column("nome_escritorio", sa.String(length=200), nullable=False),
        sa.Column("nome_contato", sa.String(length=120), nullable=True),
        sa.Column("oab", sa.String(length=20), nullable=True),
        sa.Column("cnpj", sa.String(length=18), nullable=True),
        sa.Column("whatsapp", sa.String(length=20), nullable=False),
        sa.Column("cidade", sa.String(length=120), nullable=True),
        sa.Column("area", sa.String(length=80), nullable=True),
        sa.Column("score_icp", sa.SmallInteger(), nullable=True),
        sa.Column("classe_icp", sa.String(length=1), nullable=True),
        sa.Column("origem", sa.String(length=40), nullable=False, server_default="planilha"),
        sa.Column("processo_cnj", sa.String(length=30), nullable=True),
        sa.Column("movimentacao_bruta", sa.Text(), nullable=True),
        sa.Column("mensagem_espelho", sa.Text(), nullable=True),
        sa.Column("template_usado", sa.String(length=1), nullable=True),
        sa.Column("confianca_validacao", sa.SmallInteger(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="novo"),
        sa.Column("cliente_conversa_id", sa.Integer(), nullable=True),
        sa.Column("toques_enviados", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("ultimo_toque_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("proximo_toque_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("respondeu_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadados", JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["escritorio_id"], ["escritorios.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alvos_vendas_escritorio_id", "alvos_vendas", ["escritorio_id"])
    op.create_index("ix_alvos_vendas_oab", "alvos_vendas", ["oab"])
    op.create_index("ix_alvos_vendas_cnpj", "alvos_vendas", ["cnpj"])
    op.create_index("ix_alvos_vendas_whatsapp", "alvos_vendas", ["whatsapp"])
    op.create_index("ix_alvos_vendas_status", "alvos_vendas", ["status"])
    op.create_index("ix_alvos_vendas_proximo_toque_em", "alvos_vendas", ["proximo_toque_em"])


def downgrade() -> None:
    op.drop_index("ix_alvos_vendas_proximo_toque_em", table_name="alvos_vendas")
    op.drop_index("ix_alvos_vendas_status", table_name="alvos_vendas")
    op.drop_index("ix_alvos_vendas_whatsapp", table_name="alvos_vendas")
    op.drop_index("ix_alvos_vendas_cnpj", table_name="alvos_vendas")
    op.drop_index("ix_alvos_vendas_oab", table_name="alvos_vendas")
    op.drop_index("ix_alvos_vendas_escritorio_id", table_name="alvos_vendas")
    op.drop_table("alvos_vendas")
