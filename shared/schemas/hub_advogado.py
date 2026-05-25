"""
shared/schemas/hub_advogado.py
================================
Schemas Pydantic do Hub do Advogado.

Exporta os schemas de request/response para os endpoints REST do Hub,
bem como o schema de listagem/detalhe das sessões, conversas e métricas.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class ConsultaHubRequest(BaseModel):
    pergunta: Annotated[str, Field(min_length=1, max_length=4096)]
    cliente_id: int | None = None
    processo_id: int | None = None
    # UUID gerado pelo frontend para agrupar mensagens em uma thread de conversa
    conversa_id: str | None = None


# ---------------------------------------------------------------------------
# Response schemas — endpoints de consulta
# ---------------------------------------------------------------------------


class ConsultaHubResponse(BaseModel):
    resposta: str
    modelo_ia: str
    tokens_input: int
    tokens_output: int
    custo_estimado: Decimal
    # Retorna o conversa_id confirmado (gerado ou recebido)
    conversa_id: str | None = None


# ---------------------------------------------------------------------------
# Response schemas — histórico de sessões (endpoint legado /hub/historico)
# ---------------------------------------------------------------------------


class SessaoAdvogadoListItem(BaseModel):
    id: int
    intencao: str
    modelo_ia: str
    mensagem_preview: Annotated[str, Field(max_length=100)]
    created_at: datetime

    model_config = {"from_attributes": True}


class SessaoAdvogadoResponse(BaseModel):
    """Detalhe completo de uma sessão do Hub."""

    id: int
    intencao: str
    modelo_ia: str
    mensagem_advogado: str
    resposta_hub: str
    tokens_input: int
    tokens_output: int
    custo_estimado: Decimal
    cliente_referenciado_id: int | None
    processo_referenciado_id: int | None
    metadata_json: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Response schemas — conversas (threads agrupadas por conversa_id)
# ---------------------------------------------------------------------------


class ConversaListItem(BaseModel):
    """Item de listagem de conversas — uma thread de múltiplas trocas Q&A."""

    conversa_id: str
    titulo: str          # primeira mensagem truncada (usado como nome da conversa)
    ultima_mensagem_em: datetime
    total_mensagens: int


class ConversaMensagem(BaseModel):
    """Uma troca Q&A dentro de uma conversa."""

    id: int
    mensagem_advogado: str
    resposta_hub: str
    modelo_ia: str
    tokens_input: int
    tokens_output: int
    custo_estimado: Decimal
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Response schemas — métricas (admin)
# ---------------------------------------------------------------------------


class IntencaoCount(BaseModel):
    intencao: str
    total: int


class AdvogadoAtivo(BaseModel):
    usuario_id: int
    total_sessoes: int


class MetricasHubResponse(BaseModel):
    mes_atual: Annotated[str, Field(pattern=r"^\d{4}-\d{2}$")]
    total_sessoes: int
    tokens_input_total: int
    tokens_output_total: int
    custo_total_usd: Decimal
    intencoes_top5: list[IntencaoCount]
    advogados_mais_ativos: list[AdvogadoAtivo]
