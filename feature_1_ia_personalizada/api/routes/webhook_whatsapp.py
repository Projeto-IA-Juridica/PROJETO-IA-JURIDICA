from fastapi import APIRouter

router = APIRouter(prefix="/webhook/whatsapp", tags=["Webhooks Evolution"])

@router.post("")
async def receive_message():
    return {"status": "received"}
