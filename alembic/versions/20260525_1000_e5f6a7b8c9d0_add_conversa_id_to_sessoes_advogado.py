"""add conversa_id to sessoes_advogado

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-05-25 10:00:00.000000

Agrupa múltiplas trocas Q&A em um thread de conversa.
conversa_id é gerado pelo frontend (crypto.randomUUID) e enviado com cada mensagem.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'e5f6a7b8c9d0'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'sessoes_advogado',
        sa.Column('conversa_id', postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        'ix_sessoes_advogado_conversa_id',
        'sessoes_advogado',
        ['conversa_id'],
    )


def downgrade() -> None:
    op.drop_index('ix_sessoes_advogado_conversa_id', table_name='sessoes_advogado')
    op.drop_column('sessoes_advogado', 'conversa_id')
