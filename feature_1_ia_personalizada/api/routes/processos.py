from fastapi import APIRouter

router = APIRouter(prefix="/processos", tags=["Processos Jurídicos"])

@router.get("")
async def list_processos():
    return {"message": "Not implemented yet"}
