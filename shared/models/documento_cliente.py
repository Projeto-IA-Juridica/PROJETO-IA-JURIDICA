"""
shared/models/documento_cliente.py
====================================
Documentos vinculados a um cliente específico — contratos, procurações,
comprovantes e qualquer arquivo enviado pelo advogado ou pelo cliente.

Diferente de documentos_rag (base de conhecimento do escritório),
estes documentos pertencem a um cliente e não são vetorizados.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import Boolean, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from shared.models.base import Base, TenantMixin, TimestampMixin

TIPOS_DOCUMENTO_CLIENTE = frozenset(
    {"contrato", "procuracao", "identidade", "peticao", "comprovante", "outro"}
)

MAX_TAMANHO_BYTES = 10 * 1024 * 1024  # 10 MB


class DocumentoCliente(Base, TenantMixin, TimestampMixin):
    """
    Tabela: documentos_cliente

    Armazena arquivos (PDF, imagens, etc.) vinculados a um cliente.
    O conteúdo binário é salvo diretamente no banco (BYTEA).
    """

    __tablename__ = "documentos_cliente"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    cliente_id: Mapped[int] = mapped_column(
        Integer,
        sa.ForeignKey("clientes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    processo_id: Mapped[int | None] = mapped_column(
        Integer,
        sa.ForeignKey("processos.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    nome: Mapped[str] = mapped_column(String(500), nullable=False)
    arquivo_nome: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    tamanho_bytes: Mapped[int] = mapped_column(Integer, nullable=False)

    tipo: Mapped[str] = mapped_column(String(50), nullable=False, server_default="outro")

    conteudo: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    ativo: Mapped[bool] = mapped_column(Boolean, server_default=sa.text("true"), nullable=False)

    def __repr__(self) -> str:
        return (
            f"<DocumentoCliente id={self.id} cliente={self.cliente_id} "
            f"tipo={self.tipo} nome={self.nome!r}>"
        )
