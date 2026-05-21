"""
shared/models/mensagem_agendada.py
===================================
Mensagens que precisam ser enviadas fora da janela comercial
ou após rate-limit diário, armazenadas para envio posterior.

O worker dispatcher_agendadas roda a cada 5 minutos via Celery Beat
e processa tudo com enviar_em <= agora e status='pendente'.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.models.base import Base, TenantMixin, TimestampMixin

if TYPE_CHECKING:
    from shared.models.cliente import Cliente
    from shared.models.processo import Processo


class MensagemAgendada(Base, TimestampMixin, TenantMixin):
    """
    Tabela: mensagens_agendadas

    Cada linha é uma mensagem que o WhatsAppService quis enviar mas
    foi bloqueada (fora do horário comercial ou rate-limit diário).
    O dispatcher lê as linhas pendentes e tenta o envio real.

    Status:
      pendente  — aguardando o instante enviar_em
      enviada   — enviada com sucesso
      falha     — esgotou as tentativas (max 3) sem sucesso
    """

    __tablename__ = "mensagens_agendadas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    cliente_id: Mapped[int] = mapped_column(
        ForeignKey("clientes.id", ondelete="CASCADE"),
        nullable=False,
    )
    processo_id: Mapped[int | None] = mapped_column(
        ForeignKey("processos.id", ondelete="SET NULL"),
        nullable=True,
    )

    texto: Mapped[str] = mapped_column(Text, nullable=False)
    motivo: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="fora_horario_comercial | rate_limit_diario",
    )

    enviar_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Instante a partir do qual o dispatcher pode enviar",
    )

    status: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        server_default="pendente",
        comment="pendente | enviada | falha",
    )
    tentativas: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
    )
    enviada_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relacionamentos
    cliente: Mapped[Cliente] = relationship("Cliente")
    processo: Mapped[Processo | None] = relationship("Processo")

    __table_args__ = (
        # Índice principal do dispatcher: pendentes ordenadas por enviar_em
        Index(
            "ix_mensagens_agendadas_dispatcher",
            "escritorio_id",
            "status",
            "enviar_em",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<MensagemAgendada id={self.id} status={self.status!r} "
            f"cliente_id={self.cliente_id} enviar_em={self.enviar_em}>"
        )
