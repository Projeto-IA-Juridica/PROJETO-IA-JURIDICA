from __future__ import annotations

import os
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import redis
import structlog
from celery import shared_task
from prometheus_client import Counter

from feature_1_ia_personalizada.services.integrations.google_sheets import (
    GoogleSheetsClient as _RealGoogleSheetsClient,
)
from shared.config.settings import settings
from shared.database.worker_queries import (
    enviar_mensagem_whatsapp as _enviar_whatsapp,
)
from shared.database.worker_queries import (
    insert_interacao,
    query_clientes_relacionamento,
    query_ultima_interacao_batch,
)
from shared.database.worker_queries import (
    query_processo_ativo_do_cliente as _orm_processo_ativo,
)

logger = structlog.get_logger(__name__)

_mensagens_relacionamento_enviadas_total = Counter(
    "mensagens_relacionamento_enviadas_total",
    "Total de mensagens de relacionamento enviadas com sucesso",
    labelnames=["tipo"],
)

FUSO_HORARIO_PADRAO = int(os.getenv("FUSO_HORARIO_PADRAO", "-3"))
cliente_redis = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)

TAMANHO_LOTE = 10
TEMPO_ALERTA_POR_CLIENTE = (
    15  # limiar de observabilidade; não interrompe o processamento
)
TEMPO_30_DIAS = 30 * 24 * 60 * 60
TEMPO_5_MINUTOS = 5 * 60


TEMPLATE_ANIVERSARIO = (
    "🎉 {nome}, feliz aniversário!\n\n"
    "Passando pra te desejar um dia incrível. Se precisar de algo sobre seu processo, estou por aqui. 😊"
)

TEMPLATE_MENSAGEM_TRIMESTRAL = (
    "👋 Oi, {nome}! Passando pra saber se está tudo certo.\n\n"
    "Se quiser, posso te atualizar sobre seu processo e próximos passos."
)

TEMPLATE_DIA_BANCARIO = (
    "🏦 Hoje é {nome_data}.\n\n"
    "Se precisar de ajuda com documentos, prazos ou dúvidas do processo, me chama por aqui."
)

TEMPLATE_DATA_COMEMORATIVA_GENERICA = "📅 Hoje é {nome_data}.\n\nSe precisar de qualquer apoio com seu processo, estou à disposição."


@dataclass
class Cliente:
    id: int
    nome: str
    telefone: str
    status: str
    data_nascimento: str | None = None
    profissao: str | None = None


@dataclass
class Processo:
    id: int
    numero: str
    cliente_id: int
    status: str


def agora_local() -> datetime:
    fuso = timezone(timedelta(hours=FUSO_HORARIO_PADRAO))
    return datetime.now(tz=fuso)


def normalizar_texto(texto: str) -> str:
    if not texto:
        return ""
    texto = texto.strip().lower()
    return "".join(
        c
        for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )


def chave(prefixo: str, *partes: Any) -> str:
    return prefixo + ":" + ":".join(str(p) for p in partes)


def adquirir_bloqueio(chave_bloqueio: str, tempo_segundos: int) -> bool:
    if not cliente_redis:
        return False
    return bool(cliente_redis.set(chave_bloqueio, "1", nx=True, ex=tempo_segundos))


def ja_enviado_recentemente(chave_envio: str) -> bool:
    if not cliente_redis:
        return False
    return bool(cliente_redis.exists(chave_envio) == 1)


def marcar_enviado(chave_envio: str, tempo_segundos: int) -> None:
    if cliente_redis:
        cliente_redis.set(chave_envio, "1", ex=tempo_segundos)


def dia_mes_hoje() -> tuple[int, int]:
    hoje = agora_local().date()
    return hoje.day, hoje.month


def dividir_em_lotes(itens: list[Any], tamanho: int) -> list[list[Any]]:
    return [itens[i : i + tamanho] for i in range(0, len(itens), tamanho)]


# ====== INTEGRAÇÕES ======


def _criar_sheets_client() -> _RealGoogleSheetsClient:
    """Instancia o cliente real a partir das variáveis de ambiente."""
    credentials_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "")
    spreadsheet_id = os.getenv("GOOGLE_SHEETS_ID", "")
    return _RealGoogleSheetsClient(credentials_path, spreadsheet_id)


