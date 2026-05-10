from __future__ import annotations

import asyncio
import os
from datetime import datetime, time, timedelta, timezone
from typing import Any

import redis
import structlog
from celery import shared_task

from feature_1_ia_personalizada.services.messaging.evolution_client import (
    EvolutionClient,
)
from feature_1_ia_personalizada.services.messaging.whatsapp import (
    SQLWhatsAppRepository,
    WhatsAppService,
)
from feature_1_ia_personalizada.workers.celery_app import DLQTask
from shared.config.settings import settings
from shared.database.worker_queries import (
    insert_interacao,
    query_clientes_ativos_por_escritorio,
    query_clientes_para_pesquisa,
    query_processo_e_cliente,
    query_processos_sem_movimentacao,
)

logger = structlog.get_logger(__name__)


# CONFIGURAÇÕES


FUSO_HORARIO_PADRAO = int(os.getenv("FUSO_HORARIO_PADRAO", "-3"))
HORA_INICIO_ENVIO = int(os.getenv("HORA_INICIO_ENVIO", "8"))
HORA_FIM_ENVIO = int(os.getenv("HORA_FIM_ENVIO", "20"))

URL_REDIS = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# ✅ CORREÇÃO: conexão lazy — criada apenas na primeira chamada,
# não no momento em que o módulo é importado.
_cliente_redis: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _cliente_redis
    if _cliente_redis is None:
        _cliente_redis = redis.Redis.from_url(URL_REDIS, decode_responses=True)
    assert _cliente_redis is not None
    return _cliente_redis


TEMPO_30_DIAS = 30 * 24 * 60 * 60
TEMPO_32_DIAS = 32 * 24 * 60 * 60
TEMPO_5_MINUTOS = 5 * 60


# MENSAGENS PADRÃO


MENSAGEM_NOVO_ANDAMENTO = (
    "Atualização do seu processo:\n\n"
    "{descricao_andamento}\n\n"
    "Se desejar, posso explicar em linguagem mais simples."
)

MENSAGEM_SEM_MOVIMENTACAO = (
    "Seu processo está sem movimentação nos últimos 30 dias.\n\n"
    "Isso é comum e não significa necessariamente um problema."
)

MENSAGEM_PESQUISA_SATISFACAO = (
    "De 1 a 5, como você avalia nosso atendimento este mês?\nResponda apenas com um número."
)

MENSAGEM_ERRO_PADRAO = (
    "No momento não consegui processar sua mensagem. Nossa equipe será notificada."
)

MENSAGEM_BOAS_VINDAS = (
    "Olá, {nome}! 👋 Seja bem-vindo(a).\n\n"
    "Estou aqui para facilitar o acompanhamento do seu processo e esclarecer dúvidas rápidas.\n\n"
    "⚠️ _As informações enviadas por aqui não substituem a orientação jurídica formal do seu advogado._\n\n"
    "Quando precisar, é só chamar! ⚖️"
)


# FUNÇÕES AUXILIARES


def _get_whatsapp_service() -> WhatsAppService:
    client = EvolutionClient(settings.EVOLUTION_API_URL, settings.EVOLUTION_API_KEY)
    repo = SQLWhatsAppRepository()
    return WhatsAppService(evolution_client=client, repositorio=repo)


def agora_local() -> datetime:
    fuso = timezone(timedelta(hours=FUSO_HORARIO_PADRAO))
    return datetime.now(tz=fuso)


def horario_permitido(data_hora: datetime) -> bool:
    inicio = time(HORA_INICIO_ENVIO, 0)
    fim = time(HORA_FIM_ENVIO, 0)
    return inicio <= data_hora.timetz().replace(tzinfo=None) < fim


def segundos_ate_proximo_horario(data_hora: datetime) -> int:
    fuso = data_hora.tzinfo
    inicio_hoje = datetime(
        data_hora.year,
        data_hora.month,
        data_hora.day,
        HORA_INICIO_ENVIO,
        0,
        tzinfo=fuso,
    )

    if data_hora < inicio_hoje:
        return int((inicio_hoje - data_hora).total_seconds())

    amanha = data_hora + timedelta(days=1)
    inicio_amanha = datetime(
        amanha.year, amanha.month, amanha.day, HORA_INICIO_ENVIO, 0, tzinfo=fuso
    )
    return int((inicio_amanha - data_hora).total_seconds())


