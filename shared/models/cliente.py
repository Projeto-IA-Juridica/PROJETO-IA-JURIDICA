"""
shared/models/cliente.py
=========================
Model do Cliente — pessoa física que o escritório representa.

Pontos de atenção:
- CPF é armazenado CRIPTOGRAFADO em repouso (AES-256 via Fernet).
  A criptografia/descriptografia é feita na camada de serviço,
  antes de salvar e após ler do banco.
- telefone_whatsapp é o identificador primário para mensagens.
- aceite_lgpd é obrigatório para envio de mensagens proativas.
- data_nascimento permite envio de mensagens de aniversário.
- profissao permite mensagens em datas comemorativas (ex: Dia do Bancário).
"""

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.models.base import Base, TenantMixin, TimestampMixin

if TYPE_CHECKING:
    from shared.models.escritorio import Escritorio
    from shared.models.interacao import Interacao
    from shared.models.processo import Processo


class Cliente(Base, TimestampMixin, TenantMixin):
    """
    Tabela: clientes

    Representa o cliente final — quem manda mensagem pelo WhatsApp.
    """

    __tablename__ = "clientes"

    # --- Chave Primária ---
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # --- Dados Pessoais ---
    nome: Mapped[str] = mapped_column(String(200), nullable=False)
    cpf: Mapped[str] = mapped_column(
        String(100),  # maior que 14 pois o valor é criptografado
        nullable=False,
        comment="CPF armazenado criptografado (AES-256 Fernet)",
    )

    # --- Contato ---
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    telefone_whatsapp: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Formato: 5511999999999 (55 + DDD + número)",
    )

    # --- Personalização / Relacionamento ---
    data_nascimento: Mapped[date | None] = mapped_column(Date, nullable=True)
    profissao: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Usado para mensagens em datas comemorativas (ex: Dia do Bancário)",
    )
    empresa_atual: Mapped[str | None] = mapped_column(String(200), nullable=True)
    cargo: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # --- LGPD ---
    aceite_lgpd: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    data_aceite_lgpd: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # --- Preferências ---
    preferencia_horario_notificacao: Mapped[str] = mapped_column(
        String(20),
        default="comercial",
        nullable=False,
        comment="comercial | qualquer | silencioso",
    )

    # --- Status ---
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # --- CRM Inteligente ---
    crm_nivel: Mapped[str | None] = mapped_column(
        Enum(
            "excelente",
            "satisfeito",
            "neutro",
            "em_risco",
            "critico",
            name="crm_nivel_enum",
        ),
        nullable=True,
        comment="excelente | satisfeito | neutro | em_risco | critico",
    )
    crm_score: Mapped[int | None] = mapped_column(
        SmallInteger,
        nullable=True,
        comment="Score composto 0–100 calculado deterministicamente",
    )
    crm_resumo: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Texto gerado pelo Claude explicando o porquê da classificação (≤ 3 frases)",
    )
    crm_acao_sugerida: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Ação concreta sugerida pelo Claude para o advogado",
    )
    crm_analisado_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp de quando a análise CRM foi calculada",
    )

    # --- Relacionamentos ---
    escritorio: Mapped["Escritorio"] = relationship(  # noqa: F821
        "Escritorio", back_populates="clientes"
    )
    processos: Mapped[list["Processo"]] = relationship(  # noqa: F821
        "Processo", back_populates="cliente", cascade="all, delete-orphan"
    )
    interacoes: Mapped[list["Interacao"]] = relationship(  # noqa: F821
        "Interacao", back_populates="cliente", cascade="all, delete-orphan"
    )

    # --- Constraints e Índices ---
    __table_args__ = (
        UniqueConstraint("escritorio_id", "cpf", name="uq_clientes_escritorio_cpf"),
        Index("ix_clientes_telefone_whatsapp", "telefone_whatsapp"),
    )

    @property
    def idade(self) -> int | None:
        """Calcula a idade do cliente a partir de data_nascimento."""
        if not self.data_nascimento:
            return None
        hoje = date.today()
        return int(
            hoje.year
            - self.data_nascimento.year
            - ((hoje.month, hoje.day) < (self.data_nascimento.month, self.data_nascimento.day))
        )

    @property
    def e_bancario(self) -> bool:
        """Detecta se a profissão tem relação com setor bancário."""
        if not self.profissao:
            return False
        termos_bancarios = {"banco", "bancário", "bancaria", "caixa", "financeiro"}
        profissao_lower = self.profissao.lower()
        return any(termo in profissao_lower for termo in termos_bancarios)

    def __repr__(self) -> str:
        return f"<Cliente id={self.id} nome={self.nome!r} escritorio_id={self.escritorio_id}>"
