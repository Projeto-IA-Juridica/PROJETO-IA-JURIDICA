import logging
import re
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database.session import get_db
from shared.models.escritorio import Escritorio
from shared.models.cliente import Cliente
from feature_1_ia_personalizada.workers.send_notifications import processar_mensagem_recebida

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook/whatsapp", tags=["Webhooks Evolution"])

@router.post("")
async def receive_message(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Recebe os eventos da Evolution API.
    Filtra as mensagens recebidas de clientes (messages.upsert),
    localiza o Escritório e o Cliente correspondentes no banco de dados,
    e envia a tarefa pesada de I.A. para a fila do Celery.
    """
    try:
        body = await request.json()
    except Exception:
        # Pydantic/FastAPI request parsing fallbacks
        raise HTTPException(status_code=400, detail="Payload inválido ou não é JSON")

    # Apenas processar mensagens novas
    event = body.get("event")
    if event != "messages.upsert":
        # Retornamos OK para a Evolution não ficar tentando reenviar indefinidamente eventos de status
        return {"status": "ignored", "reason": f"Event '{event}' not processing"}

    from typing import Any
    raw_data: Any = body.get("data", {})
    data: dict[str, Any] = raw_data if isinstance(raw_data, dict) else {}
    
    # Se for lista (às vezes a wwebjs/Evolution envia array na upsert)
    messages: Any = data.get("message", raw_data) if isinstance(raw_data, dict) else raw_data
    if isinstance(messages, list):
        msg_obj: dict[str, Any] = messages[0] if messages else {}
    else:
        msg_obj = messages if isinstance(messages, dict) else {}

    # Estrutura típica da chave
    key: dict[str, Any] = msg_obj.get("key", {}) if "key" in msg_obj else data.get("key", {})
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

    # Extrair conteúdo da mensagem
    msg_content: dict[str, Any] = msg_obj.get("message", msg_obj) if isinstance(msg_obj.get("message", msg_obj), dict) else {}
    
    # Pega texto simples ou caption de mídia
    texto = ""
    if "conversation" in msg_content:
        texto = str(msg_content["conversation"])
    elif "extendedTextMessage" in msg_content:
        ext_text = msg_content["extendedTextMessage"]
        if isinstance(ext_text, dict):
            texto = str(ext_text.get("text", ""))
    elif "audioMessage" in msg_content:
        texto = "[ÁUDIO NÃO PROCESSADO PELA ROTA AINDA]" # Futuro: processamento de áudio Whisper
    elif "imageMessage" in msg_content:
        img_msg = msg_content["imageMessage"]
        if isinstance(img_msg, dict):
            texto = str(img_msg.get("caption", "[IMAGEM]"))

    if not texto.strip():
        # Ignora mensagens vazias ou de sistema sem texto aparente
        return {"status": "ignored", "reason": "Empty text"}

    instance_name = body.get("instance")
    
    if not instance_name:
         logger.warning("Webhook Evolution sem nome de instância.")
         return {"status": "error", "reason": "Missing instance"}
         
    # 1. Puxar o Escritório correspondente a essa instância da Evolution
    stmt_esc = select(Escritorio).where(Escritorio.webhook_whatsapp_instance == instance_name)
    escritorio = (await db.execute(stmt_esc)).scalars().first()
    
    if not escritorio:
        logger.warning(f"Instância '{instance_name}' não vinculada a nenhum escritório.")
        # Retorna 200 pra Evolution parar de tentar, mas avisa erro internamente
        return {"status": "ignored", "reason": "Instance not found in DB"}

    # 2. Puxar o Cliente correspondente a esse telefone dentro do escritório
    stmt_cli = select(Cliente).where(
        Cliente.telefone_whatsapp == telefone_digitos,
        Cliente.escritorio_id == escritorio.id
    )
    cliente = (await db.execute(stmt_cli)).scalars().first()
    
    if not cliente:
         # TODO: Em um sistema real, poderíamos criar o Lead/Cliente automaticamente aqui.
         logger.info(f"Mensagem recebida de número desconhecido: {telefone_digitos} para a instância {instance_name}")
         return {"status": "ignored", "reason": "Client not registered"}

    # 3. Disparar o Worker (Processamento via Celery assíncrono)
    # A IA fará todo o trabalho pesado longe da Main Thread do FastAPI
    processar_mensagem_recebida.delay(
        id_escritorio=escritorio.id,
        id_cliente=cliente.id,
        mensagem=texto,
        tipo="texto"  # Evoluir para audio, imagem depois
    )

    logger.info(f"Mensagem do cliente {cliente.id} enfileirada no Celery.")

    return {"status": "queued"}