def chave_limite(prefixo: str, *valores: Any) -> str:
    return prefixo + ":" + ":".join(str(v) for v in valores)


def registrar_envio_com_validade(chave: str, tempo_segundos: int) -> None:
    get_redis().set(chave, "1", ex=tempo_segundos)


def envio_recente(chave: str) -> bool:
    return bool(get_redis().exists(chave) == 1)


def adquirir_bloqueio(chave: str, tempo_segundos: int) -> bool:
    return bool(get_redis().set(chave, "1", nx=True, ex=tempo_segundos))


def buscar_processo_e_cliente(id_processo: int):
    return query_processo_e_cliente(id_processo)


def buscar_processos_sem_movimentacao():
    return query_processos_sem_movimentacao()


def buscar_clientes_para_pesquisa():
    return query_clientes_para_pesquisa()


def buscar_clientes_ativos_por_escritorio(escritorio_id: int):
    return query_clientes_ativos_por_escritorio(escritorio_id)


def registrar_interacao(id_cliente: int, id_processo: int | None, tipo: str, dados: dict):
    insert_interacao(
        id_cliente=id_cliente,
        id_processo=id_processo,
        tipo=tipo,
        metadata_json={"tipo_atividade": tipo, **dados},
    )


# TASKS


@shared_task(
    bind=True,
    base=DLQTask,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    max_retries=5,
)
def enviar_notificacao_andamento(self, id_processo: int, descricao_andamento: str):

    momento = agora_local()

    if not horario_permitido(momento):
        espera = segundos_ate_proximo_horario(momento)
        raise self.retry(countdown=espera)

    chave_bloqueio = chave_limite("bloqueio_andamento", id_processo, hash(descricao_andamento))
    if not adquirir_bloqueio(chave_bloqueio, TEMPO_5_MINUTOS):
        return {"status": "ignorado"}

    service = _get_whatsapp_service()

    async def _enviar():
        resp = await service.enviar_notificacao_andamento(id_processo, descricao_andamento)
        await service.evolution_client.close()
        return resp

    resultado_envio = asyncio.run(_enviar())

    return {"status": "processado", "resultado": resultado_envio}


@shared_task(bind=True)
def enviar_lote_sem_movimentacao(self):

    momento = agora_local()

    if not horario_permitido(momento):
        espera = segundos_ate_proximo_horario(momento)
        raise self.retry(countdown=espera)

    processos = buscar_processos_sem_movimentacao()
    service = _get_whatsapp_service()

    async def _enviar_lote() -> int:
        count = 0
        for processo in processos:
            chave = chave_limite("limite_sem_movimentacao", processo.id)

            if envio_recente(chave):
                continue

            await service.enviar_sem_movimentacao(processo.id)
            registrar_envio_com_validade(chave, TEMPO_30_DIAS)
            count += 1
        await service.evolution_client.close()
        return count

    enviados = asyncio.run(_enviar_lote())
    return {"enviados": enviados}


@shared_task(bind=True)
def enviar_pesquisa_satisfacao(self):

    momento = agora_local()

    if not horario_permitido(momento):
        espera = segundos_ate_proximo_horario(momento)
        raise self.retry(countdown=espera)

    clientes = buscar_clientes_para_pesquisa()

    mes_referencia = momento.strftime("%Y-%m")
    service = _get_whatsapp_service()

    async def _enviar_lote() -> int:
        count = 0
        for cliente in clientes:
            chave = chave_limite("limite_pesquisa", cliente.id, mes_referencia)

            if envio_recente(chave):
                continue

            # Assuming cliente record has escritorio_id
            await service.enviar_pesquisa_satisfacao(cliente.escritorio_id, cliente.id)
            registrar_envio_com_validade(chave, TEMPO_32_DIAS)
            count += 1
        await service.evolution_client.close()
        return count

    enviados = asyncio.run(_enviar_lote())
    return {"enviados": enviados}