class GoogleSheetsClient:
    """
    Wrapper síncrono sobre o GoogleSheetsClient real.
    Converte os dicts retornados pelo cliente para objetos Cliente.
    O cliente real é instanciado sob demanda (lazy) a partir das env vars.
    """

    _client: _RealGoogleSheetsClient | None = None

    @classmethod
    def _get(cls) -> _RealGoogleSheetsClient:
        if cls._client is None:
            cls._client = _criar_sheets_client()
        return cls._client

    @staticmethod
    def get_datas_comemorativas() -> list[dict]:
        return GoogleSheetsClient._get().get_datas_comemorativas()

    @staticmethod
    def registrar_log_envio(*, tipo: str, cliente_id: int, detalhe: str) -> None:
        GoogleSheetsClient._get().registrar_log_envio(
            tipo=tipo, cliente_id=cliente_id, detalhe=detalhe
        )


class WhatsAppService:
    @staticmethod
    def enviar_mensagem(*, id_cliente: int, telefone: str, texto: str) -> None:
        """Envia mensagem via Evolution API. Resolve a instância WhatsApp pelo escritório do cliente."""
        _enviar_whatsapp(id_cliente, telefone, texto)


def buscar_processo_ativo_do_cliente(id_cliente: int) -> Processo | None:
    dado = _orm_processo_ativo(id_cliente)
    if dado is None:
        return None
    return Processo(
        id=dado["id"],
        numero=dado["numero"],
        cliente_id=id_cliente,
        status=dado["status"],
    )


def salvar_interacao(
    *, id_cliente: int, id_processo: int | None, texto: str, metadata_json: dict
):
    insert_interacao(
        id_cliente=id_cliente,
        id_processo=id_processo,
        texto=texto,
        metadata_json=metadata_json,
    )


# ====== TASKS ======


@shared_task(bind=True)
def verificar_aniversarios_diarios(self) -> dict:
    _raw = query_clientes_relacionamento()
    clientes = [
        Cliente(
            id=d["id"],
            nome=d["nome"],
            telefone=d["telefone"],
            status=d["status"],
            data_nascimento=d.get("data_nascimento"),
            profissao=d.get("profissao"),
        )
        for d in _raw
    ]
    clientes_ativos = clientes  # query já filtra ativo=True

    dia, mes = dia_mes_hoje()

    aniversariantes: list[Cliente] = []
    for cliente in clientes_ativos:
        if not cliente.data_nascimento:
            continue
        try:
            data = datetime.strptime(cliente.data_nascimento, "%Y-%m-%d").date()
        except ValueError:
            continue
        if data.day == dia and data.month == mes:
            aniversariantes.append(cliente)

    enviados = 0
    ignorados = 0

    for lote in dividir_em_lotes(aniversariantes, TAMANHO_LOTE):
        for cliente in lote:
            inicio = time.time()

            chave_envio = chave(
                "relacionamento:aniversario", cliente.id, f"{dia:02d}-{mes:02d}"
            )
            if ja_enviado_recentemente(chave_envio):
                ignorados += 1
                continue

            chave_bloqueio = chave("lock:aniversario", cliente.id)
            if not adquirir_bloqueio(chave_bloqueio, TEMPO_5_MINUTOS):
                ignorados += 1
                continue

            processo = buscar_processo_ativo_do_cliente(cliente.id)

            texto = TEMPLATE_ANIVERSARIO.format(nome=cliente.nome)
            WhatsAppService.enviar_mensagem(
                id_cliente=cliente.id, telefone=cliente.telefone, texto=texto
            )
            # Marca ANTES das operações não-críticas: se Sheets ou DB falharem
            # e a task for reexecutada, o cliente não recebe a mensagem de novo.
            marcar_enviado(chave_envio, TEMPO_30_DIAS)
            _mensagens_relacionamento_enviadas_total.labels(tipo="aniversario").inc()
            enviados += 1

            try:
                GoogleSheetsClient.registrar_log_envio(
                    tipo="aniversario",
                    cliente_id=cliente.id,
                    detalhe=f"processo={processo.numero if processo else 'nenhum'}",
                )
            except Exception as e:
                logger.warning(
                    "log_sheets_falhou",
                    tipo="aniversario",
                    cliente_id=cliente.id,
                    erro=str(e),
                )

            try:
                salvar_interacao(
                    id_cliente=cliente.id,
                    id_processo=processo.id if processo else None,
                    texto=texto,
                    metadata_json={"tipo_relacionamento": "aniversario"},
                )
            except Exception as e:
                logger.warning(
                    "salvar_interacao_falhou",
                    tipo="aniversario",
                    cliente_id=cliente.id,
                    erro=str(e),
                )

            if time.time() - inicio > TEMPO_ALERTA_POR_CLIENTE:
                logger.warning(
                    "timeout_por_cliente", tipo="aniversario", cliente_id=cliente.id
                )

        time.sleep(1)

    return {
        "status": "ok",
        "enviados": enviados,
        "ignorados": ignorados,
        "total": len(aniversariantes),
    }


