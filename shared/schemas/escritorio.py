"""
shared/schemas/escritorio.py
=============================
Schemas Pydantic para o recurso Escritório.

- EscritorioCreate  → criação de novo escritório (POST)
- EscritorioUpdate  → atualização parcial (PUT/PATCH)
- EscritorioResponse → retorno da API (sem dados sensíveis internos)
- EscritorioList    → alias tipado de PaginatedResponse[EscritorioResponse]

Nota: as funções _validar_cnpj / _validar_oab / _validar_telefone_br estão
inline aqui por enquanto. Quando shared/utils/validators.py for criado,
migrar a lógica para lá e substituir por chamadas diretas.
"""

import re
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from shared.schemas.response import PaginatedResponse

# ---------------------------------------------------------------------------
# Helpers de validação (inline — migrar para shared/utils/validators.py)
# ---------------------------------------------------------------------------

_PLANOS_VALIDOS = {"basico", "profissional", "enterprise"}


def _validar_cnpj(cnpj: str) -> bool:
    """Valida CNPJ com algoritmo oficial dos dígitos verificadores."""
    digits = re.sub(r"[^0-9]", "", cnpj)
    if len(digits) != 14:
        return False
    # Rejeita sequências repetidas (ex: 00000000000000)
    if digits == digits[0] * 14:
        return False

    def _calcular_digito(parcial: str, pesos: list[int]) -> int:
        total = sum(int(d) * p for d, p in zip(parcial, pesos))
        resto = total % 11
        return 0 if resto < 2 else 11 - resto

    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]

    if int(digits[12]) != _calcular_digito(digits[:12], pesos1):
        return False
    if int(digits[13]) != _calcular_digito(digits[:13], pesos2):
        return False
    return True


def _normalizar_cnpj(cnpj: str) -> str:
    """Remove formatação e retorna apenas os 14 dígitos."""
    return re.sub(r"[^0-9]", "", cnpj)


_OAB_REGEX = re.compile(r"^[A-Z]{2}\d{4,8}$")


def _validar_oab(oab: str) -> bool:
    """Valida formato OAB: 2 letras maiúsculas de UF + 4 a 8 dígitos."""
    return bool(_OAB_REGEX.match(oab.upper()))


# Aceita formatos: (11) 99999-9999 | 11 99999-9999 | 11999999999 | +5511999999999
_TEL_REGEX = re.compile(
    r"^(\+55\s?)?"           # prefixo internacional opcional
    r"(\(?\d{2}\)?\s?)"     # DDD com ou sem parênteses
    r"9?\d{4}"               # dígito 9 opcional + 4 dígitos
    r"[-]?"               # separador opcional
    r"\d{4}$"                # 4 dígitos finais
)


def _validar_telefone_br(telefone: str) -> bool:
    return bool(_TEL_REGEX.match(telefone.strip()))


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class EscritorioCreate(BaseModel):
    """Campos para criação de um novo escritório."""

    nome: str = Field(min_length=2, max_length=200)
    cnpj: str = Field(description="CNPJ com ou sem formatação (XX.XXX.XXX/XXXX-XX)")
    email: EmailStr
    telefone: str | None = Field(
        default=None,
        description="Telefone do escritório — formato brasileiro",
    )
    endereco: str | None = Field(default=None, max_length=500)
    oab_responsavel: str = Field(
        description="OAB do advogado responsável — formato UFNNNNN (ex: SP123456)",
    )
    nome_responsavel: str = Field(min_length=2, max_length=200)

    @field_validator("cnpj")
    @classmethod
    def validar_cnpj(cls, v: str) -> str:
        if not _validar_cnpj(v):
            raise ValueError("CNPJ inválido — verifique os dígitos verificadores")
        return _normalizar_cnpj(v)  # armazena só os dígitos

    @field_validator("oab_responsavel")
    @classmethod
    def validar_oab(cls, v: str) -> str:
        normalizado = v.upper().strip()
        if not _validar_oab(normalizado):
            raise ValueError(
                "OAB inválida — formato esperado: UFNNNNN (ex: SP123456)"
            )
        return normalizado

    @field_validator("telefone")
    @classmethod
    def validar_telefone(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not _validar_telefone_br(v):
            raise ValueError(
                "Telefone inválido — use formato brasileiro (ex: (11) 99999-9999)"
            )
        return v


class EscritorioUpdate(BaseModel):
    """Todos os campos opcionais — permite partial update."""

    nome: str | None = Field(default=None, min_length=2, max_length=200)
    email: EmailStr | None = None
    telefone: str | None = Field(default=None)
    endereco: str | None = Field(default=None, max_length=500)
    oab_responsavel: str | None = Field(default=None)
    nome_responsavel: str | None = Field(default=None, min_length=2, max_length=200)
    plano: str | None = Field(
        default=None,
        description="basico | profissional | enterprise",
    )
    ativo: bool | None = None
    max_processos: int | None = Field(default=None, ge=1)
    max_clientes: int | None = Field(default=None, ge=1)
    webhook_whatsapp_instance: str | None = Field(default=None, max_length=100)

    @field_validator("oab_responsavel")
    @classmethod
    def validar_oab(cls, v: str | None) -> str | None:
        if v is None:
            return v
        normalizado = v.upper().strip()
        if not _validar_oab(normalizado):
            raise ValueError(
                "OAB inválida — formato esperado: UFNNNNN (ex: SP123456)"
            )
        return normalizado

    @field_validator("telefone")
    @classmethod
    def validar_telefone(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not _validar_telefone_br(v):
            raise ValueError(
                "Telefone inválido — use formato brasileiro (ex: (11) 99999-9999)"
            )
        return v

    @field_validator("plano")
    @classmethod
    def validar_plano(cls, v: str | None) -> str | None:
        if v is None:
            return v
        normalizado = v.lower().strip()  # normaliza para lowercase
        if normalizado not in _PLANOS_VALIDOS:
            raise ValueError(
                f"Plano inválido — opções: {', '.join(sorted(_PLANOS_VALIDOS))}"
            )
        return normalizado


class EscritorioResponse(BaseModel):
    """Representação pública do escritório — retornada nos endpoints."""

    model_config = {"from_attributes": True}

    id: int
    nome: str
    cnpj: str
    email: str
    telefone: str | None
    endereco: str | None
    oab_responsavel: str
    nome_responsavel: str
    plano: str
    ativo: bool
    max_processos: int
    max_clientes: int
    webhook_whatsapp_instance: str | None
    created_at: datetime
    updated_at: datetime


# Alias tipado para listagens paginadas de escritórios
EscritorioList = PaginatedResponse[EscritorioResponse]
