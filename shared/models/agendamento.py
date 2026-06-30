from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.models.base import Base, TenantMixin, TimestampMixin

if TYPE_CHECKING:
    from shared.models.cliente import Cliente
    from shared.models.escritorio import Escritorio
    from shared.models.interacao import Interacao
    from shared.models.processo import Processo


class Agendamento(Base, TenantMixin, TimestampMixin):
    """
    Tabela: agendamentos

    Máquina de estados:
      aguardando_cliente   → IA enviou 3 opções; esperando cliente escolher
      aguardando_advogado  → cliente escolheu; aguardando confirmação do advogado
      confirmado           → advogado confirmou; reunião na agenda
      cancelado            → qualquer parte cancelou
      expirado             → worker expirar_propostas rodou após expira_em sem resposta
    """

    __tablename__ = "agendamentos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    cliente_id: Mapped[int] = mapped_column(
        ForeignKey("clientes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    interacao_id: Mapped[int | None] = mapped_column(
        ForeignKey("interacoes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Conversa WhatsApp que gerou o agendamento",
    )
    processo_id: Mapped[int | None] = mapped_column(
        ForeignKey("processos.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Processo relacionado; None quando reunião não pertence a um processo específico",
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        server_default="aguardando_cliente",
        index=True,
        comment="aguardando_cliente | aguardando_advogado | confirmado | cancelado | expirado",
    )

    data_hora_inicio: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Slot confirmado (UTC); preenchido quando advogado confirma",
    )
    data_hora_fim: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    opcoes_propostas: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment='[{inicio: ISO, fim: ISO, label: "Segunda, 07/07 às 10h"}, ...]',
    )
    opcao_selecionada_pos: Mapped[int | None] = mapped_column(
        SmallInteger,
        nullable=True,
        comment="Posição 0-2 na lista opcoes_propostas escolhida pelo cliente",
    )

    # Preenchido quando status muda para 'confirmado'.
    # processar_resposta_advogado lê este campo para não responder no WhatsApp
    # quando o advogado já confirmou pelo Hub.
    canal_aprovacao: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="'hub' | 'whatsapp'",
    )

    # Trecho da conversa que originou o pedido de reunião.
    # Exibido no card de aprovação do Hub e na notificação WhatsApp ao advogado.
    motivo_cliente: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Flags de idempotência — impedem que retries e workers horários reenviem a
    # mesma mensagem. O mais crítico: whatsapp_confirmacao_pre_reuniao_enviado evita
    # que o worker horário (janela [now+3h, now+3h59]) dispare até 59 mensagens ao
    # cliente antes da reunião.
    whatsapp_proposta_cliente_enviado: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
        comment="True após enviar_proposta_cliente() concluir com sucesso",
    )
    whatsapp_notificacao_advogado_enviado: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
        comment="True após enviar_notificacao_advogado() concluir com sucesso",
    )
    whatsapp_confirmacao_cliente_enviado: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
        comment="True após enviar_confirmacao_cliente() concluir com sucesso",
    )
    whatsapp_confirmacao_pre_reuniao_enviado: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
        comment="True após worker enviar o lembrete de 3h",
    )

    proposta_enviada_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expira_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="48h após proposta_enviada_em; worker expirar_propostas usa este campo",
    )
    resposta_cliente_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resposta_advogado_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    motivo_cancelamento: Mapped[str | None] = mapped_column(Text, nullable=True)

    escritorio: Mapped[Escritorio] = relationship("Escritorio", back_populates="agendamentos")
    cliente: Mapped[Cliente] = relationship("Cliente", back_populates="agendamentos")
    interacao: Mapped[Interacao | None] = relationship("Interacao", back_populates="agendamentos")
    processo: Mapped[Processo | None] = relationship("Processo", back_populates="agendamentos")

    __table_args__ = (
        Index("ix_agendamentos_escritorio_status", "escritorio_id", "status"),
        Index("ix_agendamentos_expira_em", "expira_em"),
    )

    def __repr__(self) -> str:
        return f"<Agendamento id={self.id} status={self.status!r} " f"cliente_id={self.cliente_id}>"
