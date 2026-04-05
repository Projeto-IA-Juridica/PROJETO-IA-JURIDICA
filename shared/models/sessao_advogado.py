"""
shared/models/sessao_advogado.py
=================================
Histórico de conversas do advogado com o Hub do Advogado.

Separado do model Interacao (que é para o fluxo cliente ↔ IA).
Cada mensagem que o advogado envia ao Hub gera um registro aqui,
com a resposta, intenção classificada, modelo usado e custo.
"""

from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from shared.models.base import Base, TenantMixin, TimestampMixin


class SessaoAdvogado(Base, TimestampMixin, TenantMixin):
    """
    Sessão de conversa do advogado com o Hub.

    Campos de auditoria / analytics:
    - modelo_ia: 'claude_opus' | 'claude' | 'claude_opus_fallback'
    - intencao: intenção classificada (duvida_juridica, resumo_processo, etc.)
    - custo_estimado: custo USD da chamada ao modelo de escalação
    - cliente_referenciado_id / processo_referenciado_id: entidades mencionadas na sessão
    """

    __tablename__ = "sessoes_advogado"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Advogado que enviou a mensagem
    usuario_id: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Conteúdo da conversa
    mensagem_advogado: Mapped[str] = mapped_column(Text, nullable=False)
    resposta_hub: Mapped[str] = mapped_column(Text, nullable=False)

    # Classificação e modelo
    intencao: Mapped[str] = mapped_column(String(50), nullable=False, default="duvida_juridica")
    modelo_ia: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        server_default="claude_opus",
        # Valores: 'claude_opus' | 'claude' | 'claude_opus_fallback'
    )

    # Métricas de custo
    tokens_input: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_output: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    custo_estimado: Mapped[Decimal] = mapped_column(
        Numeric(10, 6), nullable=False, server_default="0"
    )

    # Entidades referenciadas (opcionais — para rastreamento)
    cliente_referenciado_id: Mapped[int | None] = mapped_column(
        ForeignKey("clientes.id", ondelete="SET NULL"),
        nullable=True,
    )
    processo_referenciado_id: Mapped[int | None] = mapped_column(
        ForeignKey("processos.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Dados extras (entidades extraídas, score de confiança, etc.)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")

    __table_args__ = (
        # Busca paginada do histórico: filtra por escritório + advogado, ordena por data
        Index("ix_sessoes_advogado_usuario", "usuario_id", "escritorio_id", "created_at"),
    )
