import asyncio
import time
from collections.abc import Awaitable
from typing import Any, cast

import httpx
import redis.asyncio as redis
import structlog
from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config.settings import settings
from shared.database.session import get_db

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/health", tags=["Monitoramento"])

# Tempo máximo por verificação individual (segundos)
_CHECK_TIMEOUT = 5.0


# ------------------------------------------------------------------
# Verificações individuais
# ------------------------------------------------------------------


async def _check_postgresql(db: AsyncSession) -> dict[str, Any]:
    try:
        t = time.perf_counter()
        await db.execute(text("SELECT 1"))
        return {
            "status": "ok",
            "latency_ms": round((time.perf_counter() - t) * 1000, 2),
        }
    except TimeoutError:
        return {"status": "timeout", "detail": "PostgreSQL não respondeu em 5s"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


async def _check_redis(client: redis.Redis | None = None) -> dict[str, Any]:
    owned = client is None
    r: redis.Redis | None = client
    try:
        if r is None:
            r = redis.from_url(settings.REDIS_URL, decode_responses=True)
        t = time.perf_counter()
        await asyncio.wait_for(cast(Awaitable[bool], r.ping()), timeout=_CHECK_TIMEOUT)
        return {
            "status": "ok",
            "latency_ms": round((time.perf_counter() - t) * 1000, 2),
        }
    except TimeoutError:
        return {"status": "timeout", "detail": "Redis não respondeu em 5s"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}
    finally:
        if owned and r:
            await r.aclose()


async def _check_claude_api() -> dict[str, Any]:
    """Verifica conectividade com a Anthropic API via HEAD na URL base."""
    try:
        t = time.perf_counter()
        async with httpx.AsyncClient(timeout=_CHECK_TIMEOUT) as client:
            resp = await client.get(
                "https://api.anthropic.com",
                headers={"x-api-key": settings.ANTHROPIC_API_KEY},
            )
        latency_ms = round((time.perf_counter() - t) * 1000, 2)
        # Qualquer resposta (mesmo 404/400) confirma conectividade
        return {
            "status": "ok",
            "latency_ms": latency_ms,
            "http_status": resp.status_code,
        }
    except httpx.TimeoutException:
        return {"status": "timeout", "detail": "Claude API não respondeu em 5s"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


async def _check_evolution_api() -> dict[str, Any]:
    """Verifica conectividade com a Evolution API listando instâncias."""
    try:
        t = time.perf_counter()
        async with httpx.AsyncClient(
            timeout=_CHECK_TIMEOUT,
            headers={"apikey": settings.EVOLUTION_API_KEY},
        ) as client:
            resp = await client.get(f"{settings.EVOLUTION_API_URL}/instance/fetchInstances")
        latency_ms = round((time.perf_counter() - t) * 1000, 2)
        if resp.status_code < 500:
            return {
                "status": "ok",
                "latency_ms": latency_ms,
                "http_status": resp.status_code,
            }
        return {
            "status": "degraded",
            "latency_ms": latency_ms,
            "http_status": resp.status_code,
        }
    except httpx.TimeoutException:
        return {"status": "timeout", "detail": "Evolution API não respondeu em 5s"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


async def _check_celery_workers() -> dict[str, Any]:
    """Verifica se há workers Celery ativos via inspect().ping()."""

    def _inspect_sync() -> dict[str, Any]:
        try:
            from feature_1_ia_personalizada.workers.celery_app import celery_app

            inspector = celery_app.control.inspect(timeout=0.5)
            respostas = inspector.ping()
            if respostas:
                return {"status": "ok", "workers": list(respostas.keys())}
            return {"status": "degraded", "detail": "Nenhum worker respondeu ao ping"}
        except Exception as e:
            return {"status": "error", "detail": str(e)}

    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_inspect_sync),
            timeout=_CHECK_TIMEOUT,
        )
    except TimeoutError:
        return {"status": "timeout", "detail": "Inspect Celery não respondeu em 5s"}


async def _check_google_sheets() -> dict[str, Any]:
    """Verifica conectividade com o Google Sheets lendo a célula A1 da aba Clientes."""
    if not settings.GOOGLE_CREDENTIALS_PATH or not settings.GOOGLE_SHEETS_ID:
        return {
            "status": "skipped",
            "detail": "GOOGLE_CREDENTIALS_PATH ou GOOGLE_SHEETS_ID não configurados",
        }

    def _ping_sync() -> dict[str, Any]:
        try:
            from feature_1_ia_personalizada.services.integrations.google_sheets import (
                GoogleSheetsClient,
            )

            t = time.perf_counter()
            creds = settings.GOOGLE_CREDENTIALS_PATH or ""
            sheet_id = settings.GOOGLE_SHEETS_ID or ""
            client = GoogleSheetsClient(
                credentials_path=creds,
                spreadsheet_id=sheet_id,
            )
            client._ler_intervalo("Clientes!A1:A1")
            return {
                "status": "ok",
                "latency_ms": round((time.perf_counter() - t) * 1000, 2),
            }
        except Exception as e:
            return {"status": "error", "detail": str(e)}

    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_ping_sync),
            timeout=_CHECK_TIMEOUT + 5,  # Sheets pode ser mais lento
        )
    except TimeoutError:
        return {"status": "timeout", "detail": "Google Sheets não respondeu em 10s"}


# ------------------------------------------------------------------
# Rotas
# ------------------------------------------------------------------


@router.get("")
async def health_basic():
    """Health check superfícial — apenas verifica se a API está no ar."""
    return {"status": "ok", "service": "concierge-juridico"}


@router.get("/ready")
async def health_ready(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Verifica se a API está pronta: testa PostgreSQL e Redis.
    Retorna 503 se algum dos dois falhar.
    """
    redis_client: redis.Redis | None = getattr(request.app.state, "redis_client", None)
    pg, rd = await asyncio.gather(_check_postgresql(db), _check_redis(redis_client))

    health = {"status": "ok", "db": pg, "redis": rd}

    if pg["status"] != "ok" or rd["status"] != "ok":
        health["status"] = "error"
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=health)

    return health


@router.get("/detailed")
async def health_detailed(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Health check exaustivo — verifica todos os serviços:
      - PostgreSQL e Redis (críticos: falha → 503)
      - Claude API, Evolution API, Celery workers, Google Sheets (externos: falha → 200 degraded)
    """
    t_total = time.perf_counter()
    redis_client: redis.Redis | None = getattr(request.app.state, "redis_client", None)

    pg, rd, claude, evolution, celery_w, sheets = await asyncio.gather(
        _check_postgresql(db),
        _check_redis(redis_client),
        _check_claude_api(),
        _check_evolution_api(),
        _check_celery_workers(),
        _check_google_sheets(),
    )

    checks: dict[str, dict[str, Any]] = {
        "postgresql": pg,
        "redis": rd,
        "claude_api": claude,
        "evolution_api": evolution,
        "celery_workers": celery_w,
        "google_sheets": sheets,
    }

    critical_ok = pg["status"] == "ok" and rd["status"] == "ok"
    external_ok = all(
        v["status"] in ("ok", "skipped")
        for k, v in checks.items()
        if k not in ("postgresql", "redis")
    )

    if not critical_ok:
        overall = "error"
    elif not external_ok:
        overall = "degraded"
    else:
        overall = "ok"

    result: dict[str, Any] = {
        "status": overall,
        "total_ms": round((time.perf_counter() - t_total) * 1000, 2),
        "checks": checks,
    }

    logger.info(
        "health_detailed",
        status=overall,
        checks={k: v["status"] for k, v in checks.items()},
    )

    if not critical_ok:
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=result)

    return result
