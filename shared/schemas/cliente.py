"""
shared/schemas/cliente.py
==========================
Schemas Pydantic para o recurso Cliente.

- ClienteCreate      → criação de novo cliente (POST)
- ClienteUpdate      → atualização parcial (PUT/PATCH)
- ClienteResponse    → retorno da API (CPF mascarado, idade calculada)
- ClienteAceiteLGPD  → registro de aceite dos termos LGPD

Notas sobre CPF:
- Em ClienteCreate, o CPF é recebido em plaintext e validado aqui.
  A criptografia (AES-256 Fernet) é responsabilidade da camada de serviço.
- Em ClienteResponse, o campo cpf_mascarado é populado pelo serviço
  após descriptografar e mascarar (***.***.***-XX).
"""

import re
from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from shared.schemas.response import PaginatedResponse
from shared.utils.validators import (
    normalizar_cpf,
    validar_cpf,
    validar_telefone_whatsapp,
)

# ---------------------------------------------------------------------------
# Constantes de schema (específicas deste recurso)
# ---------------------------------------------------------------------------

_PREFERENCIAS_HORARIO = {"comercial", "qualquer", "silencioso"}

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ClienteCreate(BaseModel):
    """Campos para criação de um novo cliente."""

    nome: str = Field(min_length=2, max_length=200)
    cpf: str = Field(description="CPF com ou sem formatação (XXX.XXX.XXX-XX)")
    telefone_whatsapp: str = Field(
        description="Formato: 5511999999999 (55 + DDD + número)"
    )
    email: EmailStr | None = None
    data_nascimento: date | None = Field(
        default=None,
        description="Data de nascimento — cliente deve ter pelo menos 18 anos",
    )
    profissao: str | None = Field(default=None, max_length=100)
    empresa_atual: str | None = Field(default=None, max_length=200)
    cargo: str | None = Field(default=None, max_length=100)

    @field_validator("cpf")
    @classmethod
    def validar_cpf(cls, v: str) -> str:
        if not validar_cpf(v):
            raise ValueError("CPF inválido — verifique os dígitos verificadores")
        return normalizar_cpf(v)  # armazena sem formatação (antes de criptografar)

    @field_validator("telefone_whatsapp")
    @classmethod
    def validar_telefone_whatsapp(cls, v: str) -> str:
        digits = re.sub(r"[^0-9]", "", v)
        if not validar_telefone_whatsapp(digits):
            raise ValueError(
                "Telefone WhatsApp inválido — formato esperado: 5511999999999"
                " (55 + DDD + número)"
            )
        return digits  # normaliza para apenas dígitos

    @field_validator("data_nascimento")
    @classmethod
    def validar_data_nascimento(cls, v: date | None) -> date | None:
        if v is None:
            return v

        hoje = date.today()

        if v > hoje:
            raise ValueError("Data de nascimento não pode ser futura")

        anos = hoje.year - v.year - ((hoje.month, hoje.day) < (v.month, v.day))

        if anos < 18:
            raise ValueError("Cliente deve ter pelo menos 18 anos")

        if anos > 150:
            raise ValueError("Data de nascimento inválida (mais de 150 anos atrás)")

        return v


class ClienteUpdate(BaseModel):
    """Todos os campos opcionais — permite partial update."""

    nome: str | None = Field(default=None, min_length=2, max_length=200)
    email: EmailStr | None = None
    telefone_whatsapp: str | None = Field(default=None)
    data_nascimento: date | None = None
    profissao: str | None = Field(default=None, max_length=100)
    empresa_atual: str | None = Field(default=None, max_length=200)
    cargo: str | None = Field(default=None, max_length=100)
    preferencia_horario_notificacao: str | None = Field(default=None)
    ativo: bool | None = None

    @field_validator("telefone_whatsapp")
    @classmethod
    def validar_telefone_whatsapp(cls, v: str | None) -> str | None:
        if v is None:
            return v
        digits = re.sub(r"[^0-9]", "", v)
        if not validar_telefone_whatsapp(digits):
            raise ValueError(
                "Telefone WhatsApp inválido — formato esperado: 5511999999999"
            )
        return digits

    @field_validator("data_nascimento")
    @classmethod
    def validar_data_nascimento(cls, v: date | None) -> date | None:
        if v is None:
            return v
        hoje = date.today()
        if v > hoje:
            raise ValueError("Data de nascimento não pode ser futura")
        anos = hoje.year - v.year - ((hoje.month, hoje.day) < (v.month, v.day))
        if anos < 18:
            raise ValueError("Cliente deve ter pelo menos 18 anos")
        if anos > 150:
            raise ValueError("Data de nascimento inválida (mais de 150 anos atrás)")
        return v

    @field_validator("preferencia_horario_notificacao")
    @classmethod
    def validar_preferencia(cls, v: str | None) -> str | None:
        if v is None:
            return v
        normalizado = v.lower().strip()
        if normalizado not in _PREFERENCIAS_HORARIO:
            raise ValueError(
                f"Preferência inválida — opções: {', '.join(sorted(_PREFERENCIAS_HORARIO))}"
            )
        return normalizado


class ClienteResponse(BaseModel):
    """
    Representação pública do cliente — retornada nos endpoints.

    - cpf_mascarado: populado pelo serviço após descriptografar + mascarar
    - idade: calculado pelo serviço a partir de data_nascimento (None se ausente)
    - cpf raw NÃO é exposto
    """

    model_config = {"from_attributes": True}

    id: int
    escritorio_id: int
    nome: str
    cpf_mascarado: str = Field(description="CPF no formato ***.***.***-XX")
    email: str | None
    telefone_whatsapp: str
    data_nascimento: date | None
    idade: int | None = Field(
        default=None,
        description="Idade calculada em anos — None se data_nascimento não informada",
    )
    profissao: str | None
    empresa_atual: str | None
    cargo: str | None
    aceite_lgpd: bool
    data_aceite_lgpd: datetime | None
    preferencia_horario_notificacao: str
    ativo: bool
    created_at: datetime
    updated_at: datetime


class ClienteAceiteLGPD(BaseModel):
    """Schema para registrar o aceite dos termos LGPD pelo cliente."""

    aceite: bool = Field(
        default=True,
        description="Deve ser True — aceite explícito é obrigatório",
    )
    ip_origem: str | None = Field(
        default=None,
        description="IP do dispositivo do cliente — para trilha de auditoria LGPD",
    )

    @field_validator("aceite")
    @classmethod
    def aceite_deve_ser_verdadeiro(cls, v: bool) -> bool:
        if not v:
            raise ValueError(
                "O aceite LGPD deve ser confirmado (true) — não é possível registrar recusa"
            )
        return v


# Alias tipado para listagens paginadas de clientes
ClienteList = PaginatedResponse[ClienteResponse]
