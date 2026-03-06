from __future__ import annotations

import os
from datetime import datetime, time, timedelta, timezone
from typing import Any

import redis
import structlog
from celery import shared_task

from shared.database.worker_queries import (
    enviar_mensagem_whatsapp,
    insert_interacao,
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
cliente_redis = redis.Redis.from_url(URL_REDIS, decode_responses=True)

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
    "De 1 a 5, como você avalia nosso atendimento este mês?\n"
    "Responda apenas com um número."
)

MENSAGEM_ERRO_PADRAO = (
    "No momento não consegui processar sua mensagem. " "Nossa equipe será notificada."
)


# FUNÇÕES AUXILIARES


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


def registrar_envio_com_validade(chave: str, tempo_segundos: int):
    cliente_redis.set(chave, "1", ex=tempo_segundos)


def envio_recente(chave: str) -> bool:
    return cliente_redis.exists(chave) == 1


def adquirir_bloqueio(chave: str, tempo_segundos: int) -> bool:
    return bool(cliente_redis.set(chave, "1", nx=True, ex=tempo_segundos))


def buscar_processo_e_cliente(id_processo: int):
    return query_processo_e_cliente(id_processo)


def buscar_processos_sem_movimentacao():
    return query_processos_sem_movimentacao()


def buscar_clientes_para_pesquisa():
    return query_clientes_para_pesquisa()


def registrar_interacao(
    id_cliente: int, id_processo: int | None, tipo: str, dados: dict
):
    insert_interacao(
        id_cliente=id_cliente,
        id_processo=id_processo,
        tipo=tipo,
        metadata_json={"tipo_atividade": tipo, **dados},
    )


# TASKS


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 5},
)
def enviar_notificacao_andamento(self, id_processo: int, descricao_andamento: str):

    momento = agora_local()

    if not horario_permitido(momento):
        espera = segundos_ate_proximo_horario(momento)
        raise self.retry(countdown=espera)

    chave_bloqueio = chave_limite(
        "bloqueio_andamento", id_processo, hash(descricao_andamento)
    )
    if not adquirir_bloqueio(chave_bloqueio, TEMPO_5_MINUTOS):
        return {"status": "ignorado"}

    resultado = buscar_processo_e_cliente(id_processo)
    if resultado is None:
        return {"status": "processo_nao_encontrado", "id_processo": id_processo}
    processo, cliente = resultado

    mensagem = MENSAGEM_NOVO_ANDAMENTO.format(
        descricao_andamento=descricao_andamento.strip()
    )

    enviar_mensagem_whatsapp(cliente.id, cliente.telefone, mensagem)

    registrar_interacao(
        id_cliente=cliente.id,
        id_processo=processo.id,
        tipo="novo_andamento",
        dados={"descricao": descricao_andamento},
    )

    return {"status": "enviado"}


@shared_task(bind=True)
def enviar_lote_sem_movimentacao(self):

    momento = agora_local()

    if not horario_permitido(momento):
        espera = segundos_ate_proximo_horario(momento)
        raise self.retry(countdown=espera)

    processos = buscar_processos_sem_movimentacao()

    enviados = 0

    for processo in processos:
        chave = chave_limite("limite_sem_movimentacao", processo.id)

        if envio_recente(chave):
            continue

        cliente = processo.cliente

        enviar_mensagem_whatsapp(
            cliente.id, cliente.telefone, MENSAGEM_SEM_MOVIMENTACAO
        )

        registrar_interacao(
            id_cliente=cliente.id,
            id_processo=processo.id,
            tipo="sem_movimentacao",
            dados={},
        )

        registrar_envio_com_validade(chave, TEMPO_30_DIAS)
        enviados += 1

    return {"enviados": enviados}


@shared_task(bind=True)
def enviar_pesquisa_satisfacao(self):

    momento = agora_local()

    if not horario_permitido(momento):
        espera = segundos_ate_proximo_horario(momento)
        raise self.retry(countdown=espera)

    clientes = buscar_clientes_para_pesquisa()

    mes_referencia = momento.strftime("%Y-%m")
    enviados = 0

    for cliente in clientes:

        chave = chave_limite("limite_pesquisa", cliente.id, mes_referencia)

        if envio_recente(chave):
            continue

        enviar_mensagem_whatsapp(
            cliente.id, cliente.telefone, MENSAGEM_PESQUISA_SATISFACAO
        )

        registrar_interacao(
            id_cliente=cliente.id,
            id_processo=None,
            tipo="pesquisa_satisfacao",
            dados={"mes": mes_referencia},
        )

        registrar_envio_com_validade(chave, TEMPO_32_DIAS)
        enviados += 1

    return {"enviados": enviados}


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def processar_mensagem_recebida(
    self, id_escritorio: int, id_cliente: int, mensagem: str, tipo: str
):
    # Import lazy: evita importar asyncpg e SQLAlchemy no boot do módulo.
    # O orchestrator já envia a resposta via EvolutionClient em _node_enviar_resposta,
    # portanto esta task NÃO deve reenviar pelo WhatsApp.
    from feature_1_ia_personalizada.services.ai.orchestrator import (
        executar_fluxo_orquestrador,
    )

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

        return {"status": "ok"}

    except Exception as erro:
        registrar_interacao(
            id_cliente=id_cliente,
            id_processo=None,
            tipo="erro_processamento",
            dados={"erro": str(erro)},
        )

        raise
