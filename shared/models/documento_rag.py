"""
shared/models/documento_rag.py
================================
Model SQLAlchemy para a tabela documentos_rag.

Cada registro representa um chunk de documento vetorizado,
isolado por escritório (multi-tenant via TenantMixin).

Tipos suportados: peticao | sentenca | jurisprudencia | tese | parecer

Dimensão do vetor: 1024D
  - Provedor primário:  Voyage AI voyage-law-2  (1024D nativo, especializado em jurídico)
  - Provedor fallback:  OpenAI text-embedding-3-small com dimensions=1024
  Ambos os provedores são forçados a 1024D para garantir compatibilidade da coluna.
  Anthropic não possui API nativa de embeddings — a dimensão 1536D do TASKS.md
  foi corrigida aqui.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy import Boolean, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from shared.models.base import Base, TenantMixin, TimestampMixin
from pgvector.sqlalchemy import Vector

TIPOS_VALIDOS = frozenset(
    {"peticao", "sentenca", "jurisprudencia", "tese", "parecer"}
)

# Dimensão fixa usada pela coluna e por todos os geradores de embedding.
# Alterar aqui exige nova migration + reindexação completa.
EMBEDDING_DIM = 1024


class DocumentoRag(Base, TenantMixin, TimestampMixin):
    """
    Tabela: documentos_rag

    Armazena chunks de documentos jurídicos com seus embeddings vetoriais.
    A busca por similaridade é feita via pgvector usando o índice HNSW.

    Campos de metadata_json (convenção, não obrigatório):
      tribunal, vara, tipo_acao, data_doc, resultado, tags
    """

    __tablename__ = "documentos_rag"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    titulo: Mapped[str] = mapped_column(String(500), nullable=False)

    # peticao | sentenca | jurisprudencia | tese | parecer
    tipo: Mapped[str] = mapped_column(String(50), nullable=False)

    conteudo: Mapped[str] = mapped_column(Text, nullable=False)

    # Vetor 1024D — Voyage AI voyage-law-2 ou OpenAI text-embedding-3-small(dim=1024)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)

    # Metadados opcionais: tribunal, vara, tipo_acao, data_doc, resultado, tags
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")

    # Posição do chunk no documento original (0-indexed)
    chunk_index: Mapped[int] = mapped_column(SmallInteger, server_default="0")

    # SHA256 do conteúdo original — previne duplicatas na ingestão
    doc_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Soft delete — nunca remove fisicamente para preservar histórico
    ativo: Mapped[bool] = mapped_column(
        Boolean, server_default=sa.text("true"), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<DocumentoRag id={self.id} escritorio={self.escritorio_id} "
            f"tipo={self.tipo} chunk={self.chunk_index}>"
        )
