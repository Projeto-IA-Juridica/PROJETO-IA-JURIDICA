"""
shared/models/usuario.py
=========================
Model de Usuário do sistema — advogados, assistentes e administradores
que acessam o painel interno do escritório.

Roles disponíveis:
- admin      → acesso total ao escritório
- advogado   → CRUD processos e clientes, ver interações
- assistente → leitura de processos/clientes, criar interações
- estagiario → apenas leitura
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.models.base import Base, TenantMixin, TimestampMixin

if TYPE_CHECKING:
    from shared.models.escritorio import Escritorio
    from shared.models.processo import Processo


class Usuario(Base, TimestampMixin, TenantMixin):
    """
    Tabela: usuarios

    Armazena as credenciais e o perfil dos usuários internos do escritório.
    A senha NUNCA é armazenada em texto puro — apenas o bcrypt hash.
    """

    __tablename__ = "usuarios"

    # --- Chave Primária ---
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # --- Dados Pessoais ---
    nome: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(200), nullable=False)

    # --- Autenticação ---
    senha_hash: Mapped[str] = mapped_column(
        String(300),
        nullable=False,
        comment="Hash bcrypt — nunca armazenar senha em plain text",
    )

    # --- Perfil / Permissões ---
    role: Mapped[str] = mapped_column(
        String(30),
        default="advogado",
        nullable=False,
        comment="admin | advogado | assistente | estagiario",
    )
    oab: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="Número OAB (apenas para advogados)",
    )

    # --- Status ---
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    ultimo_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- Relacionamentos ---
    escritorio: Mapped["Escritorio"] = relationship(  # noqa: F821
        "Escritorio", back_populates="usuarios"
    )
    processos_responsavel: Mapped[list["Processo"]] = relationship(  # noqa: F821
        "Processo",
        foreign_keys="Processo.advogado_responsavel_id",
        back_populates="advogado_responsavel",
    )

    # --- Constraints ---
    __table_args__ = (UniqueConstraint("email", name="uq_usuarios_email"),)

    def __repr__(self) -> str:
        return f"<Usuario id={self.id} email={self.email!r} role={self.role!r}>"
