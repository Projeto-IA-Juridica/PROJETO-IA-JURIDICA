from __future__ import annotations

from datetime import time
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, Integer, SmallInteger, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.models.base import Base, TenantMixin, TimestampMixin

if TYPE_CHECKING:
    from shared.models.escritorio import Escritorio


class DisponibilidadeAdvogado(Base, TenantMixin, TimestampMixin):
    """
    Tabela: disponibilidade_advogado

    Uma linha por dia ativo (seg–sáb). Ausência de linha = dia não atende.
    ConfigPage escreve; AgendamentoDetector lê filtrando por
    (escritorio_id, dia_semana, ativo=True).

    Convenção de dia_semana: 0=segunda … 5=sábado.
    """

    __tablename__ = "disponibilidade_advogado"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    dia_semana: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        comment="0=segunda, 1=terça, 2=quarta, 3=quinta, 4=sexta, 5=sábado",
    )
    hora_inicio: Mapped[time] = mapped_column(Time, nullable=False)
    hora_fim: Mapped[time] = mapped_column(Time, nullable=False)
    ativo: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="true",
    )

    escritorio: Mapped[Escritorio] = relationship("Escritorio", back_populates="disponibilidades")

    # UniqueConstraint cria índice B-tree implícito no PostgreSQL — índice
    # explícito nos mesmos campos seria redundante.
    __table_args__ = (
        UniqueConstraint(
            "escritorio_id",
            "dia_semana",
            name="uq_disponibilidade_escritorio_dia",
        ),
        CheckConstraint(
            "dia_semana BETWEEN 0 AND 5",
            name="ck_disponibilidade_dia_semana",
        ),
        CheckConstraint(
            "hora_fim > hora_inicio",
            name="ck_disponibilidade_horario",
        ),
    )

    def __repr__(self) -> str:
        dias = ["seg", "ter", "qua", "qui", "sex", "sáb"]
        dia = dias[self.dia_semana] if 0 <= self.dia_semana <= 5 else str(self.dia_semana)
        return (
            f"<DisponibilidadeAdvogado escritorio_id={self.escritorio_id} "
            f"dia={dia} {self.hora_inicio}-{self.hora_fim} ativo={self.ativo}>"
        )