@shared_task(bind=True)
def verificar_datas_comemorativas(self) -> dict:
    _raw = query_clientes_relacionamento()
    clientes_ativos = [
        Cliente(
            id=d["id"],
            nome=d["nome"],
            telefone=d["telefone"],
            status=d["status"],
            data_nascimento=d.get("data_nascimento"),
            profissao=d.get("profissao"),
        )
        for d in _raw
    ]  # query já filtra ativo=True

    datas = GoogleSheetsClient.get_datas_comemorativas()
    dia, mes = dia_mes_hoje()

    datas_hoje = [
        d
        for d in datas
        if int(d.get("dia", -1)) == dia and int(d.get("mes", -1)) == mes
    ]
    if not datas_hoje:
        return {"status": "ok", "enviados": 0, "ignorados": 0, "datas": 0}

    enviados = 0
    ignorados = 0

    for data_info in datas_hoje:
        nome_data = str(data_info.get("nome", "Data comemorativa")).strip()
        profissao_alvo = normalizar_texto(
            str(data_info.get("profissao_alvo", "")).strip()
        )
        template = str(data_info.get("template", "")).strip()

        if profissao_alvo:
            clientes_filtrados = [
                c
                for c in clientes_ativos
                if normalizar_texto(c.profissao or "") == profissao_alvo
            ]
        else:
            clientes_filtrados = clientes_ativos

        for lote in dividir_em_lotes(clientes_filtrados, TAMANHO_LOTE):
            for cliente in lote:
                inicio = time.time()

                chave_envio = chave(
                    "relacionamento:data",
                    cliente.id,
                    f"{dia:02d}-{mes:02d}",
                    normalizar_texto(nome_data),
                )
                if ja_enviado_recentemente(chave_envio):
                    ignorados += 1
                    continue

                chave_bloqueio = chave(
                    "lock:data", cliente.id, normalizar_texto(nome_data)
                )
                if not adquirir_bloqueio(chave_bloqueio, TEMPO_5_MINUTOS):
                    ignorados += 1
                    continue

                processo = buscar_processo_ativo_do_cliente(cliente.id)

                if template == "TEMPLATE_DIA_BANCARIO":
                    texto = TEMPLATE_DIA_BANCARIO.format(nome_data=nome_data)
                else:
                    texto = TEMPLATE_DATA_COMEMORATIVA_GENERICA.format(
                        nome_data=nome_data
                    )

                WhatsAppService.enviar_mensagem(
                    id_cliente=cliente.id, telefone=cliente.telefone, texto=texto
                )
                marcar_enviado(chave_envio, TEMPO_30_DIAS)
                _mensagens_relacionamento_enviadas_total.labels(
                    tipo="data_comemorativa"
                ).inc()
                enviados += 1

                try:
                    GoogleSheetsClient.registrar_log_envio(
                        tipo="data_comemorativa",
                        cliente_id=cliente.id,
                        detalhe=f"data={nome_data} processo={processo.numero if processo else 'nenhum'}",
                    )
                except Exception as e:
                    logger.warning(
                        "log_sheets_falhou",
                        tipo="data_comemorativa",
                        cliente_id=cliente.id,
                        erro=str(e),
                    )

                try:
                    salvar_interacao(
                        id_cliente=cliente.id,
                        id_processo=processo.id if processo else None,
                        texto=texto,
                        metadata_json={
                            "tipo_relacionamento": "data_comemorativa",
                            "nome_data": nome_data,
                        },
                    )
                except Exception as e:
                    logger.warning(
                        "salvar_interacao_falhou",
                        tipo="data_comemorativa",
                        cliente_id=cliente.id,
                        erro=str(e),
                    )

                if time.time() - inicio > TEMPO_ALERTA_POR_CLIENTE:
                    logger.warning(
                        "timeout_por_cliente",
                        tipo="data_comemorativa",
                        cliente_id=cliente.id,
                    )

            time.sleep(1)

    return {
        "status": "ok",
        "enviados": enviados,
        "ignorados": ignorados,
        "datas": len(datas_hoje),
    }


