from __future__ import annotations

import os
import time
import unicodedata
import structlog
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Any

import redis
from celery import shared_task
from prometheus_client import Counter

from feature_1_ia_personalizada.services.integrations.google_sheets import (
    GoogleSheetsClient as _RealGoogleSheetsClient,
)

logger = structlog.get_logger(__name__)

_mensagens_relacionamento_enviadas_total = Counter(
    "mensagens_relacionamento_enviadas_total",
    "Total de mensagens de relacionamento enviadas com sucesso",
    labelnames=["tipo"],
)

FUSO_HORARIO_PADRAO = int(os.getenv("FUSO_HORARIO_PADRAO", "-3"))
URL_REDIS = os.getenv("REDIS_URL", "redis://localhost:6379/0")
cliente_redis = redis.Redis.from_url(URL_REDIS, decode_responses=True)

TAMANHO_LOTE = 10
TEMPO_ALERTA_POR_CLIENTE = 15  # limiar de observabilidade; não interrompe o processamento
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

TEMPLATE_DATA_COMEMORATIVA_GENERICA = (
    "📅 Hoje é {nome_data}.\n\n"
    "Se precisar de qualquer apoio com seu processo, estou à disposição."
)


@dataclass
class Cliente:
    id: int
    nome: str
    telefone: str
    status: str
    data_nascimento: Optional[str] = None
    profissao: Optional[str] = None


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
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )


def chave(prefixo: str, *partes: Any) -> str:
    return prefixo + ":" + ":".join(str(p) for p in partes)


def adquirir_bloqueio(chave_bloqueio: str, tempo_segundos: int) -> bool:
    return bool(cliente_redis.set(chave_bloqueio, "1", nx=True, ex=tempo_segundos))


def ja_enviado_recentemente(chave_envio: str) -> bool:
    return cliente_redis.exists(chave_envio) == 1


def marcar_enviado(chave_envio: str, tempo_segundos: int):
    cliente_redis.set(chave_envio, "1", ex=tempo_segundos)


def dia_mes_hoje() -> tuple[int, int]:
    hoje = agora_local().date()
    return hoje.day, hoje.month


def dividir_em_lotes(itens: list[Any], tamanho: int) -> list[list[Any]]:
    return [itens[i:i + tamanho] for i in range(0, len(itens), tamanho)]


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
    def get_clientes() -> list[Cliente]:
        raw = GoogleSheetsClient._get().get_clientes()
        return [
            Cliente(
                id=d["id"],
                nome=d["nome"],
                telefone=d["telefone"],
                status=d["status"],
                data_nascimento=d.get("data_nascimento"),
                profissao=d.get("profissao"),
            )
            for d in raw
        ]

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
    def enviar_mensagem(*, telefone: str, texto: str):
        # TODO: implementar integração real com a API do WhatsApp
        raise NotImplementedError


def buscar_processo_ativo_do_cliente(id_cliente: int) -> Optional[Processo]:
    # TODO: implementar consulta ao banco de dados
    raise NotImplementedError


def salvar_interacao(*, id_cliente: int, id_processo: Optional[int], texto: str, metadata_json: dict):
    # TODO: implementar persistência no banco de dados
    raise NotImplementedError


def buscar_data_ultima_interacao(id_cliente: int) -> Optional[datetime]:
    # TODO: implementar consulta ao banco de dados.
    # Atenção: chamada em loop em verificar_clientes_sem_contato — preferir batch lookup
    # para evitar N+1 queries (ex: SELECT id, ultima_interacao FROM clientes WHERE id IN (...)).
    raise NotImplementedError


# ====== TASKS ======

@shared_task(bind=True)
def verificar_aniversarios_diarios(self) -> dict:
    clientes = GoogleSheetsClient.get_clientes()
    clientes_ativos = [c for c in clientes if normalizar_texto(c.status) == "ativo"]

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

            chave_envio = chave("relacionamento:aniversario", cliente.id, f"{dia:02d}-{mes:02d}")
            if ja_enviado_recentemente(chave_envio):
                ignorados += 1
                continue

            chave_bloqueio = chave("lock:aniversario", cliente.id)
            if not adquirir_bloqueio(chave_bloqueio, TEMPO_5_MINUTOS):
                ignorados += 1
                continue

            processo = buscar_processo_ativo_do_cliente(cliente.id)

            texto = TEMPLATE_ANIVERSARIO.format(nome=cliente.nome)
            WhatsAppService.enviar_mensagem(telefone=cliente.telefone, texto=texto)

            GoogleSheetsClient.registrar_log_envio(
                tipo="aniversario",
                cliente_id=cliente.id,
                detalhe=f"processo={processo.numero if processo else 'nenhum'}"
            )

            salvar_interacao(
                id_cliente=cliente.id,
                id_processo=processo.id if processo else None,
                texto=texto,
                metadata_json={"tipo_relacionamento": "aniversario"}
            )

            _mensagens_relacionamento_enviadas_total.labels(tipo="aniversario").inc()
            marcar_enviado(chave_envio, TEMPO_30_DIAS)
            enviados += 1

            if time.time() - inicio > TEMPO_ALERTA_POR_CLIENTE:
                logger.warning("timeout_por_cliente", tipo="aniversario", cliente_id=cliente.id)

        time.sleep(1)

    return {"status": "ok", "enviados": enviados, "ignorados": ignorados, "total": len(aniversariantes)}