@shared_task(
    bind=True,
    base=DLQTask,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    max_retries=3,
)
def processar_mensagem_recebida(
    self,
    id_escritorio: int,
    id_cliente: int,
    mensagem: str,
    tipo: str,
    instance_nome: str | None = None,
    audio_message_id: str | None = None,
):
    # Import lazy: evita importar asyncpg e SQLAlchemy no boot do módulo.
    # O orchestrator já envia a resposta via EvolutionClient em _node_enviar_resposta,
    # portanto esta task NÃO deve reenviar pelo WhatsApp.
    from feature_1_ia_personalizada.services.ai.orchestrator import (
        executar_fluxo_orquestrador,
    )

    # --- Transcrição de áudio (Whisper) ---
    # Quando o webhook identifica um audioMessage, passa tipo="audio" e audio_message_id.
    # Aqui baixamos o OGG da Evolution API, convertemos para MP3 e transcrevemos.
    # Se a transcrição falhar, substituímos por mensagem de fallback amigável para
    # que o orchestrador informe o cliente do problema sem crashar o fluxo.
    if tipo == "audio" and audio_message_id and instance_nome:
        async def _transcrever() -> str:
            from feature_1_ia_personalizada.services.messaging.evolution_client import (
                EvolutionClient,
            )
            from shared.utils.audio_handler import (
                converter_ogg_para_mp3,
                transcrever_audio,
                validar_duracao_audio,
            )

            evo = EvolutionClient(settings.EVOLUTION_API_URL, settings.EVOLUTION_API_KEY)
            try:
                ogg_bytes = await evo.baixar_media(instance_nome, audio_message_id)
                validar_duracao_audio(ogg_bytes)
                mp3_bytes = converter_ogg_para_mp3(ogg_bytes)
                return await transcrever_audio(mp3_bytes)
            finally:
                await evo.close()

        try:
            from feature_1_ia_personalizada.api.routes.metrics import audio_transcritos_total as _ctr_audio
        except Exception:
            _ctr_audio = None  # métricas opcionais

        try:
            mensagem = asyncio.run(_transcrever())
            tipo = "texto"  # orchestrador trata como texto após transcrição
            logger.info(
                "audio.transcricao_ok",
                id_cliente=id_cliente,
                chars=len(mensagem),
            )
            if _ctr_audio:
                _ctr_audio.labels(resultado="sucesso").inc()
        except ValueError as exc:
            # Duração excedida, áudio corrompido ou timeout Whisper
            logger.warning("audio.transcricao_falhou", id_cliente=id_cliente, erro=str(exc))
            mensagem = (
                "[Recebi um áudio, mas não consegui processá-lo. "
                f"Motivo: {exc}. Por favor, tente enviar uma mensagem de texto.]"
            )
            tipo = "texto"
            _resultado_audio = "erro_duracao" if "longo" in str(exc).lower() or "máximo" in str(exc).lower() else "erro_whisper"
            if _ctr_audio:
                _ctr_audio.labels(resultado=_resultado_audio).inc()
        except Exception as exc:
            logger.error("audio.transcricao_erro_inesperado", id_cliente=id_cliente, erro=str(exc))
            mensagem = (
                "[Recebi um áudio, mas ocorreu um erro interno ao processá-lo. "
                "Por favor, envie uma mensagem de texto.]"
            )
            tipo = "texto"
            if _ctr_audio:
                _ctr_audio.labels(resultado="erro_inesperado").inc()

    try:
        resultado = executar_fluxo_orquestrador(
            id_escritorio=id_escritorio,
            id_cliente=id_cliente,
            mensagem=mensagem,
            tipo=tipo,
        )

        registrar_interacao(
            id_cliente=id_cliente,
            id_processo=None,
            tipo="mensagem_processada",
            dados=resultado,
        )

        # Invalida cache de analytics para que o dashboard reflita a nova interação
        try:
            r = get_redis()
            for dias in (7, 30, 90):
                r.delete(f"analytics:{id_escritorio}:{dias}")
        except Exception:
            pass  # cache opcional — nunca bloqueia a task

        return {"status": "ok"}

    except Exception as erro:
        registrar_interacao(
            id_cliente=id_cliente,
            id_processo=None,
            tipo="erro_processamento",
            dados={"erro": str(erro)},
        )

        raise


