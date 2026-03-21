"""add_crm_cliente

Revision ID: 009_add_crm_cliente
Revises: e4bcb5d405fa
Create Date: 2026-03-21

Adiciona colunas CRM à tabela clientes:
- crm_nivel: classificação de satisfação (excelente/satisfeito/neutro/em_risco/critico)
- crm_score: score composto 0–100 calculado deterministicamente
- crm_resumo: texto gerado pelo Claude explicando a classificação
- crm_acao_sugerida: ação concreta sugerida pelo Claude para o advogado
- crm_analisado_em: timestamp da última análise
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "009_add_crm_cliente"
down_revision: Union[str, None] = "e4bcb5d405fa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CRM_NIVEL_ENUM = sa.Enum(
    "excelente",
    "satisfeito",
    "neutro",
    "em_risco",
    "critico",
    name="crm_nivel_enum",
)


def upgrade() -> None:
    CRM_NIVEL_ENUM.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "clientes",
        sa.Column(
            "crm_nivel",
            CRM_NIVEL_ENUM,
            nullable=True,
            comment="excelente | satisfeito | neutro | em_risco | critico",
        ),
    )
    op.add_column(
        "clientes",
        sa.Column(
            "crm_score",
            sa.SmallInteger(),
            nullable=True,
            comment="Score composto 0–100 calculado deterministicamente",
        ),
    )
    op.add_column(
        "clientes",
        sa.Column(
            "crm_resumo",
            sa.Text(),
            nullable=True,
            comment="Texto gerado pelo Claude explicando o porquê da classificação (≤ 3 frases)",
        ),
    )
    op.add_column(
        "clientes",
        sa.Column(
            "crm_acao_sugerida",
            sa.Text(),
            nullable=True,
            comment="Ação concreta sugerida pelo Claude para o advogado",
        ),
    )
    op.add_column(
        "clientes",
        sa.Column(
            "crm_analisado_em",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp de quando a análise CRM foi calculada",
        ),
    )

    op.create_index(
        "ix_clientes_escritorio_crm_nivel",
        "clientes",
        ["escritorio_id", "crm_nivel"],
    )
    op.create_index(
        "ix_clientes_escritorio_crm_analisado_em",
        "clientes",
        ["escritorio_id", "crm_analisado_em"],
        postgresql_where=sa.text("crm_nivel IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_clientes_escritorio_crm_analisado_em",
        table_name="clientes",
    )
    op.drop_index(
        "ix_clientes_escritorio_crm_nivel",
        table_name="clientes",
    )

    op.drop_column("clientes", "crm_analisado_em")
    op.drop_column("clientes", "crm_acao_sugerida")
    op.drop_column("clientes", "crm_resumo")
    op.drop_column("clientes", "crm_score")
    op.drop_column("clientes", "crm_nivel")
    CRM_NIVEL_ENUM.drop(op.get_bind(), checkfirst=True)
