"""
shared/schemas/processo.py
===========================
Schemas Pydantic para o recurso Processo Judicial.

- AndamentoSchema        → entrada de andamento processual
- ProcessoCreate         → criação de processo (POST)
- ProcessoUpdate         → atualização parcial (PUT/PATCH)
- ProcessoResponse       → retorno da API (com último andamento)
- ProcessoComAndamentos  → retorno detalhado (com histórico de andamentos)

Formato CNJ obrigatório: NNNNNNN-DD.AAAA.J.TT.OOOO
Exemplo: 0001234-56.2024.8.26.0100
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from shared.schemas.response import PaginatedResponse
from shared.utils.validators import validar_numero_processo

# ---------------------------------------------------------------------------
# Constantes de schema (específicas deste recurso)
# ---------------------------------------------------------------------------

_POLOS_VALIDOS = {"autor", "reu", "terceiro"}
_FREQUENCIAS_VALIDAS = {"diario", "semanal"}
_NIVEIS_SCORE_VALIDOS = {"baixo", "moderado", "alto", "critico"}

# ---------------------------------------------------------------------------
# Schemas auxiliares
# ---------------------------------------------------------------------------

TipoAndamento = Literal[
    "despacho", "sentença", "decisão", "petição", "certidão", "audiência", "outro"
]


class AndamentoSchema(BaseModel):
    """
    Representa uma movimentação/andamento processual.
    Populado a partir dos dados do Jusbrasil ou DataJud,
    após limpeza pelo DataCleaner.
    """

    data: datetime = Field(description="Data e hora do andamento")
    descricao: str = Field(
        min_length=1, description="Texto do andamento (já limpo pelo DataCleaner)"
    )
    tipo: TipoAndamento = Field(
        description=(
            "Classificação do andamento: despacho | sentença | decisão | petição"
            " | certidão | audiência | outro"
        )
    )


# ---------------------------------------------------------------------------
# Schemas principais
# ---------------------------------------------------------------------------


class ProcessoCreate(BaseModel):
    """Campos para cadastro de um novo processo."""

    numero_cnj: str = Field(
        description="Número CNJ do processo — formato NNNNNNN-DD.AAAA.J.TT.OOOO"
    )
    cliente_id: int = Field(ge=1)
    polo_cliente: str = Field(
        default="autor",
        description="Posição do cliente no processo: autor | reu | terceiro",
    )
    tipo_acao: str | None = Field(
        default=None,
        max_length=200,
        description="Ex: Ação de Cobrança, Ação Trabalhista",
    )

    @field_validator("numero_cnj")
    @classmethod
    def validar_numero_cnj(cls, v: str) -> str:
        normalizado = v.strip()
        if not validar_numero_processo(normalizado):
            raise ValueError(
                "Número de processo inválido — formato esperado: NNNNNNN-DD.AAAA.J.TT.OOOO"
                " (ex: 0001234-56.2024.8.26.0100) ou dígito verificador incorreto"
            )
        return normalizado

    @field_validator("polo_cliente")
    @classmethod
    def validar_polo(cls, v: str) -> str:
        normalizado = v.lower().strip()
        if normalizado not in _POLOS_VALIDOS:
            raise ValueError(f"Polo inválido — opções: {', '.join(sorted(_POLOS_VALIDOS))}")
        return normalizado


class ProcessoUpdate(BaseModel):
    """
    Campos atualizáveis de um processo.
    Dados processuais (tribunal, vara, comarca) são sincronizados via
    Jusbrasil — não são editados manualmente.
    """

    polo_cliente: str | None = Field(default=None)
    tipo_acao: str | None = Field(default=None, max_length=200)
    advogado_responsavel_id: int | None = Field(default=None, ge=1)
    monitoramento_ativo: bool | None = None
    frequencia_monitoramento: str | None = Field(default=None)

    @field_validator("polo_cliente")
    @classmethod
    def validar_polo(cls, v: str | None) -> str | None:
        if v is None:
            return v
        normalizado = v.lower().strip()
        if normalizado not in _POLOS_VALIDOS:
            raise ValueError(f"Polo inválido — opções: {', '.join(sorted(_POLOS_VALIDOS))}")
        return normalizado

    @field_validator("frequencia_monitoramento")
    @classmethod
    def validar_frequencia(cls, v: str | None) -> str | None:
        if v is None:
            return v
        normalizado = v.lower().strip()
        if normalizado not in _FREQUENCIAS_VALIDAS:
            raise ValueError(
                f"Frequência inválida — opções: {', '.join(sorted(_FREQUENCIAS_VALIDAS))}"
            )
        return normalizado


class ProcessoResponse(BaseModel):
    """Representação pública do processo — retornada nos endpoints de listagem."""

    model_config = {"from_attributes": True}

    id: int
    escritorio_id: int
    cliente_id: int
    advogado_responsavel_id: int | None
    numero_cnj: str
    tribunal: str | None
    vara: str | None
    comarca: str | None
    tipo_acao: str | None
    polo_cliente: str
    status: str
    ultimo_andamento: str | None
    data_ultimo_andamento: datetime | None

    data_distribuicao: datetime | None
    valor_causa: Decimal | None
    jusbrasil_id: str | None
    monitoramento_ativo: bool
    frequencia_monitoramento: str | None = None
    created_at: datetime
    updated_at: datetime

    # --- Score de Risco (Feature 2) ---
    # Todos opcionais: null enquanto o worker não calculou ainda.
    # Uso interno do advogado — NÃO comunicar probabilidade de resultado ao cliente (OAB).
    score_risco: int | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Score de complexidade/risco 0–100 (uso interno do advogado)",
    )
    score_nivel: str | None = Field(
        default=None,
        description="baixo | moderado | alto | critico",
    )
    score_interpretacao: str | None = Field(
        default=None,
        description="Texto explicativo para o advogado",
    )
    score_atualizado_em: datetime | None = Field(default=None)


class ProcessoComAndamentos(ProcessoResponse):
    """
    Versão detalhada do processo — inclui histórico de andamentos recentes.
    Retornada em GET /processos/{id}.
    """

    andamentos: list[AndamentoSchema] = Field(
        default_factory=list,
        description="Últimos andamentos do processo (máx. 10), ordenados do mais recente",
    )


# Alias tipado para listagens paginadas de processos
ProcessoList = PaginatedResponse[ProcessoResponse]
