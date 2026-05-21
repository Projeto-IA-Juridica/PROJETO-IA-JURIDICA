"""
shared/models/lead_prospeccao.py
==================================
Model do Lead de Prospecção Inteligente (Feature 3).

Suporta dois tipos de lead no mesmo registro:
  - empresa (B2B): identificado por CNPJ real
  - pessoa  (B2C): dados do processo público apenas — sem CPF/telefone/email (LGPD)

Um lead é único por (escritorio_id, cnpj) — mesmo CNPJ pesquisado duas vezes
→ atualiza o registro existente. Para B2C, 'cnpj' armazena o número CNJ do processo.
"""

from sqlalchemy import (
    Boolean,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from shared.models.base import Base, TenantMixin, TimestampMixin


class LeadProspeccao(Base, TimestampMixin, TenantMixin):
    """
    Tabela: leads_prospeccao

    Armazena leads qualificados pela Feature 3 — Prospecção Inteligente.
    Acesso exclusivo a roles advogado e admin (nunca exposto a clientes).

    Para leads do tipo 'pessoa' (B2C):
      - nome          = nome público da pessoa (do processo)
      - cnpj          = número CNJ do processo de origem (não é CNPJ real)
      - socios        = []  (vazio)
      - contatos_linkedin = [] (vazio)
      - CPF, telefone, email NUNCA armazenados — proibido por design (LGPD art. 11)
    """

    __tablename__ = "leads_prospeccao"
    __table_args__ = (
        # Deduplicação: mesmo CNPJ (empresa) ou mesmo CNJ (pessoa) por escritório
        UniqueConstraint("escritorio_id", "cnpj", name="uq_lead_escritorio_cnpj"),
    )

    # --- Chave Primária ---
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # --- Identificação (comum a empresa e pessoa) ---
    # Para empresa: razão social. Para pessoa: nome conforme consta no processo.
    nome: Mapped[str] = mapped_column(String(500), nullable=False)

    # --- Tipo de Lead ---
    # 'empresa' (B2B) | 'pessoa' (B2C)
    tipo_lead: Mapped[str] = mapped_column(String(10), server_default="empresa", nullable=False)

    # --- Campos específicos de empresa (B2B) ---
    # CNPJ formatado (14 dígitos). Para B2C: armazena o número CNJ do processo.
    cnpj: Mapped[str | None] = mapped_column(String(50), nullable=True)
    empresa_setor: Mapped[str | None] = mapped_column(String(200), nullable=True)
    empresa_porte: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # [{nome, qualificacao}] — nunca inclui CPF dos sócios (LGPD)
    socios: Mapped[list] = mapped_column(JSONB, server_default="[]", nullable=False)
    # [{nome, cargo, url_perfil}] — vazio quando LinkedIn indisponível
    contatos_linkedin: Mapped[list] = mapped_column(JSONB, server_default="[]", nullable=False)
    linkedin_disponivel: Mapped[bool] = mapped_column(
        Boolean, server_default="false", nullable=False
    )

    # --- Campos específicos de pessoa (B2C) ---
    # ⚠️ LGPD: nunca armazenar CPF, telefone, email ou endereço de pessoa física
    polo_processo: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tipo_acao_origem: Mapped[str | None] = mapped_column(String(300), nullable=True)
    numero_cnj_exemplo: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # --- Contador de processos públicos ---
    processos_publicos_count: Mapped[int] = mapped_column(
        SmallInteger, server_default="0", nullable=False
    )

    # --- Score de Matching (gerado pelo MatchingService) ---
    score_match: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    score_motivo: Mapped[str | None] = mapped_column(Text, nullable=True)
    abordagem_sugerida: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Gestão do Pipeline ---
    # novo | contatado | qualificado | descartado
    status: Mapped[str] = mapped_column(String(50), server_default="novo", nullable=False)
    notas_advogado: Mapped[str | None] = mapped_column(Text, nullable=True)
    # tipo_acao usado na descoberta
    fonte_descoberta: Mapped[str | None] = mapped_column(String(100), nullable=True)

    @property
    def criado_em(self):
        """Alias de created_at para compatibilidade com o schema Pydantic."""
        return self.created_at

    @criado_em.setter
    def criado_em(self, value):
        self.created_at = value