@shared_task(bind=True)
def enviar_boas_vindas_escritorio(self, escritorio_id: int):
    """
    Disparada quando o WhatsApp do escritório conecta (evento connection.update/open).

    Envia mensagem de boas-vindas para todos os clientes ativos do escritório.
    Usa Redis para garantir que cada cliente receba no máximo 1 mensagem
    (TTL de 90 dias — evita re-envio se o advogado reconectar o WhatsApp).
    """
    TTL_BOAS_VINDAS = 90 * 24 * 60 * 60  # 90 dias

    clientes = buscar_clientes_ativos_por_escritorio(escritorio_id)
    service = _get_whatsapp_service()

    async def _enviar_lote() -> tuple[int, int]:
        c_enviados: int = 0
        c_ignorados: int = 0
        for cliente in clientes:
            chave = chave_limite("boas_vindas", escritorio_id, cliente.id)

            if envio_recente(chave):
                c_ignorados += 1
                continue

            try:
                await service.enviar_boas_vindas(escritorio_id, cliente.id)
                registrar_envio_com_validade(chave, TTL_BOAS_VINDAS)
                c_enviados += 1
            except Exception as exc:
                logger.error(
                    "erro_boas_vindas_individual",
                    escritorio_id=escritorio_id,
                    cliente_id=cliente.id,
                    erro=str(exc),
                )
        await service.evolution_client.close()
        return c_enviados, c_ignorados

    enviados, ignorados = asyncio.run(_enviar_lote())

    logger.info(
        "boas_vindas_escritorio_finalizadas",
        escritorio_id=escritorio_id,
        sucesso=enviados,
        ignorados=ignorados,
    )

    return {"enviados": enviados, "ignorados": ignorados}


@shared_task(
    bind=True,
    base=DLQTask,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    max_retries=3,
)
def processar_resposta_advogado(
    self, id_escritorio: int, id_advogado: int, texto_resposta: str, msg_context: dict
):
    """
    Processa a resposta de um advogado a uma escalação e envia ao cliente final.
    """
    from shared.database.connection import async_session_factory
    from sqlalchemy import select
    from shared.models.interacao import Interacao

    async def _processar():
        async with async_session_factory() as session:
            interacao_id = None
            import re
            
            # Buscar no quoted message
            texto_citado = ""
            if "extendedTextMessage" in msg_context:
                ctx_info = msg_context.get("extendedTextMessage", {}).get("contextInfo", {})
                quoted = ctx_info.get("quotedMessage", {})
                if "conversation" in quoted:
                    texto_citado = quoted["conversation"]
                elif "extendedTextMessage" in quoted:
                    texto_citado = quoted.get("extendedTextMessage", {}).get("text", "")

            if texto_citado:
                match = re.search(r"ID:\s*#(\d+)", texto_citado)
                if match:
                    interacao_id = int(match.group(1))

            stmt = select(Interacao).where(
                Interacao.escritorio_id == id_escritorio,
                Interacao.tipo == "escalacao",
            ).order_by(Interacao.id.desc()).limit(20)
            
            result = await session.execute(stmt)
            interacoes_recentes = result.scalars().all()
            
            interacao_alvo = None
            if interacao_id:
                for i in interacoes_recentes:
                    meta_i = i.metadata_json or {}
                    if i.id == interacao_id and meta_i.get("escalacao", {}).get("status") == "pendente":
                        interacao_alvo = i
                        break

            if not interacao_alvo:
                # Fallback: pegar pendente mais recente
                for i in interacoes_recentes:
                    meta_esc = (i.metadata_json or {}).get("escalacao", {})
                    if meta_esc.get("status") == "pendente" and id_advogado in meta_esc.get("advogados_notificados", []):
                        interacao_alvo = i
                        break

            if not interacao_alvo:
                logger.warning("nenhuma_escalacao_pendente_encontrada", advogado_id=id_advogado)
                return

            # Atualizar o status da escalação
            meta = dict(interacao_alvo.metadata_json or {})
            esc_meta = dict(meta.get("escalacao", {}))
            esc_meta["status"] = "respondido"
            esc_meta["advogado_responsavel_id"] = id_advogado
            esc_meta["resposta_advogado"] = texto_resposta
            meta["escalacao"] = esc_meta
            
            interacao_alvo.metadata_json = meta
            
            # Analisar a resposta do advogado
            texto_limpo = texto_resposta.strip().lower()
            if texto_limpo in ["ok", "aprovado", "aprovar", "sim", "pode enviar"]:
                resposta_final = esc_meta.get("sugestao_resposta", "")
            else:
                resposta_final = texto_resposta
                
            service = _get_whatsapp_service()
            await service.enviar_mensagem(id_escritorio, interacao_alvo.cliente_id, resposta_final)
            
            await session.commit()
            logger.info("escalacao_resolvida", interacao_id=interacao_alvo.id, advogado_id=id_advogado)
            await service.evolution_client.close()

    asyncio.run(_processar())
    return {"status": "processado"}

