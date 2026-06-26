"""
Schemas Pydantic — Prospecção Inteligente
==========================================
Arquivo: shared/schemas/prospeccao.py
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class DescobertaRequest(BaseModel):
    """Body do POST /prospeccao/descobrir."""

    tipo_lead: Literal["empresa", "pessoa", "auto"] = Field(
        description="'auto' usa o tipo_lead_predominante do DNA do escritório"
    )
    # Vigilant API — lista de CPFs a enriquecer (formato NNN.NNN.NNN-NN ou 11 dígitos)
    cpfs: list[str] = Field(
        min_length=1,
        max_length=50,
        description="CPFs a pesquisar na API Vigilant. Ex: ['529.982.247-25', '123.456.789-09']",
    )
    tribunais: list[str] = Field(
        default_factory=list,
        description="Tribunais alvo. Ex: ['TJSP', 'TRT2']. Vazio = padrão por tipo de ação.",
    )
    tipo_acao_filtro: str | None = Field(
        default=None,
        description="Filtrar processos pelo tipo de ação. None = todos os processos do CPF.",
    )
    score_minimo: int = Field(default=40, ge=0, le=100)
    # Mantidos para compatibilidade com testes existentes — não usados na rota Vigilant
    tipo_acao: str | None = None
    tribunal: str | None = None
    limite: int = Field(default=20, ge=1, le=100)


class LeadStatusUpdate(BaseModel):
    """Body do PATCH /prospeccao/{id}/status."""

    status: Literal["novo", "contatado", "qualificado", "descartado"]
    notas_advogado: str | None = None


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class LeadProspeccaoResponse(BaseModel):
    """
    Representa um lead no pipeline — empresa ou pessoa física.

    Campos exclusivos de empresa ficam None para leads pessoa, e vice-versa.
    """

    # Campos comuns
    id: int
    tipo_lead: Literal["empresa", "pessoa"]
    nome: str  # razao_social ou nome da pessoa
    score_match: int | None
    score_motivo: str | None
    abordagem_sugerida: str | None
    status: str
    notas_advogado: str | None
    fonte_descoberta: str | None
    criado_em: datetime

    # Campos exclusivos empresa (None para pessoa)
    cnpj: str | None = None
    empresa_setor: str | None = None
    empresa_porte: str | None = None
    socios: list[dict] = Field(default_factory=list)
    contatos_linkedin: list[dict] = Field(default_factory=list)
    linkedin_disponivel: bool = False

    # Campos exclusivos pessoa (None para empresa)
    # ⚠️ CPF, telefone e email NUNCA aparecem aqui — proibido por design (LGPD)
    polo_processo: str | None = None
    tipo_acao_origem: str | None = None
    numero_cnj_exemplo: str | None = None

    # Sempre presente
    processos_publicos_count: int = 0

    model_config = {"from_attributes": True}


class DNAEscritorioResponse(BaseModel):
    """Retorno do GET /prospeccao/dna."""

    dados_insuficientes: bool = False
    especialidades: list[str] = Field(default_factory=list)
    setores_alvo: list[str] = Field(default_factory=list)
    tipo_lead_predominante: Literal["empresa", "pessoa", "ambos"] | None = None
    perfil_cliente_ideal: str | None = None
    diferenciais: list[str] = Field(default_factory=list)
    gerado_em: datetime | None = None

    model_config = {"from_attributes": True}


# Aviso LGPD injetado quando o pipeline contém leads B2C
_AVISO_LGPD_B2C = (
    "Este pipeline contém leads de pessoas físicas identificadas em processos públicos. "
    "A abordagem deve respeitar o art. 7º da LGPD e o Provimento OAB 205/2021: "
    "não utilize dados pessoais para contato direto não solicitado. "
    "A prospecção deve ocorrer exclusivamente por canais processuais ou publicidade institucional."
)


class PipelineResponse(BaseModel):
    """Retorno do POST /prospeccao/descobrir e GET /prospeccao/pipeline."""

    total: int
    leads: list[LeadProspeccaoResponse]
    dna_disponivel: bool
    linkedin_disponivel: bool
    aviso_lgpd: str | None = Field(
        default=None, description="Preenchido automaticamente quando o pipeline contém leads B2C"
    )

    @classmethod
    def montar(
        cls,
        leads: list[LeadProspeccaoResponse],
        dna_disponivel: bool,
        linkedin_disponivel: bool,
    ) -> PipelineResponse:
        """
        Factory que injeta aviso_lgpd automaticamente se houver leads B2C.
        Use este método em vez do construtor direto.
        """
        tem_b2c = any(lead.tipo_lead == "pessoa" for lead in leads)
        return cls(
            total=len(leads),
            leads=leads,
            dna_disponivel=dna_disponivel,
            linkedin_disponivel=linkedin_disponivel,
            aviso_lgpd=_AVISO_LGPD_B2C if tem_b2c else None,
        )
