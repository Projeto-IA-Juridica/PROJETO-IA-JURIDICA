#!/usr/bin/env python3
# scripts/monitoring/health_check.py
"""
Script standalone de health check — usável em CI/CD e cron.

Saída:
  exit 0 → PostgreSQL e Redis OK (serviços críticos saudáveis)
  exit 1 → falha em pelo menos um serviço crítico

Uso:
  python scripts/monitoring/health_check.py
  python scripts/monitoring/health_check.py --json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from typing import Any

# Garante que o root do projeto esteja no path, independente de onde o script é chamado
_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import httpx

_CHECK_TIMEOUT = 5.0


# ------------------------------------------------------------------
# Verificações individuais (sem dependência do FastAPI)
# ------------------------------------------------------------------


async def _check_postgresql(database_url: str) -> dict[str, Any]:
    try:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(
            database_url, pool_size=1, max_overflow=0, pool_pre_ping=True
        )
        t = time.perf_counter()
        async with engine.connect() as conn:
            await asyncio.wait_for(
                conn.execute(text("SELECT 1")), timeout=_CHECK_TIMEOUT
            )
        await engine.dispose()
        return {
            "status": "ok",
            "latency_ms": round((time.perf_counter() - t) * 1000, 2),
        }
    except TimeoutError:
        return {"status": "timeout", "detail": "PostgreSQL não respondeu em 5s"}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


async def _check_redis(redis_url: str) -> dict[str, Any]:
    r = None
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(redis_url, decode_responses=True)
        t = time.perf_counter()
        await asyncio.wait_for(r.ping(), timeout=_CHECK_TIMEOUT)
        return {
            "status": "ok",
            "latency_ms": round((time.perf_counter() - t) * 1000, 2),
        }
    except TimeoutError:
        return {"status": "timeout", "detail": "Redis não respondeu em 5s"}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}
    finally:
        if r:
            await r.aclose()


async def _check_claude_api(api_key: str) -> dict[str, Any]:
    try:
        t = time.perf_counter()
        async with httpx.AsyncClient(timeout=_CHECK_TIMEOUT) as client:
            resp = await client.get(
                "https://api.anthropic.com",
                headers={"x-api-key": api_key},
            )
        return {
            "status": "ok",
            "latency_ms": round((time.perf_counter() - t) * 1000, 2),
            "http_status": resp.status_code,
        }
    except httpx.TimeoutException:
        return {"status": "timeout", "detail": "Claude API não respondeu em 5s"}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


async def _check_evolution_api(url: str, api_key: str) -> dict[str, Any]:
    try:
        t = time.perf_counter()
        async with httpx.AsyncClient(
            timeout=_CHECK_TIMEOUT,
            headers={"apikey": api_key},
        ) as client:
            resp = await client.get(f"{url}/instance/fetchInstances")
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
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


async def _check_celery_workers(broker_url: str) -> dict[str, Any]:
    def _inspect_sync() -> dict[str, Any]:
        try:
            from celery import Celery

            app = Celery(broker=broker_url)
            inspector = app.control.inspect(timeout=3.0)
            respostas = inspector.ping()
            if respostas:
                return {"status": "ok", "workers": list(respostas.keys())}
            return {"status": "degraded", "detail": "Nenhum worker respondeu ao ping"}
        except Exception as exc:
            return {"status": "error", "detail": str(exc)}

    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_inspect_sync),
            timeout=_CHECK_TIMEOUT,
        )
    except TimeoutError:
        return {"status": "timeout", "detail": "Inspect Celery não respondeu em 5s"}


async def _check_google_sheets(
    credentials_path: str | None,
    spreadsheet_id: str | None,
) -> dict[str, Any]:
    if not credentials_path or not spreadsheet_id:
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
            client = GoogleSheetsClient(
                credentials_path=credentials_path,
                spreadsheet_id=spreadsheet_id,
            )
            client._ler_intervalo("Clientes!A1:A1")
            return {
                "status": "ok",
                "latency_ms": round((time.perf_counter() - t) * 1000, 2),
            }
        except Exception as exc:
            return {"status": "error", "detail": str(exc)}

    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_ping_sync),
            timeout=_CHECK_TIMEOUT + 5,
        )
    except TimeoutError:
        return {"status": "timeout", "detail": "Google Sheets não respondeu em 10s"}


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

_STATUS_ICON = {
    "ok": "✓",
    "degraded": "~",
    "skipped": "~",
    "timeout": "✗",
    "error": "✗",
}


async def run(output_json: bool) -> int:
    from shared.config.settings import settings

    t_total = time.perf_counter()

    pg, rd, claude, evolution, celery_w, sheets = await asyncio.gather(
        _check_postgresql(settings.DATABASE_URL),
        _check_redis(settings.REDIS_URL),
        _check_claude_api(settings.ANTHROPIC_API_KEY),
        _check_evolution_api(settings.EVOLUTION_API_URL, settings.EVOLUTION_API_KEY),
        _check_celery_workers(settings.CELERY_BROKER_URL),
        _check_google_sheets(
            settings.GOOGLE_CREDENTIALS_PATH, settings.GOOGLE_SHEETS_ID
        ),
    )

    checks: dict[str, dict[str, Any]] = {
        "postgresql": pg,
        "redis": rd,
        "claude_api": claude,
        "evolution_api": evolution,
        "celery_workers": celery_w,
        "google_sheets": sheets,
    }

    total_ms = round((time.perf_counter() - t_total) * 1000, 2)
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

    result = {"status": overall, "total_ms": total_ms, "checks": checks}

    if output_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"\n{'='*52}")
        print(f"  Health Check  —  {overall.upper()}  ({total_ms}ms)")
        print(f"{'='*52}")
        for name, info in checks.items():
            icon = _STATUS_ICON.get(info["status"], "?")
            latency = f" ({info['latency_ms']}ms)" if "latency_ms" in info else ""
            detail = f"  {info['detail']}" if info.get("detail") else ""
            print(f"  {icon}  {name:<18}  {info['status']}{latency}{detail}")
        print()

    return 0 if critical_ok else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Health check standalone dos serviços")
    parser.add_argument(
        "--json", action="store_true", help="Saída em JSON (para integração CI/CD)"
    )
    args = parser.parse_args()

    sys.exit(asyncio.run(run(output_json=args.json)))


if __name__ == "__main__":
    main()
