# webhook_whatsapp.py

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from feature_1_ia_personalizada.workers.send_notifications import (
    processar_mensagem_recebida,
)

router = APIRouter()


class WebhookWhatsAppEntrada(BaseModel):
    escritorio_id: int
    cliente_id: int
    mensagem: str
    tipo: str


@router.post("/webhook/whatsapp")
async def webhook_whatsapp(payload: WebhookWhatsAppEntrada, request: Request):
    if not payload.mensagem or not payload.tipo:
        raise HTTPException(status_code=400, detail="Payload inválido")

    processar_mensagem_recebida.delay(
        payload.escritorio_id,
        payload.cliente_id,
        payload.mensagem,
        payload.tipo,
    )

    return {"status": "ok"}
