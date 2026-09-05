"""add advogado_responsavel_id em clientes

Revision ID: 20260814_1000
Revises: 20260714_1000
Create Date: 2026-08-14 10:00:00.000000

Atribuição de responsabilidade por cliente.

Até aqui só `processos.advogado_responsavel_id` existia — e era preenchido
apenas pelos scripts de seed. Sem responsável no cliente não há para quem
enviar o alerta de alto risco nem em qual agenda diária o cliente entra.

Altera clientes:
- ADD COLUMN advogado_responsavel_id (FK usuarios, SET NULL, indexado)

Backfill: clientes que já têm processo recebem o responsável do processo mais
recente que tiver um. Clientes sem processo (ou com processos sem responsável)
ficam NULL e caem no fallback em runtime.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260814_1000"
down_revision = "20260714_1000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "clientes",
        sa.Column(
            "advogado_responsavel_id",
            sa.Integer(),
            nullable=True,
            comment="Advogado responsável pela conta do cliente",
        ),
    )
    op.create_foreign_key(
        "fk_clientes_advogado_responsavel",
        "clientes",
        "usuarios",
        ["advogado_responsavel_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_clientes_advogado_responsavel_id",
        "clientes",
        ["advogado_responsavel_id"],
    )

    # Backfill a partir do processo mais recente que tenha responsável.
    op.execute(
        """
        UPDATE clientes c
        SET advogado_responsavel_id = p.advogado_responsavel_id
        FROM (
            SELECT DISTINCT ON (cliente_id) cliente_id, advogado_responsavel_id
            FROM processos
            WHERE advogado_responsavel_id IS NOT NULL
            ORDER BY cliente_id, created_at DESC
        ) p
        WHERE c.id = p.cliente_id
          AND c.advogado_responsavel_id IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_clientes_advogado_responsavel_id", table_name="clientes")
    op.drop_constraint("fk_clientes_advogado_responsavel", "clientes", type_="foreignkey")
    op.drop_column("clientes", "advogado_responsavel_id")
