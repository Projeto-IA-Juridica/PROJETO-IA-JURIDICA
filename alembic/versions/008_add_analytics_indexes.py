"""add analytics indexes

Revision ID: 008_add_analytics_indexes
Revises: 004
Create Date: 2026-03-19 15:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '008_add_analytics_indexes'
down_revision: Union[str, None] = '004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Índice para busca de interações recentes do escritório (paginação do painel)
    op.create_index(
        'ix_interacoes_escritorio_created_desc', 
        'interacoes', 
        ['escritorio_id', sa.text('created_at DESC')]
    )
    
    # 2. Índice filtrado para cálculo rápido de NPS/Satisfação (onde houver nota)
    op.create_index(
        'ix_interacoes_escritorio_satisfacao',
        'interacoes',
        ['escritorio_id', 'satisfacao'],
        postgresql_where=sa.text('satisfacao IS NOT NULL')
    )
    
    # 3. Índice para filtros compostos de direção (dashboard costuma segmentar IA vs Cliente)
    op.create_index(
        'ix_interacoes_escritorio_direcao_created', 
        'interacoes', 
        ['escritorio_id', 'direcao', 'created_at']
    )
    
    # 4. Índice para agrupar as últimas interações por cliente, rápido (ex: listar contatos recentes)
    op.create_index(
        'ix_interacoes_cliente_created_desc', 
        'interacoes', 
        ['cliente_id', sa.text('created_at DESC')]
    )


def downgrade() -> None:
    op.drop_index('ix_interacoes_cliente_created_desc', table_name='interacoes')
    op.drop_index('ix_interacoes_escritorio_direcao_created', table_name='interacoes')
    op.drop_index('ix_interacoes_escritorio_satisfacao', table_name='interacoes')
    op.drop_index('ix_interacoes_escritorio_created_desc', table_name='interacoes')
