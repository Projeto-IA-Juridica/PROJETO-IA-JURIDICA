"""
Integração Google Calendar do Agendamento Inteligente.

Caso de uso central: escritórios com secretária já vivem no Google Calendar.
Conectando as duas agendas:

  1. Reunião confirmada aqui → evento criado na agenda do Google (a secretária
     vê sem abrir o Hub); cancelamento/remarcação remove o evento.
  2. Horários ocupados no Google (audiência marcada pela secretária, almoço,
     outra reunião) → deixam de ser oferecidos pela IA (freeBusy no detector).

Decisões de projeto:
  - OAuth2 authorization-code por escritório; refresh token criptografado
    (Fernet) em Escritorio.google_calendar_refresh_token. Sem SDK do Google —
    REST puro com httpx (zero dependências novas).
  - TUDO best-effort: Google fora do ar nunca bloqueia confirmação nem
    proposta. Falha de freeBusy → propõe sem o filtro; falha de sync →
    loga e segue (o evento pode ser recriado manualmente).
  - Integração desabilitada de forma limpa quando as envs
    GOOGLE_CALENDAR_CLIENT_ID/SECRET/REDIRECT_URI não existem.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config.settings import settings
from shared.models.agendamento import Agendamento
from shared.models.escritorio import Escritorio
from shared.security.encryption import criptografar, descriptografar

logger = structlog.get_logger(__name__)

_OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
_OAUTH_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_CALENDAR_API = "https://www.googleapis.com/calendar/v3"
_SCOPES = "https://www.googleapis.com/auth/calendar.events https://www.googleapis.com/auth/calendar.freebusy"

_HTTP_TIMEOUT_S = 8.0  # curto: integração acessória não pode segurar o fluxo


def integracao_configurada() -> bool:
    return bool(
        settings.GOOGLE_CALENDAR_CLIENT_ID
        and settings.GOOGLE_CALENDAR_CLIENT_SECRET
        and settings.GOOGLE_CALENDAR_REDIRECT_URI
    )


def escritorio_conectado(escritorio: Escritorio) -> bool:
    return integracao_configurada() and bool(escritorio.google_calendar_refresh_token)


def montar_auth_url(state: str) -> str:
    """URL de consentimento OAuth. access_type=offline + prompt=consent → refresh token."""
    params = httpx.QueryParams(
        client_id=settings.GOOGLE_CALENDAR_CLIENT_ID or "",
        redirect_uri=settings.GOOGLE_CALENDAR_REDIRECT_URI or "",
        response_type="code",
        scope=_SCOPES,
        access_type="offline",
        prompt="consent",
        state=state,
    )
    return f"{_OAUTH_AUTH_URL}?{params}"


async def trocar_code_por_refresh_token(code: str) -> str | None:
    """Troca o authorization code por refresh_token. None em falha (logada)."""
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_S) as http:
        try:
            resp = await http.post(
                _OAUTH_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": settings.GOOGLE_CALENDAR_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CALENDAR_CLIENT_SECRET,
                    "redirect_uri": settings.GOOGLE_CALENDAR_REDIRECT_URI,
                    "grant_type": "authorization_code",
                },
            )
            resp.raise_for_status()
            refresh = resp.json().get("refresh_token")
            if not refresh:
                logger.error("gcal_callback_sem_refresh_token")
                return None
            return str(refresh)
        except Exception as exc:
            logger.error("gcal_troca_code_falhou", erro=str(exc))
            return None


class GoogleCalendarClient:
    """
    Cliente REST mínimo (events.insert / events.delete / freeBusy).
    `http` injetável para testes; access token cacheado na instância.
    """

    def __init__(self, refresh_token: str, http: httpx.AsyncClient | None = None) -> None:
        self._refresh_token = refresh_token
        self._http = http or httpx.AsyncClient(timeout=_HTTP_TIMEOUT_S)
        self._http_externo = http is not None
        self._access_token: str | None = None
        self._token_expira_em: float = 0.0

    async def aclose(self) -> None:
        if not self._http_externo:
            await self._http.aclose()

    async def _obter_access_token(self) -> str:
        if self._access_token and time.monotonic() < self._token_expira_em:
            return self._access_token
        resp = await self._http.post(
            _OAUTH_TOKEN_URL,
            data={
                "client_id": settings.GOOGLE_CALENDAR_CLIENT_ID,
                "client_secret": settings.GOOGLE_CALENDAR_CLIENT_SECRET,
                "refresh_token": self._refresh_token,
                "grant_type": "refresh_token",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        self._access_token = str(data["access_token"])
        # renova 60s antes de expirar
        self._token_expira_em = time.monotonic() + int(data.get("expires_in", 3600)) - 60
        return self._access_token

    async def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {await self._obter_access_token()}"}

    async def criar_evento(
        self,
        calendar_id: str,
        titulo: str,
        descricao: str,
        inicio: datetime,
        fim: datetime,
        timezone_str: str,
    ) -> str:
        """Cria o evento e retorna o event id."""
        payload = {
            "summary": titulo,
            "description": descricao,
            "start": {"dateTime": inicio.isoformat(), "timeZone": timezone_str},
            "end": {"dateTime": fim.isoformat(), "timeZone": timezone_str},
            "reminders": {"useDefault": True},
        }
        resp = await self._http.post(
            f"{_CALENDAR_API}/calendars/{calendar_id}/events",
            json=payload,
            headers=await self._headers(),
        )
        resp.raise_for_status()
        return str(resp.json()["id"])

    async def deletar_evento(self, calendar_id: str, event_id: str) -> bool:
        resp = await self._http.delete(
            f"{_CALENDAR_API}/calendars/{calendar_id}/events/{event_id}",
            headers=await self._headers(),
        )
        # 404/410 = já não existe — objetivo atingido
        if resp.status_code in (404, 410):
            return True
        resp.raise_for_status()
        return True

    async def listar_ocupados(
        self, calendar_id: str, inicio: datetime, fim: datetime
    ) -> list[tuple[datetime, datetime]]:
        """freeBusy: intervalos ocupados na agenda no período (UTC-aware)."""
        resp = await self._http.post(
            f"{_CALENDAR_API}/freeBusy",
            json={
                "timeMin": inicio.astimezone(UTC).isoformat(),
                "timeMax": fim.astimezone(UTC).isoformat(),
                "items": [{"id": calendar_id}],
            },
            headers=await self._headers(),
        )
        resp.raise_for_status()
        busy = resp.json().get("calendars", {}).get(calendar_id, {}).get("busy", [])
        ocupados: list[tuple[datetime, datetime]] = []
        for item in busy:
            try:
                ini = datetime.fromisoformat(item["start"].replace("Z", "+00:00"))
                end = datetime.fromisoformat(item["end"].replace("Z", "+00:00"))
                ocupados.append((ini, end))
            except (KeyError, ValueError):
                continue
        return ocupados


def _calendar_id(escritorio: Escritorio) -> str:
    return escritorio.google_calendar_id or "primary"


def _client_do_escritorio(escritorio: Escritorio) -> GoogleCalendarClient | None:
    if not escritorio_conectado(escritorio):
        return None
    try:
        refresh = descriptografar(escritorio.google_calendar_refresh_token or "")
    except Exception:
        logger.error("gcal_refresh_token_indecifravel", escritorio_id=escritorio.id)
        return None
    return GoogleCalendarClient(refresh_token=refresh)


def salvar_conexao(escritorio: Escritorio, refresh_token: str) -> None:
    """Persiste a conexão no modelo (caller commita)."""
    escritorio.google_calendar_refresh_token = criptografar(refresh_token)
    escritorio.google_calendar_conectado_em = datetime.now(UTC)


def limpar_conexao(escritorio: Escritorio) -> None:
    escritorio.google_calendar_refresh_token = None
    escritorio.google_calendar_conectado_em = None


# ---------------------------------------------------------------------------
# Hooks de alto nível (best-effort — nunca levantam para o caller)
# ---------------------------------------------------------------------------


async def obter_ocupados_google(
    escritorio: Escritorio, inicio: datetime, fim: datetime
) -> list[tuple[datetime, datetime]]:
    """Intervalos ocupados na agenda externa; [] se desconectado ou em falha."""
    client = _client_do_escritorio(escritorio)
    if client is None:
        return []
    try:
        return await client.listar_ocupados(_calendar_id(escritorio), inicio, fim)
    except Exception as exc:
        logger.warning("gcal_freebusy_falhou", escritorio_id=escritorio.id, erro=str(exc))
        return []
    finally:
        await client.aclose()


async def sincronizar_confirmacao(session: AsyncSession, ag: Agendamento) -> bool:
    """
    Cria o evento da reunião confirmada na agenda do escritório e persiste
    google_event_id. Idempotente: evento já criado → no-op.
    """
    if ag.google_event_id or not ag.data_hora_inicio or not ag.data_hora_fim:
        return False
    escritorio = await session.get(Escritorio, ag.escritorio_id)
    if escritorio is None:
        return False
    client = _client_do_escritorio(escritorio)
    if client is None:
        return False

    from shared.models.cliente import Cliente

    cliente = await session.get(Cliente, ag.cliente_id)
    nome_cliente = cliente.nome if cliente else f"cliente #{ag.cliente_id}"

    try:
        event_id = await client.criar_evento(
            calendar_id=_calendar_id(escritorio),
            titulo=f"Reunião — {nome_cliente}",
            descricao=(
                "Reunião agendada pelo Agendamento Inteligente (amicus).\n"
                f"Cliente: {nome_cliente}\n"
                f"Motivo: {ag.motivo_cliente or 'conversar sobre o processo'}"
            ),
            inicio=ag.data_hora_inicio,
            fim=ag.data_hora_fim,
            timezone_str=escritorio.timezone or "America/Sao_Paulo",
        )
        ag.google_event_id = event_id
        await session.commit()
        logger.info("gcal_evento_criado", agendamento_id=ag.id, event_id=event_id)
        return True
    except Exception as exc:
        logger.warning("gcal_criar_evento_falhou", agendamento_id=ag.id, erro=str(exc))
        return False
    finally:
        await client.aclose()


async def remover_evento_agendamento(session: AsyncSession, ag: Agendamento) -> bool:
    """Remove o evento do Google (cancelamento/remarcação) e limpa o event_id."""
    if not ag.google_event_id:
        return False
    escritorio = await session.get(Escritorio, ag.escritorio_id)
    if escritorio is None:
        return False
    client = _client_do_escritorio(escritorio)
    if client is None:
        return False
    try:
        await client.deletar_evento(_calendar_id(escritorio), ag.google_event_id)
        ag.google_event_id = None
        await session.commit()
        logger.info("gcal_evento_removido", agendamento_id=ag.id)
        return True
    except Exception as exc:
        logger.warning("gcal_remover_evento_falhou", agendamento_id=ag.id, erro=str(exc))
        return False
    finally:
        await client.aclose()
