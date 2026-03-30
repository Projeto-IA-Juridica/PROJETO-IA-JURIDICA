"""add composite indexes for webhook hot paths and process queries

Revision ID: 013_add_composite_indexes
Revises: e4bcb5d405fa
Create Date: 2026-03-30

Adiciona índices compostos ausentes que causam full scan em produção com >1K processos:

1. clientes(telefone_whatsapp, escritorio_id)
   Hot path do webhook: toda mensagem WhatsApp executa
   WHERE telefone_whatsapp = ? AND escritorio_id = ?
   O índice simples ix_clientes_telefone_whatsapp exige heap fetch para filtrar escritorio_id.

2. escritorios(webhook_whatsapp_instance)
   Primeira query de todo evento webhook. A coluna não tem nenhum índice.

3. processos(cliente_id, status)
   query_processo_ativo_do_cliente: WHERE cliente_id = ? AND status = 'ativo' LIMIT 1
   Chamado para cada cliente no worker de relacionamento.

4. usuarios(whatsapp_numero, escritorio_id)
   Lookup de advogado no webhook (escalação): sem índice desde a migration e4bcb5d.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "013_add_composite_indexes"
down_revision: Union[str, None] = "e4bcb5d405fa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Webhook hot path: lookup por telefone dentro do escritório
    # Cobre a query: WHERE telefone_whatsapp = ? AND escritorio_id = ?
    op.create_index(
        "ix_clientes_telefone_escritorio",
        "clientes",
        ["telefone_whatsapp", "escritorio_id"],
    )

    # 2. Lookup da instância Evolution em todo evento webhook
    # Cobre: WHERE webhook_whatsapp_instance = ?
    # Parcial: exclui escritórios sem WhatsApp configurado (NULL) do índice
    op.create_index(
        "ix_escritorios_webhook_instance",
        "escritorios",
        ["webhook_whatsapp_instance"],
        postgresql_where=sa.text("webhook_whatsapp_instance IS NOT NULL"),
    )

    # 3. Query de processo ativo por cliente (worker de relacionamento)
    # Cobre: WHERE cliente_id = ? AND status = 'ativo' LIMIT 1
    op.create_index(
        "ix_processos_cliente_status",
        "processos",
        ["cliente_id", "status"],
    )

    # 4. Lookup de advogado por WhatsApp no webhook (resposta de escalação)
    # Cobre: WHERE whatsapp_numero = ? AND escritorio_id = ? AND ativo = TRUE AND escalacao_ativa = TRUE
    # Parcial: exclui advogados sem WhatsApp configurado (NULL)
    op.create_index(
        "ix_usuarios_whatsapp_escritorio",
        "usuarios",
        ["whatsapp_numero", "escritorio_id"],
        postgresql_where=sa.text("whatsapp_numero IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_usuarios_whatsapp_escritorio", table_name="usuarios")
    op.drop_index("ix_processos_cliente_status", table_name="processos")
    op.drop_index("ix_escritorios_webhook_instance", table_name="escritorios")
    op.drop_index("ix_clientes_telefone_escritorio", table_name="clientes")
