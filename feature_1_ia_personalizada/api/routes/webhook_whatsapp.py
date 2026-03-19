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
    enviar_boas_vindas_escritorio,
    processar_mensagem_recebida,
    processar_resposta_advogado,
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
        raise HTTPException(status_code=400, detail="Payload inválido ou não é JSON") from None

    event = body.get("event")
    instance_name = body.get("instance")

    # ----------------------------------------------------------------
    # connection.update — WhatsApp conectou → envia boas-vindas em lote
    # ----------------------------------------------------------------
    if event == "connection.update":
        state = body.get("data", {}).get("state", "")
        if state == "open" and instance_name:
            stmt_esc = select(Escritorio).where(
                Escritorio.webhook_whatsapp_instance == instance_name
            )
            escritorio = (await db.execute(stmt_esc)).scalars().first()
            if escritorio:
                enviar_boas_vindas_escritorio.delay(escritorio.id)
                logger.info(
                    "whatsapp_conectado_boas_vindas_agendadas",
                    instance_name=instance_name,
                    escritorio_id=escritorio.id,
                )
                return {"status": "boas_vindas_agendadas"}
        return {"status": "ignored", "reason": f"connection.update state={state!r}"}

    # Apenas processar mensagens novas
    if event != "messages.upsert":
        # Retornamos OK para a Evolution não ficar tentando reenviar indefinidamente eventos de status
        return {"status": "ignored", "reason": f"Event '{event}' not processing"}

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
    if not telefone_digitos:
        return {"status": "ignored", "reason": "Invalid phone format"}

    # Extrair conteúdo da mensagem
    msg_content: dict[str, Any] = (
        msg_obj.get("message", msg_obj) if isinstance(msg_obj.get("message", msg_obj), dict) else {}
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

    if not instance_name:
        logger.warning("webhook_sem_instancia")
        return {"status": "error", "reason": "Missing instance"}

    # 1. Puxar o Escritório correspondente a essa instância da Evolution
    stmt_esc = select(Escritorio).where(Escritorio.webhook_whatsapp_instance == instance_name)
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
        # Tentar verificar se é um ADVOGADO respondendo a uma escalação
        from shared.models.usuario import Usuario

        stmt_adv = select(Usuario).where(
            Usuario.whatsapp_numero == telefone_digitos,
            Usuario.escritorio_id == escritorio.id,
            Usuario.ativo == True,
            Usuario.escalacao_ativa == True,
        )
        advogado = (await db.execute(stmt_adv)).scalars().first()

        if advogado:
            processar_resposta_advogado.delay(
                id_escritorio=escritorio.id,
                id_advogado=advogado.id,
                texto_resposta=texto,
                msg_context=msg_content if isinstance(msg_content, dict) else {},
            )
            return {"status": "queued_escalation_reply"}

        logger.info(
            "webhook_numero_desconhecido",
            telefone=telefone_digitos,
            instance_name=instance_name,
        )
        return {"status": "ignored", "reason": "Client or Lawyer not registered"}

    # 3. Verificar se é resposta de pesquisa NPS (1-5)
    nps_processado = await _processar_resposta_nps(texto, cliente, escritorio, db)
    if nps_processado:
        _webhook_processing_time.observe(time.perf_counter() - _inicio)
        return {"status": "nps_registrado"}

    # 4. Disparar o Worker (Processamento via Celery assíncrono)
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

    _mensagens_recebidas.labels(escritorio_id=str(escritorio.id), tipo=tipo_mensagem).inc()
    _webhook_processing_time.observe(time.perf_counter() - _inicio)

    logger.info(
        "webhook_mensagem_enfileirada",
        cliente_id=cliente.id,
        escritorio_id=escritorio.id,
        tipo=tipo_mensagem,
    )

    return {"status": "queued"}


async def _processar_resposta_nps(
    texto: str,
    cliente: Cliente,
    escritorio: Escritorio,
    db: AsyncSession,
) -> bool:
    """
    Verifica se o cliente estava aguardando NPS e a mensagem é um número 1-5.
    Retorna True se a mensagem foi identificada como resposta NPS e processada,
    para que o webhook não a encaminhe à IA.
    """
    # Só processa se for dígito 1-5 isolado
    texto_limpo = texto.strip()
    if texto_limpo not in {"1", "2", "3", "4", "5"}:
        return False

    nota = int(texto_limpo)

    # Busca última interação com aguardando_nps=True para este cliente
    from shared.models.interacao import Interacao as InteracaoModel

    stmt = (
        select(InteracaoModel)
        .where(
            InteracaoModel.cliente_id == cliente.id,
            InteracaoModel.metadata_json["aguardando_nps"] == True,  # noqa: E712
        )
        .order_by(InteracaoModel.created_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    interacao_nps = result.scalar_one_or_none()

    if not interacao_nps:
        # Não havia NPS pendente — mensagem "1-5" tratada como texto normal
        return False

    # Registra nota e limpa flag
    meta = dict(interacao_nps.metadata_json or {})
    meta.pop("aguardando_nps", None)
    interacao_nps.satisfacao = nota
    interacao_nps.metadata_json = meta
    await db.commit()

    logger.info(
        "nps_registrado",
        cliente_id=cliente.id,
        escritorio_id=escritorio.id,
        nota=nota,
    )

    # Envia agradecimento e, se NPS baixo, alerta os advogados
    from feature_1_ia_personalizada.services.messaging.evolution_client import EvolutionClient
    from shared.config.settings import settings

    evo = EvolutionClient(
        base_url=settings.EVOLUTION_API_URL,
        api_key=settings.EVOLUTION_API_KEY,
    )
    try:
        agradecimento = (
            f"Obrigado pela avaliação, {cliente.nome}! "
            "Seu feedback é muito importante para continuarmos melhorando o atendimento. 🙏"
        )
        await evo.enviar_texto(
            escritorio.webhook_whatsapp_instance,
            cliente.telefone_whatsapp,
            agradecimento,
        )

        if nota <= 3:
            from shared.models.usuario import Usuario

            stmt_adv = select(Usuario).where(
                Usuario.escritorio_id == escritorio.id,
                Usuario.ativo == True,  # noqa: E712
                Usuario.escalacao_ativa == True,  # noqa: E712
                Usuario.whatsapp_numero.isnot(None),
            )
            advogados = (await db.execute(stmt_adv)).scalars().all()

            alerta = (
                f"⚠️ *ALERTA — NPS BAIXO*\n"
                f"Cliente: {cliente.nome}\n"
                f"Nota: {nota}/5\n\n"
                f"Recomendado entrar em contato para verificar a satisfação."
            )
            for adv in advogados:
                await evo.enviar_texto(
                    escritorio.webhook_whatsapp_instance,
                    adv.whatsapp_numero,
                    alerta,
                )
            logger.info(
                "nps_alerta_enviado",
                cliente_id=cliente.id,
                nota=nota,
                advogados_alertados=len(advogados),
            )
    except Exception as e:
        logger.error("nps_envio_mensagem_falhou", cliente_id=cliente.id, erro=str(e))
    finally:
        await evo.close()

    return True
