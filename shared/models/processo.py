"""
shared/models/processo.py
==========================
Model do Processo Judicial vinculado a um cliente.

- numero_cnj segue o padrão CNJ: NNNNNNN-DD.AAAA.J.TR.OOOO
- O sistema monitora andamentos automaticamente via Jusbrasil (ou DataJud como fallback)
- monitoramento_ativo + frequencia_monitoramento controlam o worker Celery
"""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.models.base import Base, TenantMixin, TimestampMixin

if TYPE_CHECKING:
    from shared.models.cliente import Cliente
    from shared.models.escritorio import Escritorio
    from shared.models.interacao import Interacao
    from shared.models.usuario import Usuario


class Processo(Base, TimestampMixin, TenantMixin):
    """
    Tabela: processos

    Representa um processo judicial monitorado para o cliente.
    Pode ter múltiplos andamentos (rastreados externamente via Jusbrasil).
    """

    __tablename__ = "processos"

    # --- Chave Primária ---
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # --- Relacionamentos (FKs) ---
    cliente_id: Mapped[int] = mapped_column(
        ForeignKey("clientes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    advogado_responsavel_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # --- Identificação do Processo ---
    numero_cnj: Mapped[str] = mapped_column(
        String(25),
        nullable=False,
        comment="Formato CNJ: NNNNNNN-DD.AAAA.J.TR.OOOO",
    )
    tribunal: Mapped[str | None] = mapped_column(
        String(10), nullable=True, comment="Ex: TJSP, TRF3, STJ"
    )
    vara: Mapped[str | None] = mapped_column(String(200), nullable=True)
    comarca: Mapped[str | None] = mapped_column(String(200), nullable=True)
    tipo_acao: Mapped[str | None] = mapped_column(
        String(200), nullable=True, comment="Ex: Ação de Cobrança, Ação Trabalhista"
    )

    # --- Posição do Cliente ---
    polo_cliente: Mapped[str] = mapped_column(
        String(20),
        default="autor",
        nullable=False,
        comment="autor | reu | terceiro",
    )

    # --- Status do Processo ---
    status: Mapped[str] = mapped_column(
        String(50),
        default="ativo",
        nullable=False,
        comment="ativo | arquivado | suspenso | encerrado",
        index=True,
    )

    # --- Último Andamento (cache local) ---
    ultimo_andamento: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Texto do último andamento registrado (cache para evitar chamadas à API)",
    )
    data_ultimo_andamento: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # --- Dados Complementares ---
    data_distribuicao: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    valor_causa: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)

    # --- Integração Jusbrasil ---
    jusbrasil_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="ID interno do processo no Jusbrasil",
    )

    # --- Monitoramento ---
    monitoramento_ativo: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="Se True, o worker Celery monitora este processo automaticamente",
    )
    frequencia_monitoramento: Mapped[str] = mapped_column(
        String(20),
        default="diario",
        nullable=False,
        comment="diario | semanal",
    )

    # --- Relacionamentos ---
    escritorio: Mapped["Escritorio"] = relationship(  # noqa: F821
        "Escritorio", back_populates="processos"
    )
    cliente: Mapped["Cliente"] = relationship(  # noqa: F821
        "Cliente", back_populates="processos"
    )
    advogado_responsavel: Mapped["Usuario | None"] = relationship(  # noqa: F821
        "Usuario",
        foreign_keys=[advogado_responsavel_id],
        back_populates="processos_responsavel",
    )
    interacoes: Mapped[list["Interacao"]] = relationship(  # noqa: F821
        "Interacao", back_populates="processo"
    )

    # --- Constraints e Índices ---
    __table_args__ = (
        UniqueConstraint(
            "escritorio_id", "numero_cnj", name="uq_processos_escritorio_cnj"
        ),
    )

    def __repr__(self) -> str:
        return f"<Processo id={self.id} cnj={self.numero_cnj!r} status={self.status!r}>"
