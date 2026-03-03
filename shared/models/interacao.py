"""
shared/models/interacao.py
===========================
Model de Interação — log completo de todas as conversas entre
cliente e IA (ou canal de sistema) do escritório.

Cada mensagem WhatsApp (entrada ou saída), cada notificação
proativa e cada pesquisa NPS gera um registro aqui.

Usado para:
- Auditoria (LGPD)
- Analytics (custo de tokens, NPS, tempo de resposta)
- Histórico de conversas para contexto da IA
- Rastreamento de mensagens de relacionamento (aniversários, datas comemorativas)
"""

from decimal import Decimal

from sqlalchemy import (
    JSON,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.models.base import Base, TenantMixin, TimestampMixin


class Interacao(Base, TimestampMixin, TenantMixin):
    """
    Tabela: interacoes

    Cada linha representa uma troca de mensagem individual.
    Tanto mensagens do cliente (entrada) quanto respostas da IA (saída)
    são registradas para rastreabilidade completa.
    """

    __tablename__ = "interacoes"

    # --- Chave Primária ---
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # --- Relacionamentos (FKs) ---
    cliente_id: Mapped[int] = mapped_column(
        ForeignKey("clientes.id", ondelete="CASCADE"),
        nullable=False,
    )
    processo_id: Mapped[int | None] = mapped_column(
        ForeignKey("processos.id", ondelete="SET NULL"),
        nullable=True,
        comment="Nulo se for interação geral (não relacionada a um processo)",
    )

    # --- Classificação ---
    tipo: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="whatsapp_texto | whatsapp_audio | sistema | notificacao",
    )
    direcao: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="entrada (cliente → IA) | saida (IA → cliente)",
    )

    # --- Conteúdo ---
    mensagem_cliente: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="O que o cliente enviou",
    )
    mensagem_ia: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="O que a IA respondeu",
    )
    audio_transcricao: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Transcrição do áudio, se a mensagem foi um áudio (Whisper API)",
    )

    # --- Métricas de IA ---
    tokens_input: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens_output: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    custo_estimado: Mapped[Decimal] = mapped_column(
        Numeric(10, 6),
        default=0,
        nullable=False,
        comment="Custo estimado em USD baseado nos tokens consumidos",
    )
    tempo_resposta_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Latência total em milissegundos (desde recebimento até envio)",
    )

    # --- Feedback do Usuário ---
    satisfacao: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Nota NPS de 1 a 5 (preenchida quando cliente responde pesquisa)",
    )

    # --- Dados Extras (JSON flexível) ---
    metadata_json: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment=(
            "Dados extras variáveis:\n"
            "- whatsapp_message_id: ID da mensagem na Evolution API\n"
            "- tipo_relacionamento: aniversario | data_comemorativa | check_in\n"
            "- erro: true se houve erro no processamento\n"
            "- usando_fallback: true se Claude estava offline\n"
            "- fact_check_corrigido: true se houve correção pela IA"
        ),
    )

    # --- Relacionamentos ---
    escritorio: Mapped["Escritorio"] = relationship(  # noqa: F821
        "Escritorio", back_populates="interacoes"
    )
    cliente: Mapped["Cliente"] = relationship(  # noqa: F821
        "Cliente", back_populates="interacoes"
    )
    processo: Mapped["Processo | None"] = relationship(  # noqa: F821
        "Processo", back_populates="interacoes"
    )

    # --- Índices ---
    __table_args__ = (
        Index("ix_interacoes_escritorio_cliente", "escritorio_id", "cliente_id"),
        Index("ix_interacoes_created_at", "created_at"),  # para queries de analytics
    )

    def __repr__(self) -> str:
        return (
            f"<Interacao id={self.id} tipo={self.tipo!r} "
            f"direcao={self.direcao!r} cliente_id={self.cliente_id}>"
        )
