"""add_escalacao_status_index

Revision ID: 010_add_escalacao_status_index
Revises: 009_add_crm_cliente
Create Date: 2026-03-21

Adiciona índice de expressão PostgreSQL sobre metadata_json->>'escalacao_status'
na tabela interacoes para acelerar as queries de escalação (verificar_escalacoes_pendentes,
EscalacaoManager) que filtram por status pendente/rejeitada.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "010_add_escalacao_status_index"
down_revision: Union[str, None] = "009_add_crm_cliente"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_interacoes_escalacao_status
        ON interacoes ((metadata_json->>'escalacao_status'))
        WHERE metadata_json->>'escalacao_status' IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_interacoes_escalacao_status")
