import hmac
import re
import time
from typing import Any

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from prometheus_client import Counter, Histogram
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from feature_1_ia_personalizada.workers.send_notifications import (
    processar_mensagem_recebida,
)
from shared.config.settings import settings
from shared.database.session import get_db
from shared.models.cliente import Cliente
from shared.models.escritorio import Escritorio

logger = structlog.get_logger(__name__)

_mensagens_recebidas = Counter(
    "whatsapp_messages_received_total",
    "Total de mensagens WhatsApp recebidas via webhook",
    labelnames=["escritorio_id", "tipo"],
)
_webhook_processing_time = Histogram(
    "webhook_processing_time_seconds",
    "Tempo de processamento do webhook WhatsApp (até enfileirar no Celery)",
)

router = APIRouter(prefix="/webhook/whatsapp", tags=["Webhooks Evolution"])


@router.post("")
async def receive_message(
    request: Request,
    apikey: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """
    Recebe os eventos da Evolution API.
    Filtra as mensagens recebidas de clientes (messages.upsert),
    localiza o Escritório e o Cliente correspondentes no banco de dados,
    e envia a tarefa pesada de I.A. para a fila do Celery.
    """
    if not apikey or not hmac.compare_digest(apikey, settings.EVOLUTION_API_KEY):
        logger.warning("webhook_auth_failed", apikey_received=bool(apikey))
        raise HTTPException(status_code=401, detail="Unauthorized")

    _inicio = time.perf_counter()
    try:
        body = await request.json()
    except Exception:
        # Pydantic/FastAPI request parsing fallbacks
        raise HTTPException(
            status_code=400, detail="Payload inválido ou não é JSON"
        ) from None

    # Apenas processar mensagens novas
    event = body.get("event")
    if event != "messages.upsert":
        # Retornamos OK para a Evolution não ficar tentando reenviar indefinidamente eventos de status
        return {"status": "ignored", "reason": f"Event '{event}' not processing"}

    raw_data: Any = body.get("data", {})
    data: dict[str, Any] = raw_data if isinstance(raw_data, dict) else {}

    # Se for lista (às vezes a wwebjs/Evolution envia array na upsert)
    messages: Any = (
        data.get("message", raw_data) if isinstance(raw_data, dict) else raw_data
    )
    if isinstance(messages, list):
        msg_obj: dict[str, Any] = messages[0] if messages else {}
    else:
        msg_obj = messages if isinstance(messages, dict) else {}

    # Estrutura típica da chave
    key: dict[str, Any] = (
        msg_obj.get("key", {}) if "key" in msg_obj else data.get("key", {})
    )
    from_me = key.get("fromMe", False)

    # Não processa mensagens que nós mesmos mandamos (loop infinito)
    if from_me:
        return {"status": "ignored", "reason": "Message from self"}

    remote_jid = key.get("remoteJid", "")
    if "@g.us" in remote_jid:
        # Ignorar mensagens de grupos
        return {"status": "ignored", "reason": "Group message"}

    # Extrair telefone puro
    telefone_str = remote_jid.split("@")[0]
    telefone_digitos = re.sub(r"\D", "", telefone_str)
    if not telefone_digitos:
        return {"status": "ignored", "reason": "Invalid phone format"}

    # Extrair conteúdo da mensagem
    msg_content: dict[str, Any] = (
        msg_obj.get("message", msg_obj)
        if isinstance(msg_obj.get("message", msg_obj), dict)
        else {}
    )

    # Pega texto simples ou caption de mídia
    texto = ""
    if "conversation" in msg_content:
        texto = str(msg_content["conversation"])
    elif "extendedTextMessage" in msg_content:
        ext_text = msg_content["extendedTextMessage"]
        if isinstance(ext_text, dict):
            texto = str(ext_text.get("text", ""))
    elif "audioMessage" in msg_content:
        texto = "[ÁUDIO NÃO PROCESSADO PELA ROTA AINDA]"  # Futuro: processamento de áudio Whisper
    elif "imageMessage" in msg_content:
        img_msg = msg_content["imageMessage"]
        if isinstance(img_msg, dict):
            texto = str(img_msg.get("caption", "[IMAGEM]"))

    if not texto.strip():
        # Ignora mensagens vazias ou de sistema sem texto aparente
        return {"status": "ignored", "reason": "Empty text"}

    instance_name = body.get("instance")

    if not instance_name:
        logger.warning("webhook_sem_instancia")
        return {"status": "error", "reason": "Missing instance"}

    # 1. Puxar o Escritório correspondente a essa instância da Evolution
    stmt_esc = select(Escritorio).where(
        Escritorio.webhook_whatsapp_instance == instance_name
    )
    escritorio = (await db.execute(stmt_esc)).scalars().first()

    if not escritorio:
        logger.warning("webhook_instancia_nao_vinculada", instance_name=instance_name)
        return {"status": "ignored", "reason": "Instance not found in DB"}

    # 2. Puxar o Cliente correspondente a esse telefone dentro do escritório
    stmt_cli = select(Cliente).where(
        Cliente.telefone_whatsapp == telefone_digitos,
        Cliente.escritorio_id == escritorio.id,
    )
    cliente = (await db.execute(stmt_cli)).scalars().first()

    if not cliente:
        logger.info(
            "webhook_numero_desconhecido",
            telefone=telefone_digitos,
            instance_name=instance_name,
        )
        return {"status": "ignored", "reason": "Client not registered"}

    # 3. Disparar o Worker (Processamento via Celery assíncrono)
    # A IA fará todo o trabalho pesado longe da Main Thread do FastAPI
    tipo_mensagem = "texto"
    if "audioMessage" in (msg_content if isinstance(msg_content, dict) else {}):
        tipo_mensagem = "audio"
    elif "imageMessage" in (msg_content if isinstance(msg_content, dict) else {}):
        tipo_mensagem = "imagem"

    processar_mensagem_recebida.delay(
        id_escritorio=escritorio.id,
        id_cliente=cliente.id,
        mensagem=texto,
        tipo=tipo_mensagem,
    )

    _mensagens_recebidas.labels(
        escritorio_id=str(escritorio.id), tipo=tipo_mensagem
    ).inc()
    _webhook_processing_time.observe(time.perf_counter() - _inicio)

    logger.info(
        "webhook_mensagem_enfileirada",
        cliente_id=cliente.id,
        escritorio_id=escritorio.id,
        tipo=tipo_mensagem,
    )

    return {"status": "queued"}
