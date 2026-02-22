from fastapi import APIRouter

router = APIRouter(prefix="/chat", tags=["Histórico e Chat"])

@router.get("/history/{cliente_id}")
async def get_history(cliente_id: int):
    return {"message": "Not implemented yet"}
