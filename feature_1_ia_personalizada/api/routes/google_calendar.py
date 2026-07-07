"""
Rotas de conexão do Google Calendar (Agendamento Inteligente).

Fluxo OAuth2 authorization-code por escritório:

  1. GET /google-calendar/auth-url   (JWT) → gera state de uso único no Redis
     e devolve a URL de consentimento; o frontend redireciona o navegador.
  2. GET /google-calendar/callback   (público — o Google chama sem JWT) →
     valida o state, troca o code por refresh_token, salva criptografado.
  3. GET /google-calendar/status     (JWT) → configurado/conectado.
  4. POST /google-calendar/disconnect(JWT) → limpa a conexão.
"""

from __future__ import annotations

import secrets
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from feature_1_ia_personalizada.services.agendamento.google_calendar import (
    integracao_configurada,
    limpar_conexao,
    montar_auth_url,
    salvar_conexao,
    trocar_code_por_refresh_token,
)
from shared.config.settings import settings
from shared.database.session import get_db
from shared.models.escritorio import Escritorio

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/google-calendar", tags=["Agendamento — Google Calendar"])

_STATE_TTL_S = 600  # 10 min para o advogado concluir o consentimento
_STATE_PREFIX = "gcal_state:"


def _escritorio_id(request: Request) -> int:
    if not hasattr(request.state, "user_payload"):
        raise HTTPException(status_code=401, detail="Não autenticado")
    return int(request.state.user_payload["escritorio_id"])


def _redis(request: Request) -> Any:
    return getattr(request.app.state, "redis_client", None)


@router.get("/status")
async def status_conexao(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    eid = _escritorio_id(request)
    escritorio = await db.get(Escritorio, eid)
    if escritorio is None:
        raise HTTPException(status_code=404, detail="Escritório não encontrado")
    return {
        "configurado": integracao_configurada(),
        "conectado": bool(escritorio.google_calendar_refresh_token),
        "conectado_em": escritorio.google_calendar_conectado_em,
        "calendar_id": escritorio.google_calendar_id or "primary",
    }


@router.get("/auth-url")
async def gerar_auth_url(request: Request) -> dict[str, str]:
    if not integracao_configurada():
        raise HTTPException(
            status_code=503,
            detail=(
                "Integração Google Calendar não configurada no servidor "
                "(GOOGLE_CALENDAR_CLIENT_ID/SECRET/REDIRECT_URI)."
            ),
        )
    eid = _escritorio_id(request)
    r = _redis(request)
    if r is None:
        raise HTTPException(status_code=503, detail="Redis indisponível")

    state = secrets.token_urlsafe(32)
    await r.set(f"{_STATE_PREFIX}{state}", str(eid), ex=_STATE_TTL_S)
    return {"url": montar_auth_url(state)}


@router.get("/callback", include_in_schema=False)
async def callback_oauth(
    request: Request,
    db: AsyncSession = Depends(get_db),
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> RedirectResponse:
    """
    Redirect do Google (sem JWT — rota pública na whitelist do middleware).
    Segurança: state de uso único gerado por usuário autenticado em /auth-url.
    """
    # Com frontend em domínio próprio (Railway 2 serviços), FRONTEND_URL leva
    # o usuário de volta ao app; sem ela, redirect relativo (mesmo domínio)
    base = (settings.FRONTEND_URL or "").rstrip("/")
    destino_ok = f"{base}/?gcal=conectado"
    destino_erro = f"{base}/?gcal=erro"

    if error or not code or not state:
        logger.warning("gcal_callback_negado", error=error)
        return RedirectResponse(destino_erro)

    r = _redis(request)
    if r is None:
        return RedirectResponse(destino_erro)

    chave = f"{_STATE_PREFIX}{state}"
    eid_raw = await r.get(chave)
    if not eid_raw:
        logger.warning("gcal_callback_state_invalido")
        return RedirectResponse(destino_erro)
    await r.delete(chave)  # uso único

    escritorio = await db.get(Escritorio, int(eid_raw))
    if escritorio is None:
        return RedirectResponse(destino_erro)

    refresh_token = await trocar_code_por_refresh_token(code)
    if not refresh_token:
        return RedirectResponse(destino_erro)

    salvar_conexao(escritorio, refresh_token)
    await db.commit()
    logger.info("gcal_conectado", escritorio_id=escritorio.id)
    return RedirectResponse(destino_ok)


@router.post("/disconnect")
async def desconectar(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    eid = _escritorio_id(request)
    escritorio = await db.get(Escritorio, eid)
    if escritorio is None:
        raise HTTPException(status_code=404, detail="Escritório não encontrado")
    limpar_conexao(escritorio)
    await db.commit()
    logger.info("gcal_desconectado", escritorio_id=eid)
    return {"status": "desconectado"}
