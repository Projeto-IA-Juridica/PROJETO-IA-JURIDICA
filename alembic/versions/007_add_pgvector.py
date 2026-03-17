"""add pgvector and documentos_rag table

Revision ID: 007_add_pgvector
Revises: 002_add_performance_indexes
Create Date: 2026-03-17

Feature 1 — RAG Jurisprudencial por Escritório.
Ativa a extensão pgvector e cria a tabela documentos_rag
com índice IVFFlat para busca vetorial eficiente.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "007_add_pgvector"
down_revision = "002_add_performance_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # =========================================================================
    # 1. Ativa extensão pgvector
    # =========================================================================
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # =========================================================================
    # 2. Cria tabela documentos_rag
    # =========================================================================
    op.execute(
        """
        CREATE TABLE documentos_rag (
            id            SERIAL PRIMARY KEY,
            escritorio_id INTEGER NOT NULL REFERENCES escritorios(id) ON DELETE CASCADE,
            titulo        VARCHAR(500) NOT NULL,
            tipo          VARCHAR(50) NOT NULL,
            conteudo      TEXT NOT NULL,
            embedding     vector(1024) NOT NULL,
            metadata_json JSONB DEFAULT '{}',
            chunk_index   SMALLINT DEFAULT 0,
            doc_hash      VARCHAR(64),
            ativo         BOOLEAN DEFAULT TRUE,
            created_at    TIMESTAMPTZ DEFAULT NOW(),
            updated_at    TIMESTAMPTZ DEFAULT NOW()
        )
        """
    )

    # =========================================================================
    # 3. Índices
    # =========================================================================
    # HNSW para busca por similaridade coseno.
    # Preferido ao IVFFlat porque:
    #   - funciona em tabela vazia (IVFFlat requer dados no momento do CREATE INDEX)
    #   - recall estável com inserts incrementais sem reconstrução
    #   - sem necessidade de calibrar `lists` conforme volume cresce
    # m=16 / ef_construction=64 são os defaults do pgvector — adequados para até ~1M chunks.
    # Para recall máximo em prod: SET hnsw.ef_search = 80 na sessão de busca.
    op.execute(
        "CREATE INDEX ON documentos_rag USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )

    # Filtro por escritório + tipo + ativo (busca contextual multi-tenant)
    op.create_index(
        "ix_documentos_rag_escritorio_tipo_ativo",
        "documentos_rag",
        ["escritorio_id", "tipo", "ativo"],
    )

    # Deduplicação por hash do documento original
    op.create_index(
        "ix_documentos_rag_doc_hash",
        "documentos_rag",
        ["doc_hash"],
    )


def downgrade() -> None:
    op.drop_table("documentos_rag")
    op.execute("DROP EXTENSION IF EXISTS vector")
