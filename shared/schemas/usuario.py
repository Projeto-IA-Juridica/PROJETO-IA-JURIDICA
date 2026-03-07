"""
shared/schemas/usuario.py
==========================
Schemas Pydantic para o recurso Usuário (advogados, assistentes, admins).

- UsuarioCreate   → cadastro de novo usuário (POST)
- UsuarioLogin    → autenticação (POST /auth/login)
- UsuarioResponse → retorno da API (sem senha_hash)
- TokenResponse   → tokens JWT retornados após login/refresh

Roles disponíveis: admin | advogado | assistente | estagiario

A validação de força de senha aqui cobre o mínimo necessário —
políticas mais avançadas (rotação, histórico) são responsabilidade
da camada de segurança.
"""

import re
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from shared.utils.validators import validar_oab

# ---------------------------------------------------------------------------
# Constantes de schema (específicas deste recurso)
# ---------------------------------------------------------------------------

_ROLES_VALIDAS = {"admin", "advogado", "assistente", "estagiario"}

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class UsuarioCreate(BaseModel):
    """Campos para cadastro de um novo usuário interno do escritório."""

    nome: str = Field(min_length=2, max_length=200)
    email: EmailStr
    senha: str = Field(
        min_length=8,
        description="Senha plain-text — será hasheada com bcrypt pela camada de serviço",
    )
    role: str = Field(
        default="advogado",
        description="Perfil de acesso: admin | advogado | assistente | estagiario",
    )
    oab: str | None = Field(
        default=None,
        description="Número OAB — obrigatório para role=advogado (ex: SP123456)",
    )

    @field_validator("senha")
    @classmethod
    def validar_senha(cls, v: str) -> str:
        erros = []
        if not re.search(r"[A-Z]", v):
            erros.append("pelo menos uma letra maiúscula")
        if not re.search(r"[a-z]", v):
            erros.append("pelo menos uma letra minúscula")
        if not re.search(r"\d", v):
            erros.append("pelo menos um número")
        if erros:
            raise ValueError(f"Senha fraca — exige: {', '.join(erros)}")
        return v  # plain-text; o serviço faz o hash antes de salvar

    @field_validator("role")
    @classmethod
    def validar_role(cls, v: str) -> str:
        normalizado = v.lower().strip()
        if normalizado not in _ROLES_VALIDAS:
            raise ValueError(f"Role inválida — opções: {', '.join(sorted(_ROLES_VALIDAS))}")
        return normalizado

    @field_validator("oab")
    @classmethod
    def validar_oab(cls, v: str | None) -> str | None:
        if v is None:
            return v
        normalizado = v.upper().strip()
        if not validar_oab(normalizado):
            raise ValueError("OAB inválida — formato esperado: UFNNNNN (ex: SP123456)")
        return normalizado


class UsuarioLogin(BaseModel):
    """Credenciais para autenticação — POST /auth/login."""

    email: EmailStr
    senha: str = Field(min_length=1, description="Senha plain-text para verificação")


class UsuarioResponse(BaseModel):
    """
    Representação pública do usuário — retornada nos endpoints.
    senha_hash NUNCA é exposto.
    """

    model_config = {"from_attributes": True}

    id: int
    escritorio_id: int
    nome: str
    email: str
    role: str
    oab: str | None
    ativo: bool
    ultimo_login: datetime | None
    created_at: datetime
    updated_at: datetime


class TokenResponse(BaseModel):
    """
    Tokens JWT retornados após login ou refresh.

    - access_token: token de curta duração para autenticação de requests
    - refresh_token: token de longa duração (7 dias) para renovar o access_token
    - token_type: sempre "bearer"
    - expires_in: segundos até o access_token expirar
    """

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(
        gt=0,
        description="Segundos até o access_token expirar (definido em JWT_EXPIRATION_MINUTES)",
    )