@shared_task(bind=True)
def verificar_datas_comemorativas(self) -> dict:
    clientes = GoogleSheetsClient.get_clientes()
    clientes_ativos = [c for c in clientes if normalizar_texto(c.status) == "ativo"]

    datas = GoogleSheetsClient.get_datas_comemorativas()
    dia, mes = dia_mes_hoje()

    datas_hoje = [d for d in datas if int(d.get("dia", -1)) == dia and int(d.get("mes", -1)) == mes]
    if not datas_hoje:
        return {"status": "ok", "enviados": 0, "ignorados": 0, "datas": 0}

    enviados = 0
    ignorados = 0

    for data_info in datas_hoje:
        nome_data = str(data_info.get("nome", "Data comemorativa")).strip()
        profissao_alvo = normalizar_texto(str(data_info.get("profissao_alvo", "")).strip())
        template = str(data_info.get("template", "")).strip()

        if profissao_alvo:
            clientes_filtrados = [
                c for c in clientes_ativos
                if normalizar_texto(c.profissao or "") == profissao_alvo
            ]
        else:
            clientes_filtrados = clientes_ativos

        for lote in dividir_em_lotes(clientes_filtrados, TAMANHO_LOTE):
            for cliente in lote:
                inicio = time.time()

                chave_envio = chave("relacionamento:data", cliente.id, f"{dia:02d}-{mes:02d}", normalizar_texto(nome_data))
                if ja_enviado_recentemente(chave_envio):
                    ignorados += 1
                    continue

                chave_bloqueio = chave("lock:data", cliente.id, normalizar_texto(nome_data))
                if not adquirir_bloqueio(chave_bloqueio, TEMPO_5_MINUTOS):
                    ignorados += 1
                    continue

                processo = buscar_processo_ativo_do_cliente(cliente.id)

                if template == "TEMPLATE_DIA_BANCARIO":
                    texto = TEMPLATE_DIA_BANCARIO.format(nome_data=nome_data)
                else:
                    texto = TEMPLATE_DATA_COMEMORATIVA_GENERICA.format(nome_data=nome_data)

                WhatsAppService.enviar_mensagem(telefone=cliente.telefone, texto=texto)

                GoogleSheetsClient.registrar_log_envio(
                    tipo="data_comemorativa",
                    cliente_id=cliente.id,
                    detalhe=f"data={nome_data} processo={processo.numero if processo else 'nenhum'}"
                )

                salvar_interacao(
                    id_cliente=cliente.id,
                    id_processo=processo.id if processo else None,
                    texto=texto,
                    metadata_json={"tipo_relacionamento": "data_comemorativa", "nome_data": nome_data}
                )

                _mensagens_relacionamento_enviadas_total.labels(tipo="data_comemorativa").inc()
                marcar_enviado(chave_envio, TEMPO_30_DIAS)
                enviados += 1

                if time.time() - inicio > TEMPO_ALERTA_POR_CLIENTE:
                    logger.warning("timeout_por_cliente", tipo="data_comemorativa", cliente_id=cliente.id)

            time.sleep(1)

    return {"status": "ok", "enviados": enviados, "ignorados": ignorados, "datas": len(datas_hoje)}


@shared_task(bind=True)
def verificar_clientes_sem_contato(self) -> dict:
    clientes = GoogleSheetsClient.get_clientes()
    clientes_ativos = [c for c in clientes if normalizar_texto(c.status) == "ativo"]

    limite_maximo = 10
    dias_sem_contato = 90
    enviados = 0
    ignorados = 0

    agora = agora_local()
    candidatos: list[Cliente] = []

    for cliente in clientes_ativos:
        ultima = buscar_data_ultima_interacao(cliente.id)
        if ultima is None:
            candidatos.append(cliente)
            continue
        if (agora - ultima) > timedelta(days=dias_sem_contato):
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
            WhatsAppService.enviar_mensagem(telefone=cliente.telefone, texto=texto)

            GoogleSheetsClient.registrar_log_envio(
                tipo="check_in",
                cliente_id=cliente.id,
                detalhe=f"processo={processo.numero if processo else 'nenhum'}"
            )

            salvar_interacao(
                id_cliente=cliente.id,
                id_processo=processo.id if processo else None,
                texto=texto,
                metadata_json={"tipo_relacionamento": "check_in"}
            )

            _mensagens_relacionamento_enviadas_total.labels(tipo="check_in").inc()
            marcar_enviado(chave_envio, TEMPO_30_DIAS)
            enviados += 1

            if time.time() - inicio > TEMPO_ALERTA_POR_CLIENTE:
                logger.warning("timeout_por_cliente", tipo="check_in", cliente_id=cliente.id)

        time.sleep(1)

    return {"status": "ok", "enviados": enviados, "ignorados": ignorados, "candidatos": len(candidatos)}