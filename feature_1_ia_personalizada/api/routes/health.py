import time
from fastapi import APIRouter, Depends, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as redis

from shared.database.session import get_db
from shared.config.settings import settings

router = APIRouter(prefix="/health", tags=["Monitoramento"])

@router.get("")
async def health_basic():
    """Health check superfícial (apenas verifica se a API está no ar)."""
    return {"status": "ok", "service": "concierge-juridico"}

@router.get("/ready")
async def health_ready(db: AsyncSession = Depends(get_db)):
    """
    Verifica se a API está pronta e consegue se comunicar
    com o Banco de Dados (PostgreSQL) e o Cache/Rate Limit (Redis).
    """
    health_status = {"status": "ok", "db": "unknown", "redis": "unknown"}
    is_ready = True
    
    # 1. Testar o Banco de Dados (PostgreSQL)
    try:
        start_time = time.time()
        await db.execute(text("SELECT 1"))
        db_ping = round((time.time() - start_time) * 1000, 2)
        health_status["db"] = f"connected ({db_ping} ms)"
    except Exception as e:
        health_status["db"] = f"error: {str(e)}"
        health_status["status"] = "error"
        is_ready = False

    # 2. Testar o Redis
    try:
        start_time = time.time()
        # Conectando usando o URL do .env
        r = redis.from_url(settings.REDIS_URL, decode_responses=True)
        await r.ping()
        redis_ping = round((time.time() - start_time) * 1000, 2)
        health_status["redis"] = f"connected ({redis_ping} ms)"
        await r.aclose()  # Fecha a conexão após o ping
    except Exception as e:
        health_status["redis"] = f"error: {str(e)}"
        health_status["status"] = "error"
        is_ready = False

    if not is_ready:
        # Retorna 503 Service Unavailable se alguma dependência falhar
        # Isso é útil para orquestradores como Kubernetes ou Docker Swarm
        from fastapi import HTTPException
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, 
            detail=health_status
        )

    return health_status

@router.get("/detailed")
async def health_detailed(db: AsyncSession = Depends(get_db)):
    """
    Health check mais exaustivo (Fase 3+).
    Aqui testaremos conexões com APIs externas (Claude, Evolution, Jusbrasil).
    """
    # Por ora, retorna a mesma coisa do /ready
    return await health_ready(db)
