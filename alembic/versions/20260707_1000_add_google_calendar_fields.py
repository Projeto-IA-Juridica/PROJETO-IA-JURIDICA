"""add google calendar fields

Revision ID: 20260707_1000
Revises: 20260630_1000
Create Date: 2026-07-07 10:00:00.000000

Integração Google Calendar do Agendamento Inteligente:

Altera escritorios:
- ADD COLUMN google_calendar_refresh_token (OAuth2, criptografado com Fernet)
- ADD COLUMN google_calendar_id (agenda alvo; NULL = primary)
- ADD COLUMN google_calendar_conectado_em

Altera agendamentos:
- ADD COLUMN google_event_id (evento criado na confirmação; sync best-effort)
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260707_1000"
down_revision = "20260630_1000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "escritorios",
        sa.Column(
            "google_calendar_refresh_token",
            sa.Text(),
            nullable=True,
            comment="Refresh token OAuth2 criptografado (Fernet)",
        ),
    )
    op.add_column(
        "escritorios",
        sa.Column(
            "google_calendar_id",
            sa.String(length=255),
            nullable=True,
            comment="ID da agenda alvo; None/'primary' = agenda principal da conta",
        ),
    )
    op.add_column(
        "escritorios",
        sa.Column(
            "google_calendar_conectado_em",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "agendamentos",
        sa.Column("google_event_id", sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agendamentos", "google_event_id")
    op.drop_column("escritorios", "google_calendar_conectado_em")
    op.drop_column("escritorios", "google_calendar_id")
    op.drop_column("escritorios", "google_calendar_refresh_token")
