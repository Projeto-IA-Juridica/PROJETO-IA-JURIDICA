"""add_tipo_lead_e_dna_prospeccao

Revision ID: 012_add_tipo_lead_e_dna
Revises: 011_add_leads_prospeccao
Create Date: 2026-03-23

Complementa a Feature 3 — Prospecção Inteligente:
  - leads_prospeccao.tipo_lead: distingue lead de empresa (B2B) de pessoa física (B2C)
  - escritorios.dna_prospeccao: armazena o perfil de especialização gerado pelo DNAAdvogadoService
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "012_add_tipo_lead_e_dna"
down_revision: Union[str, None] = "011_add_leads_prospeccao"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- leads_prospeccao: tipo_lead ---
    op.add_column(
        "leads_prospeccao",
        sa.Column(
            "tipo_lead",
            sa.String(10),
            server_default="empresa",
            nullable=False,
        ),
    )
    op.create_index(
        "ix_leads_tipo",
        "leads_prospeccao",
        ["escritorio_id", "tipo_lead"],
    )

    # --- escritorios: dna_prospeccao ---
    op.add_column(
        "escritorios",
        sa.Column("dna_prospeccao", JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("escritorios", "dna_prospeccao")
    op.drop_index("ix_leads_tipo", table_name="leads_prospeccao")
    op.drop_column("leads_prospeccao", "tipo_lead")
