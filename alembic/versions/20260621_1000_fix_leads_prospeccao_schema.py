"""fix_leads_prospeccao_schema

Revision ID: 20260621_fix_leads
Revises: 272dee696f72
Create Date: 2026-06-21

Sincroniza a tabela leads_prospeccao com o modelo SQLAlchemy atual.

Mudanças:
  - Renomeia empresa_nome → nome (suporte a leads B2C — pessoa física)
  - Altera cnpj para nullable e String(50) (B2C tem cnpj=None; B2B usava String(18))
  - Remove processos_publicos (JSONB) — coluna órfã substituída por processos_publicos_count
  - Adiciona polo_processo, tipo_acao_origem, numero_cnj_exemplo (campos B2C)
  - Adiciona processos_publicos_count (SmallInteger)
  - Adiciona linkedin_disponivel (Boolean)
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260621_fix_leads"
down_revision: Union[str, None] = "272dee696f72"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)
    cols = [c["name"] for c in inspector.get_columns("leads_prospeccao")]

    # 1. Adiciona nome como nullable
    if "nome" not in cols:
        op.add_column(
            "leads_prospeccao",
            sa.Column("nome", sa.String(500), nullable=True),
        )

    # 2. Copia empresa_nome → nome
    if "empresa_nome" in cols:
        op.execute("UPDATE leads_prospeccao SET nome = empresa_nome WHERE nome IS NULL")
        # 3. Remove empresa_nome
        op.drop_column("leads_prospeccao", "empresa_nome")

    # 3. Torna nome NOT NULL
    op.alter_column("leads_prospeccao", "nome", nullable=False)

    # 4. Altera cnpj: NOT NULL → nullable e String(18) → String(50)
    op.alter_column(
        "leads_prospeccao",
        "cnpj",
        existing_type=sa.String(18),
        type_=sa.String(50),
        nullable=True,
    )

    # 5. Remove coluna órfã processos_publicos
    if "processos_publicos" in cols:
        op.drop_column("leads_prospeccao", "processos_publicos")

    # 6. Adiciona campos B2C
    if "polo_processo" not in cols:
        op.add_column(
            "leads_prospeccao",
            sa.Column("polo_processo", sa.String(50), nullable=True),
        )
    if "tipo_acao_origem" not in cols:
        op.add_column(
            "leads_prospeccao",
            sa.Column("tipo_acao_origem", sa.String(300), nullable=True),
        )
    if "numero_cnj_exemplo" not in cols:
        op.add_column(
            "leads_prospeccao",
            sa.Column("numero_cnj_exemplo", sa.String(50), nullable=True),
        )

    # 7. Adiciona contador de processos públicos
    if "processos_publicos_count" not in cols:
        op.add_column(
            "leads_prospeccao",
            sa.Column(
                "processos_publicos_count",
                sa.SmallInteger(),
                server_default="0",
                nullable=False,
            ),
        )

    # 8. Adiciona flag de LinkedIn disponível
    if "linkedin_disponivel" not in cols:
        op.add_column(
            "leads_prospeccao",
            sa.Column(
                "linkedin_disponivel",
                sa.Boolean(),
                server_default="false",
                nullable=False,
            ),
        )


def downgrade() -> None:
    op.drop_column("leads_prospeccao", "linkedin_disponivel")
    op.drop_column("leads_prospeccao", "processos_publicos_count")
    op.drop_column("leads_prospeccao", "numero_cnj_exemplo")
    op.drop_column("leads_prospeccao", "tipo_acao_origem")
    op.drop_column("leads_prospeccao", "polo_processo")

    # Reverte cnpj para String(18) NOT NULL (com placeholder para linhas B2C)
    op.execute("UPDATE leads_prospeccao SET cnpj = 'N/A' WHERE cnpj IS NULL")
    op.alter_column(
        "leads_prospeccao",
        "cnpj",
        existing_type=sa.String(50),
        type_=sa.String(18),
        nullable=False,
    )

    # Recria processos_publicos (órfã)
    from sqlalchemy.dialects.postgresql import JSONB

    op.add_column(
        "leads_prospeccao",
        sa.Column("processos_publicos", JSONB(), server_default="[]", nullable=False),
    )

    # Reverte nome → empresa_nome
    op.add_column(
        "leads_prospeccao",
        sa.Column("empresa_nome", sa.String(500), nullable=True),
    )
    op.execute("UPDATE leads_prospeccao SET empresa_nome = nome")
    op.alter_column("leads_prospeccao", "empresa_nome", nullable=False)
    op.drop_column("leads_prospeccao", "nome")
