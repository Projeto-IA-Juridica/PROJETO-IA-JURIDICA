"""
shared/models/lead_prospeccao.py
==================================
Model do Lead de Prospecção Inteligente (Feature 3).

Representa uma empresa-alvo identificada para o escritório prospectar,
com dados agregados de Receita Federal, DataJud e LinkedIn, além do
score de afinidade calculado pelo MatchingService.

Um lead é único por (escritorio_id, cnpj) — se o mesmo CNPJ for pesquisado
novamente, os dados são atualizados no registro existente.
"""

from sqlalchemy import (
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
    """

    __tablename__ = "leads_prospeccao"
    __table_args__ = (
        UniqueConstraint("escritorio_id", "cnpj", name="uq_lead_escritorio_cnpj"),
    )

    # --- Chave Primária ---
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # --- Identificação da Empresa ---
    cnpj: Mapped[str] = mapped_column(String(18), nullable=False)
    empresa_nome: Mapped[str] = mapped_column(String(500), nullable=False)
    empresa_setor: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # MEI | ME | EPP | MEDIO | GRANDE
    empresa_porte: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # --- Dados Agregados das Fontes Externas ---
    # [{nome, qualificacao, data_entrada}]
    socios: Mapped[list] = mapped_column(JSONB, server_default="[]", nullable=False)
    # [{numero_cnj, tipo_acao, fase, polo, tribunal}]
    processos_publicos: Mapped[list] = mapped_column(
        JSONB, server_default="[]", nullable=False
    )
    # [{nome, cargo, url_perfil}] — vazio quando LinkedIn indisponível
    contatos_linkedin: Mapped[list] = mapped_column(
        JSONB, server_default="[]", nullable=False
    )

    # --- Score de Matching (gerado pelo MatchingService) ---
    score_match: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    score_motivo: Mapped[str | None] = mapped_column(Text, nullable=True)
    abordagem_sugerida: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Tipo de Lead ---
    # empresa (B2B) | pessoa (B2C — pessoa física encontrada via DataJud)
    # Para leads do tipo 'pessoa': empresa_nome = nome da pessoa,
    # cnpj = número CNJ do processo de origem, socios/contatos_linkedin = [].
    # CPF, telefone e email de pessoa física NUNCA são armazenados (LGPD art. 11).
    tipo_lead: Mapped[str] = mapped_column(
        String(10), server_default="empresa", nullable=False
    )

    # --- Gestão do Pipeline ---
    # novo | contatado | qualificado | descartado
    status: Mapped[str] = mapped_column(
        String(50), server_default="novo", nullable=False
    )
    notas_advogado: Mapped[str | None] = mapped_column(Text, nullable=True)
    # manual | sugerido_ia | importado
    fonte_descoberta: Mapped[str | None] = mapped_column(String(100), nullable=True)
