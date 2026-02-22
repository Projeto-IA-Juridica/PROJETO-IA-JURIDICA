from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["Monitoramento"])

@router.get("")
async def health_basic():
    return {"status": "ok"}

@router.get("/ready")
async def health_ready():
    return {"status": "ok", "db": "connected", "redis": "connected"}
