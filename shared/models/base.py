"""
shared/models/base.py
=====================
Fundação de todos os models SQLAlchemy do projeto.

Exporta:
- Base          — DeclarativeBase do SQLAlchemy 2.x
- TimestampMixin — campos created_at e updated_at (com timezone)
- TenantMixin    — campo escritorio_id para isolamento multi-tenant
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """
    Base declarativa unificada.
    Todos os models herdam desta classe.
    O Alembic usa o metadata desta classe para gerar migrations.
    """

    pass


class TimestampMixin:
    """
    Mixin que adiciona created_at e updated_at em qualquer model.

    - created_at: preenchido automaticamente na inserção (server_default)
    - updated_at: atualizado automaticamente em cada UPDATE (onupdate)
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class TenantMixin:
    """
    Mixin de isolamento multi-tenant.

    Adiciona escritorio_id como FK obrigatória para a tabela 'escritorios'.
    TODA query que usa este mixin DEVE filtrar por escritorio_id
    (extraído do JWT do usuário autenticado) para garantir isolamento de dados.
    """

    escritorio_id: Mapped[int] = mapped_column(
        ForeignKey("escritorios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
