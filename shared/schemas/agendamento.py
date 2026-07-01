from __future__ import annotations

from datetime import datetime, time

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Disponibilidade
# ---------------------------------------------------------------------------


class DisponibilidadeItem(BaseModel):
    dia_semana: int = Field(ge=0, le=5, description="0=segunda … 5=sábado")
    hora_inicio: time
    hora_fim: time
    ativo: bool = True


class DisponibilidadeResponse(BaseModel):
    dia_semana: int
    hora_inicio: time
    hora_fim: time
    ativo: bool

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Slots disponíveis
# ---------------------------------------------------------------------------


class SlotResponse(BaseModel):
    inicio: datetime
    fim: datetime
    label: str = Field(description="Ex: 'Segunda-feira, 07/07 às 10h'")


# ---------------------------------------------------------------------------
# Agendamento
# ---------------------------------------------------------------------------


class AgendamentoResponse(BaseModel):
    id: int
    status: str
    cliente_id: int
    cliente_nome: str | None = None
    processo_id: int | None = None
    interacao_id: int | None = None
    data_hora_inicio: datetime | None = None
    data_hora_fim: datetime | None = None
    opcoes_propostas: list[dict] | None = None
    opcao_selecionada_pos: int | None = None
    canal_aprovacao: str | None = None
    motivo_cliente: str | None = None
    nota_advogado: str | None = None
    expira_em: datetime | None = None
    proposta_enviada_em: datetime | None = None
    resposta_cliente_em: datetime | None = None
    resposta_advogado_em: datetime | None = None
    motivo_cancelamento: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SugerirRequest(BaseModel):
    nota_advogado: str | None = Field(
        default=None,
        max_length=500,
        description="Nota interna do advogado (não exibida ao cliente)",
    )


class CancelarRequest(BaseModel):
    motivo: str | None = Field(default=None, max_length=500)
