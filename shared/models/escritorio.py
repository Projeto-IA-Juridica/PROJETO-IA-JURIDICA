"""
shared/models/escritorio.py
============================
Model do Escritório de Advocacia — o TENANT raiz do sistema.

Cada escritório é um cliente isolado. Todos os outros models
referenciam escritorio_id para garantir isolamento multi-tenant.
"""

from sqlalchemy import Boolean, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.models.base import Base, TimestampMixin


class Escritorio(Base, TimestampMixin):
    """
    Tabela: escritorios

    Representa um escritório de advocacia (tenant).
    O plano determina os limites de uso (max_processos, max_clientes).
    """

    __tablename__ = "escritorios"

    # --- Chave Primária ---
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # --- Dados do Escritório ---
    nome: Mapped[str] = mapped_column(String(200), nullable=False)
    cnpj: Mapped[str] = mapped_column(String(18), nullable=False, unique=True)
    email: Mapped[str] = mapped_column(String(200), nullable=False)
    telefone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    endereco: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # --- Responsável OAB ---
    oab_responsavel: Mapped[str] = mapped_column(String(20), nullable=False)
    nome_responsavel: Mapped[str] = mapped_column(String(200), nullable=False)

    # --- Plano / Limites ---
    plano: Mapped[str] = mapped_column(
        String(50),
        default="basico",
        nullable=False,
        comment="basico | profissional | enterprise",
    )
    max_processos: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    max_clientes: Mapped[int] = mapped_column(Integer, default=200, nullable=False)

    # --- Status ---
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # --- Integração WhatsApp ---
    webhook_whatsapp_instance: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Nome da instância na Evolution API",
    )

    # --- Relacionamentos ---
    usuarios: Mapped[list["Usuario"]] = relationship(  # noqa: F821
        "Usuario", back_populates="escritorio", cascade="all, delete-orphan"
    )
    clientes: Mapped[list["Cliente"]] = relationship(  # noqa: F821
        "Cliente", back_populates="escritorio", cascade="all, delete-orphan"
    )
    processos: Mapped[list["Processo"]] = relationship(  # noqa: F821
        "Processo", back_populates="escritorio", cascade="all, delete-orphan"
    )
    interacoes: Mapped[list["Interacao"]] = relationship(  # noqa: F821
        "Interacao", back_populates="escritorio", cascade="all, delete-orphan"
    )

    # --- Constraints ---
    __table_args__ = (
        UniqueConstraint("cnpj", name="uq_escritorios_cnpj"),
    )

    def __repr__(self) -> str:
        return f"<Escritorio id={self.id} nome={self.nome!r} plano={self.plano!r}>"