@shared_task(bind=True)
def verificar_clientes_sem_contato(self) -> dict:
    _raw = query_clientes_relacionamento()
    clientes_ativos = [
        Cliente(
            id=d["id"],
            nome=d["nome"],
            telefone=d["telefone"],
            status=d["status"],
            data_nascimento=d.get("data_nascimento"),
            profissao=d.get("profissao"),
        )
        for d in _raw
    ]  # query já filtra ativo=True

    limite_maximo = 10
    dias_sem_contato = 90
    enviados = 0
    ignorados = 0

    agora = agora_local()
    candidatos: list[Cliente] = []

    ids_ativos = [c.id for c in clientes_ativos]
    datas_ultima = query_ultima_interacao_batch(ids_ativos)

    for cliente in clientes_ativos:
        ultima = datas_ultima.get(cliente.id)
        if ultima is None or (agora - ultima) > timedelta(days=dias_sem_contato):
            candidatos.append(cliente)

    candidatos = candidatos[:limite_maximo]

    for lote in dividir_em_lotes(candidatos, TAMANHO_LOTE):
        for cliente in lote:
            inicio = time.time()

            semana_tag = agora.strftime("%Y-%W")
            chave_envio = chave("relacionamento:checkin", cliente.id, semana_tag)
            if ja_enviado_recentemente(chave_envio):
                ignorados += 1
                continue

            chave_bloqueio = chave("lock:checkin", cliente.id)
            if not adquirir_bloqueio(chave_bloqueio, TEMPO_5_MINUTOS):
                ignorados += 1
                continue

            processo = buscar_processo_ativo_do_cliente(cliente.id)

            texto = TEMPLATE_MENSAGEM_TRIMESTRAL.format(nome=cliente.nome)
            WhatsAppService.enviar_mensagem(
                id_cliente=cliente.id, telefone=cliente.telefone, texto=texto
            )
            marcar_enviado(chave_envio, TEMPO_30_DIAS)
            _mensagens_relacionamento_enviadas_total.labels(tipo="check_in").inc()
            enviados += 1

            try:
                GoogleSheetsClient.registrar_log_envio(
                    tipo="check_in",
                    cliente_id=cliente.id,
                    detalhe=f"processo={processo.numero if processo else 'nenhum'}",
                )
            except Exception as e:
                logger.warning(
                    "log_sheets_falhou",
                    tipo="check_in",
                    cliente_id=cliente.id,
                    erro=str(e),
                )

            try:
                salvar_interacao(
                    id_cliente=cliente.id,
                    id_processo=processo.id if processo else None,
                    texto=texto,
                    metadata_json={"tipo_relacionamento": "check_in"},
                )
            except Exception as e:
                logger.warning(
                    "salvar_interacao_falhou",
                    tipo="check_in",
                    cliente_id=cliente.id,
                    erro=str(e),
                )

            if time.time() - inicio > TEMPO_ALERTA_POR_CLIENTE:
                logger.warning(
                    "timeout_por_cliente", tipo="check_in", cliente_id=cliente.id
                )

        time.sleep(1)

    return {
        "status": "ok",
        "enviados": enviados,
        "ignorados": ignorados,
        "candidatos": len(candidatos),
    }
