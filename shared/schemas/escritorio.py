"""
shared/schemas/escritorio.py
=============================
Schemas Pydantic para o recurso Escritório.

- EscritorioCreate  → criação de novo escritório (POST)
- EscritorioUpdate  → atualização parcial (PUT/PATCH)
- EscritorioResponse → retorno da API (sem dados sensíveis internos)
- EscritorioList    → alias tipado de PaginatedResponse[EscritorioResponse]
"""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from shared.schemas.response import PaginatedResponse
from shared.utils.validators import (
    normalizar_cnpj,
    validar_cnpj,
    validar_oab,
    validar_telefone_br,
)

# ---------------------------------------------------------------------------
# Constantes de schema (específicas deste recurso)
# ---------------------------------------------------------------------------

_PLANOS_VALIDOS = {"basico", "profissional", "enterprise"}

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
        if not validar_cnpj(v):
            raise ValueError("CNPJ inválido — verifique os dígitos verificadores")
        return normalizar_cnpj(v)  # armazena só os dígitos

    @field_validator("oab_responsavel")
    @classmethod
    def validar_oab_responsavel(cls, v: str) -> str:
        normalizado = v.upper().strip()
        if not validar_oab(normalizado):
            raise ValueError("OAB inválida — formato esperado: UFNNNNN (ex: SP123456)")
        return normalizado

    @field_validator("telefone")
    @classmethod
    def validar_telefone(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not validar_telefone_br(v):
            raise ValueError("Telefone inválido — use formato brasileiro (ex: (11) 99999-9999)")
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
    def validar_oab_responsavel(cls, v: str | None) -> str | None:
        if v is None:
            return v
        normalizado = v.upper().strip()
        if not validar_oab(normalizado):
            raise ValueError("OAB inválida — formato esperado: UFNNNNN (ex: SP123456)")
        return normalizado

    @field_validator("telefone")
    @classmethod
    def validar_telefone(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not validar_telefone_br(v):
            raise ValueError("Telefone inválido — use formato brasileiro (ex: (11) 99999-9999)")
        return v

    @field_validator("plano")
    @classmethod
    def validar_plano(cls, v: str | None) -> str | None:
        if v is None:
            return v
        normalizado = v.lower().strip()  # normaliza para lowercase
        if normalizado not in _PLANOS_VALIDOS:
            raise ValueError(f"Plano inválido — opções: {', '.join(sorted(_PLANOS_VALIDOS))}")
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
