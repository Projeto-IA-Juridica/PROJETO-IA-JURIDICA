"""
feature_1_ia_personalizada/api/routes/escritorios.py
=====================================================
Endpoints de configuração do escritório autenticado.

GET  /escritorios/config  — retorna config atual
PUT  /escritorios/config  — atualiza campos editáveis pelo admin
"""

from __future__ import annotations

from datetime import datetime as _dt

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database.session import get_db
from shared.models.escritorio import Escritorio
from shared.utils.validators import validar_telefone_br

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/escritorios", tags=["Escritórios"])

_TONS_VALIDOS = {"formal", "amigavel", "neutro"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_escritorio_id(request: Request) -> int:
    payload = getattr(request.state, "user_payload", None)
    if not isinstance(payload, dict):
        raise HTTPException(status_code=401, detail="Não autenticado.")
    return int(payload["escritorio_id"])


def _time_to_str(t) -> str | None:
    return t.strftime("%H:%M") if t else None


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ConfigResponse(BaseModel):
    nome: str
    cnpj: str
    email: str
    telefone: str | None
    persona_nome: str
    persona_tom: str
    horario_inicio: str
    horario_fim: str
    template_boas_vindas: str | None
    template_atualizacao: str | None
    template_sem_novidade: str | None


class ConfigUpdateRequest(BaseModel):
    nome: str | None = Field(default=None, min_length=2, max_length=200)
    email: EmailStr | None = None
    telefone: str | None = None
    persona_nome: str | None = Field(default=None, max_length=100)
    persona_tom: str | None = None
    horario_inicio: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    horario_fim: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    template_boas_vindas: str | None = Field(default=None, max_length=2000)
    template_atualizacao: str | None = Field(default=None, max_length=2000)
    template_sem_novidade: str | None = Field(default=None, max_length=2000)

    @field_validator("persona_tom")
    @classmethod
    def _validar_tom(cls, v: str | None) -> str | None:
        if v is None:
            return v
        normalizado = v.lower().strip()
        if normalizado not in _TONS_VALIDOS:
            raise ValueError(f"Tom inválido — opções: {', '.join(sorted(_TONS_VALIDOS))}")
        return normalizado

    @field_validator("telefone")
    @classmethod
    def _validar_telefone(cls, v: str | None) -> str | None:
        if not v:
            return None
        if not validar_telefone_br(v):
            raise ValueError("Telefone inválido — use formato brasileiro (ex: (11) 99999-9999)")
        return v


def _escritorio_to_response(e: Escritorio) -> ConfigResponse:
    return ConfigResponse(
        nome=e.nome,
        cnpj=e.cnpj,
        email=e.email,
        telefone=e.telefone,
        persona_nome=e.persona_nome or "Assistente Jurídico",
        persona_tom=e.persona_tom or "formal",
        horario_inicio=_time_to_str(e.horario_inicio) or "08:00",
        horario_fim=_time_to_str(e.horario_fim) or "18:00",
        template_boas_vindas=e.template_boas_vindas,
        template_atualizacao=e.template_atualizacao,
        template_sem_novidade=e.template_sem_novidade,
    )


# ---------------------------------------------------------------------------
# GET /escritorios/config
# ---------------------------------------------------------------------------


@router.get("/config", response_model=ConfigResponse)
async def get_config(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Retorna a configuração atual do escritório autenticado."""
    escritorio_id = _get_escritorio_id(request)
    escritorio: Escritorio | None = await db.get(Escritorio, escritorio_id)
    if not escritorio:
        raise HTTPException(status_code=404, detail="Escritório não encontrado.")
    return _escritorio_to_response(escritorio)


# ---------------------------------------------------------------------------
# PUT /escritorios/config
# ---------------------------------------------------------------------------


@router.put("/config", response_model=ConfigResponse)
async def put_config(
    body: ConfigUpdateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Atualiza campos editáveis do escritório. CNPJ e plano são imutáveis."""
    escritorio_id = _get_escritorio_id(request)
    escritorio: Escritorio | None = await db.get(Escritorio, escritorio_id)
    if not escritorio:
        raise HTTPException(status_code=404, detail="Escritório não encontrado.")

    if body.nome is not None:
        escritorio.nome = body.nome
    if body.email is not None:
        escritorio.email = str(body.email)
    if body.telefone is not None:
        escritorio.telefone = body.telefone
    if body.persona_nome is not None:
        escritorio.persona_nome = body.persona_nome
    if body.persona_tom is not None:
        escritorio.persona_tom = body.persona_tom

    if body.horario_inicio is not None:
        try:
            escritorio.horario_inicio = _dt.strptime(body.horario_inicio, "%H:%M").time()
        except ValueError:
            raise HTTPException(status_code=400, detail="horario_inicio inválido.")
    if body.horario_fim is not None:
        try:
            escritorio.horario_fim = _dt.strptime(body.horario_fim, "%H:%M").time()
        except ValueError:
            raise HTTPException(status_code=400, detail="horario_fim inválido.")

    h_inicio = escritorio.horario_inicio
    h_fim = escritorio.horario_fim
    if h_inicio and h_fim and h_inicio >= h_fim:
        raise HTTPException(
            status_code=400,
            detail="horario_inicio deve ser anterior a horario_fim.",
        )

    # Strings vazias limpam o campo; None mantém valor atual
    if body.template_boas_vindas is not None:
        escritorio.template_boas_vindas = body.template_boas_vindas or None
    if body.template_atualizacao is not None:
        escritorio.template_atualizacao = body.template_atualizacao or None
    if body.template_sem_novidade is not None:
        escritorio.template_sem_novidade = body.template_sem_novidade or None

    await db.commit()
    await db.refresh(escritorio)

    logger.info("config_atualizada", escritorio_id=escritorio_id)
    return _escritorio_to_response(escritorio)
