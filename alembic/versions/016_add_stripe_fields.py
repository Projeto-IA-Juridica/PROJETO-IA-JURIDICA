"""add stripe billing fields to escritorios

Revision ID: 016_add_stripe_fields
Revises: 015_add_token_quota
Create Date: 2026-05-27

Adiciona campos de cobrança Stripe ao tenant raiz (escritorios).

Campos adicionados:
  stripe_customer_id      → ID do Customer no Stripe (cus_xxx)
  stripe_subscription_id  → ID da Subscription ativa (sub_xxx)
  stripe_price_id         → ID do Price do plano atual (price_xxx)
  assinatura_status       → Estado da assinatura:
                              trialing  → trial ativo (ainda não pagou)
                              active    → assinatura ativa e em dia
                              past_due  → pagamento atrasado
                              canceled  → assinatura cancelada
                              unpaid    → múltiplas falhas, assinatura suspensa
                              incomplete→ checkout iniciado mas não concluído
  trial_expira_em         → Timestamp de expiração do trial
  assinatura_expira_em    → Timestamp de expiração do período corrente

Nota de migração:
  Escritórios existentes recebem assinatura_status = 'active' para não
  serem bloqueados pela guard de assinatura (grandfathering). Novos
  escritórios criados após essa migration começarão com 'trialing'.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "016_add_stripe_fields"
down_revision: Union[str, None] = "015_add_token_quota"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Campos Stripe ──────────────────────────────────────────────────────────
    op.add_column(
        "escritorios",
        sa.Column(
            "stripe_customer_id",
            sa.String(50),
            nullable=True,
            comment="ID do Customer no Stripe (cus_xxx). NULL = ainda não tem conta Stripe.",
        ),
    )
    op.add_column(
        "escritorios",
        sa.Column(
            "stripe_subscription_id",
            sa.String(50),
            nullable=True,
            comment="ID da Subscription ativa (sub_xxx). NULL = sem assinatura ativa.",
        ),
    )
    op.add_column(
        "escritorios",
        sa.Column(
            "stripe_price_id",
            sa.String(50),
            nullable=True,
            comment="Price ID do plano atual no Stripe (price_xxx).",
        ),
    )
    op.add_column(
        "escritorios",
        sa.Column(
            "assinatura_status",
            sa.String(20),
            nullable=False,
            server_default="trialing",
            comment=(
                "Status da assinatura: "
                "trialing | active | past_due | canceled | unpaid | incomplete"
            ),
        ),
    )
    op.add_column(
        "escritorios",
        sa.Column(
            "trial_expira_em",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
            comment="Timestamp de expiração do período trial.",
        ),
    )
    op.add_column(
        "escritorios",
        sa.Column(
            "assinatura_expira_em",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
            comment="Timestamp de expiração do período de cobrança corrente.",
        ),
    )

    # ── Índices para buscas frequentes nos webhooks ────────────────────────────
    op.create_index(
        "ix_escritorios_stripe_customer_id",
        "escritorios",
        ["stripe_customer_id"],
    )
    op.create_index(
        "ix_escritorios_stripe_subscription_id",
        "escritorios",
        ["stripe_subscription_id"],
    )

    # ── Grandfathering: escritórios existentes ficam 'active' ─────────────────
    # Evita bloquear clientes que já estavam usando a plataforma antes da
    # integração Stripe. Novos escritórios começam com 'trialing' (server_default).
    op.execute("UPDATE escritorios SET assinatura_status = 'active'")

    # ── Adiciona plano 'escritorio' ao constraint CHECK se existir ─────────────
    # (PostgreSQL não tem enum nativo aqui — apenas VARCHAR; sem constraint CHECK
    # para manter flexibilidade de adicionar planos futuros sem nova migration)


def downgrade() -> None:
    op.drop_index("ix_escritorios_stripe_subscription_id", table_name="escritorios")
    op.drop_index("ix_escritorios_stripe_customer_id", table_name="escritorios")
    op.drop_column("escritorios", "assinatura_expira_em")
    op.drop_column("escritorios", "trial_expira_em")
    op.drop_column("escritorios", "assinatura_status")
    op.drop_column("escritorios", "stripe_price_id")
    op.drop_column("escritorios", "stripe_subscription_id")
    op.drop_column("escritorios", "stripe_customer_id")
