"""
shared/models/escritorio.py
============================
Model do Escritório de Advocacia — o TENANT raiz do sistema.

Cada escritório é um cliente isolado. Todos os outros models
referenciam escritorio_id para garantir isolamento multi-tenant.
"""

from datetime import datetime, time
from typing import TYPE_CHECKING

from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    Boolean,
    Integer,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from shared.models.cliente import Cliente
    from shared.models.interacao import Interacao
    from shared.models.processo import Processo
    from shared.models.usuario import Usuario


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

    # --- Persona da IA ---
    persona_nome: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        default="Assistente Jurídico",
        comment="Nome da IA exibido aos clientes",
    )
    persona_tom: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        default="formal",
        comment="Tom da IA: formal | amigavel | neutro",
    )
    horario_inicio: Mapped[time | None] = mapped_column(
        Time(),
        nullable=True,
        comment="Início do horário de atendimento",
    )
    horario_fim: Mapped[time | None] = mapped_column(
        Time(),
        nullable=True,
        comment="Fim do horário de atendimento",
    )

    # --- Onboarding ---
    onboarding_etapa: Mapped[int | None] = mapped_column(
        SmallInteger(),
        nullable=True,
        default=0,
        comment="Etapa atual do onboarding (0-5)",
    )
    onboarding_completo: Mapped[bool | None] = mapped_column(
        Boolean(),
        nullable=True,
        default=False,
        comment="Indica se o onboarding foi concluído",
    )
    onboarding_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
        comment="Timestamp de conclusão do onboarding",
    )

    # --- Templates Personalizados ---
    template_boas_vindas: Mapped[str | None] = mapped_column(
        Text(),
        nullable=True,
        comment="Template personalizado de boas-vindas",
    )
    template_atualizacao: Mapped[str | None] = mapped_column(
        Text(),
        nullable=True,
        comment="Template personalizado de atualização processual",
    )
    template_sem_novidade: Mapped[str | None] = mapped_column(
        Text(),
        nullable=True,
        comment="Template personalizado para quando não há novidades",
    )

    # --- Quota de Tokens Claude ---
    # Limite mensal por plano. None = sem limite (enterprise).
    # Defaults aplicados automaticamente na migration.
    # Planos: basico=500K | profissional=2M | enterprise=None
    quota_tokens_mes: Mapped[int | None] = mapped_column(
        BigInteger(),
        nullable=True,
        comment="Limite mensal de tokens Claude (input+output). None = ilimitado.",
    )
    tokens_usados_mes: Mapped[int] = mapped_column(
        BigInteger(),
        nullable=False,
        server_default="0",
        comment="Total de tokens consumidos no mês corrente.",
    )
    tokens_reset_em: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
        comment="Timestamp do último reset mensal do contador de tokens.",
    )

    # --- Feature 3: Prospecção Inteligente ---
    # Perfil de especialização gerado pelo DNAAdvogadoService.
    # Estrutura: {especialidades, setores_alvo, tipo_lead_predominante,
    #             perfil_cliente_ideal, diferenciais, gerado_em}
    dna_prospeccao: Mapped[dict | None] = mapped_column(JSONB(), nullable=True)

    # --- Feature Hub do Advogado — Modelo de Escalação (Claude Opus) ---
    # escalacao_habilitada: liga/desliga o Hub por escritório (feature flag por tenant).
    # escalacao_canal_advogado_numero: número WhatsApp dedicado ao Hub; se None usa o mesmo
    #   canal do cliente distinguindo por role do remetente.
    # escalacao_quota_tokens_mes: limite mensal de tokens do modelo de escalação (input+output).
    # escalacao_tokens_usados_mes: consumo acumulado no mês corrente.
    # escalacao_confidence_threshold: score mínimo do ConfidenceRouter para não escalar (0.0–1.0).
    escalacao_habilitada: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    escalacao_canal_advogado_numero: Mapped[str | None] = mapped_column(String(20), nullable=True)
    escalacao_quota_tokens_mes: Mapped[int] = mapped_column(Integer, default=500_000, nullable=False)
    escalacao_tokens_usados_mes: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    escalacao_confidence_threshold: Mapped[float] = mapped_column(default=0.70, nullable=False)

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
    __table_args__ = (UniqueConstraint("cnpj", name="uq_escritorios_cnpj"),)

    def __repr__(self) -> str:
        return f"<Escritorio id={self.id} nome={self.nome!r} plano={self.plano!r}>"
