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

Nota: _validar_numero_cnj / _validar_digito_cnj estão inline aqui por
enquanto. Quando shared/utils/validators.py for criado, migrar para lá.
"""

import re
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from shared.schemas.response import PaginatedResponse

# ---------------------------------------------------------------------------
# Helpers de validação (inline — migrar para shared/utils/validators.py)
# ---------------------------------------------------------------------------

_POLOS_VALIDOS = {"autor", "reu", "terceiro"}
_FREQUENCIAS_VALIDAS = {"diario", "semanal"}
# Nota: status é gerenciado pelo sistema (não validado aqui).
# Valores possíveis: ativo | arquivado | suspenso | encerrado

# CNJ: NNNNNNN-DD.AAAA.J.TT.OOOO
# Segmento de justiça (J): 1-9  |  Tribunal (TT): 01-99  |  Origem (OOOO): 0001-9999
_CNJ_REGEX = re.compile(r"^\d{7}-\d{2}\.\d{4}\.[1-9]\.\d{2}\.\d{4}$")


def _validar_formato_cnj(numero: str) -> bool:
    """Valida apenas a estrutura do número CNJ (regex)."""
    return bool(_CNJ_REGEX.match(numero.strip()))


def _validar_digito_cnj(numero: str) -> bool:
    """
    Valida o dígito verificador do número CNJ usando ISO 7064 MOD 97-10.

    Algoritmo (Resolução CNJ nº 65/2008):
    1. Extrair componentes: NNNNNNN, DD, AAAA, J, TT, OOOO
    2. Formar base: NNNNNNN + AAAA + J + TT + OOOO  (sem DD)
    3. Calcular: DD_esperado = 98 - (int(base + "00") % 97)
    4. Comparar DD_esperado com DD extraído do número
    """
    partes = re.split(r"[-.]", numero.strip())
    if len(partes) != 6:
        return False

    nnnnnnn, dd_str, aaaa, j, tt, oooo = partes
    base = nnnnnnn + aaaa + j + tt + oooo
    dd_esperado = 98 - (int(base + "00") % 97)

    return int(dd_str) == dd_esperado


# ---------------------------------------------------------------------------
# Schemas auxiliares
# ---------------------------------------------------------------------------

# Tipos de andamento definidos pelo DataCleaner — usados como Literal para
# garantir que apenas valores conhecidos sejam aceitos
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
    descricao: str = Field(min_length=1, description="Texto do andamento (já limpo pelo DataCleaner)")
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
        if not _validar_formato_cnj(normalizado):
            raise ValueError(
                "Número de processo inválido — formato esperado: NNNNNNN-DD.AAAA.J.TT.OOOO"
                " (ex: 0001234-56.2024.8.26.0100)"
            )
        if not _validar_digito_cnj(normalizado):
            raise ValueError(
                "Número de processo inválido — dígito verificador incorreto (DD)"
            )
        return normalizado

    @field_validator("polo_cliente")
    @classmethod
    def validar_polo(cls, v: str) -> str:
        # Nota: string vazia ("") passa pelo `if v is None` mas falha no `not in`
        # levantando ValueError corretamente — comportamento intencional
        normalizado = v.lower().strip()
        if normalizado not in _POLOS_VALIDOS:
            raise ValueError(
                f"Polo inválido — opções: {', '.join(sorted(_POLOS_VALIDOS))}"
            )
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
        # String vazia falha corretamente no `not in` — intencional
        normalizado = v.lower().strip()
        if normalizado not in _POLOS_VALIDOS:
            raise ValueError(
                f"Polo inválido — opções: {', '.join(sorted(_POLOS_VALIDOS))}"
            )
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
    # str | None para compatibilidade com registros legados que possam ter NULL
    frequencia_monitoramento: str | None = None
    created_at: datetime
    updated_at: datetime


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
