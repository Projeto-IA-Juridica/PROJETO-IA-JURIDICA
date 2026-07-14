"""
Workers Celery da máquina de vendas. Amarram o roteiro de ponta a ponta.

| Task                        | Trigger              | Etapa | O que faz                                              |
|-----------------------------|----------------------|-------|-------------------------------------------------------|
| enriquecer_alvos            | cron a cada 10 min   | 2/3   | novo → busca processo → espelho → valida → fila       |
| disparar_frios              | cron a cada 5 min    | 4     | fila_envio → respeita pacing → envia toque 1          |
| avancar_cadencia            | cron a cada 30 min   | 5     | em_cadencia com proximo_toque vencido → toque 2/3     |

Todos reusam os serviços de feature_vendas e a infra Celery/DB de worker que
já existe (worker_session_factory, NullPool — event loop seguro).

Sem lógica de negócio nova aqui: os workers só orquestram
filtragem → enriquecimento → validacao → dispatcher_pacing → humanizacao.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import structlog
from celery import shared_task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from feature_vendas import config as vconfig
from feature_vendas.models.alvo_vendas import AlvoVendas
from feature_vendas.services.dispatcher_pacing import DispatcherPacing
from feature_vendas.services.enriquecimento import Enriquecedor, LeitorDataJud
from feature_vendas.services.humanizacao.cadencia import EntregaHumanizada
from feature_vendas.services.humanizacao.evolution_humano import EvolutionHumano
from feature_vendas.services.validacao import validar_espelho
from shared.config.settings import settings

logger = structlog.get_logger(__name__)

# Cadência (etapa 5): dias entre toques. Índice = toque já enviado.
_DIAS_CADENCIA = {1: 3, 2: 4}  # toque 1→2: +3 dias; toque 2→3: +4 dias
_MAX_TOQUES = 3


@asynccontextmanager
async def _sessao() -> AsyncGenerator[AsyncSession, None]:
    # Mesma regra dos workers do produto: factory global NullPool, nunca a
    # pooled da API (event loop do asyncio.run é novo a cada task).
    from shared.database.connection import worker_session_factory

    async with worker_session_factory() as s:
        yield s


def _evolution() -> EvolutionHumano:
    assert settings.EVOLUTION_API_URL and vconfig.VENDAS_EVOLUTION_API_KEY
    return EvolutionHumano(settings.EVOLUTION_API_URL, vconfig.VENDAS_EVOLUTION_API_KEY)


async def _enriquecer_impl() -> int:
    processados = 0
    async with _sessao() as db:
        alvos = (
            (await db.execute(select(AlvoVendas).where(AlvoVendas.status == "novo").limit(20)))
            .scalars()
            .all()
        )

        if not alvos:
            return 0

        enriquecedor = Enriquecedor(
            vitrine_url=vconfig.VENDAS_VITRINE_URL,
            leitor=_leitor_datajud(),  # CNJ da planilha → movimentação (hoje)
            descobridor=None,  # descoberta por OAB → futuro (Escavador)
        )
        for alvo in alvos:
            alvo.status = "enriquecendo"
            msg = await enriquecedor.enriquecer(
                alvo.nome_contato, oab=alvo.oab, processo_cnj=alvo.processo_cnj
            )
            resultado = validar_espelho(
                template=msg.template,
                processo_cnj=msg.processo_cnj,
                movimentacao_bruta=msg.movimentacao_bruta,
                mensagem=msg.texto,
            )
            alvo.processo_cnj = msg.processo_cnj
            alvo.movimentacao_bruta = msg.movimentacao_bruta
            alvo.mensagem_espelho = msg.texto
            alvo.template_usado = msg.template
            alvo.confianca_validacao = resultado.confianca
            alvo.status = resultado.fila
            alvo.metadados = {**(alvo.metadados or {}), "validacao_obs": resultado.observacao}
            processados += 1

        await db.commit()
    logger.info("vendas_enriquecimento_lote", processados=processados)
    return processados


async def _disparar_impl() -> int:
    enviados = 0
    async with _sessao() as db:
        pacing = DispatcherPacing(redis=_redis(), chip_iniciado_em=vconfig.chip_iniciado_em())
        entrega = EntregaHumanizada(_evolution(), vconfig.instancia_disparo())

        while True:
            decisao = await pacing.avaliar()
            if not decisao.pode_enviar:
                logger.info("vendas_disparo_pausado", motivo=decisao.motivo)
                break

            alvo = (
                await db.execute(
                    select(AlvoVendas)
                    .where(AlvoVendas.status == "fila_envio")
                    .order_by(AlvoVendas.classe_icp, AlvoVendas.id)
                    .limit(1)
                )
            ).scalar_one_or_none()
            if not alvo or not alvo.mensagem_espelho:
                break

            # Toque 1 vai como uma mensagem só (é um recado, não uma conversa),
            # mas ainda com "digitando" proporcional ao tamanho.
            await entrega.responder(alvo.whatsapp, "", alvo.mensagem_espelho)

            alvo.status = "em_cadencia"
            alvo.toques_enviados = 1
            alvo.ultimo_toque_em = datetime.now(UTC)
            alvo.proximo_toque_em = datetime.now(UTC) + timedelta(days=_DIAS_CADENCIA[1])
            await db.commit()
            await pacing.registrar_envio()
            enviados += 1

            # Espaça o próximo envio (o próprio ciclo do worker respeita isso:
            # cada task envia 1 e sai; o cron de 5 min faz o resto). Sai já.
            break
    logger.info("vendas_disparo_ciclo", enviados=enviados)
    return enviados


def _leitor_datajud() -> LeitorDataJud:
    from feature_1_ia_personalizada.services.legal_data.datajud_client import DataJudClient

    return LeitorDataJud(DataJudClient(api_key=settings.DATAJUD_API_KEY))


def _redis():  # noqa: ANN202
    import redis.asyncio as aioredis

    return aioredis.from_url(settings.REDIS_URL, decode_responses=True)


# Toques 2 e 3 da cadência (etapa 5). Texto curto de propósito.
_TOQUE_2 = (
    "Doutor(a) {nome}, tudo bem? Só retomando aqui.\n"
    'Uma conta rápida: responder "tem novidade?" toma umas 14h por mês por advogado. '
    "A gente devolve esse tempo. Vale um teste de 2 minutos? {vitrine}"
)
_TOQUE_3 = (
    "Doutor(a) {nome}, última vez que passo por aqui, prometo.\n"
    "Deixo a assistente de demonstração ligada caso a curiosidade bata: {vitrine}. "
    "Sucesso com a banca!"
)
_TOQUE_TEXTO = {2: _TOQUE_2, 3: _TOQUE_3}


async def _cadencia_impl() -> int:
    """
    Toques 2 e 3 para quem não respondeu (etapa 5).

    Só age em alvos 'em_cadencia' com proximo_toque_em vencido. Quem respondeu
    já saiu da cadência (o webhook da Clara muda o status para 'respondeu'),
    então aqui nunca reaborda quem engajou.
    """
    from feature_vendas.services.enriquecimento import _primeiro_nome

    enviados = 0
    agora = datetime.now(UTC)
    async with _sessao() as db:
        pacing = DispatcherPacing(redis=_redis(), chip_iniciado_em=vconfig.chip_iniciado_em())
        entrega = EntregaHumanizada(_evolution(), vconfig.instancia_disparo())

        alvos = (
            (
                await db.execute(
                    select(AlvoVendas)
                    .where(
                        AlvoVendas.status == "em_cadencia",
                        AlvoVendas.proximo_toque_em <= agora,
                        AlvoVendas.toques_enviados < _MAX_TOQUES,
                    )
                    .limit(20)
                )
            )
            .scalars()
            .all()
        )

        for alvo in alvos:
            decisao = await pacing.avaliar()
            if not decisao.pode_enviar:
                break  # respeita janela/cap/breaker também nos follow-ups

            proximo = alvo.toques_enviados + 1
            texto = _TOQUE_TEXTO[proximo].format(
                nome=_primeiro_nome(alvo.nome_contato), vitrine=vconfig.VENDAS_VITRINE_URL
            )
            await entrega.responder(alvo.whatsapp, "", texto)
            await pacing.registrar_envio()

            alvo.toques_enviados = proximo
            alvo.ultimo_toque_em = agora
            if proximo >= _MAX_TOQUES:
                # Esgotou a cadência sem resposta: encerra bem, sai da fila.
                alvo.status = "descartado"
                alvo.proximo_toque_em = None
                alvo.metadados = {**(alvo.metadados or {}), "motivo_descarte": "cadência esgotada"}
            else:
                alvo.proximo_toque_em = agora + timedelta(days=_DIAS_CADENCIA[proximo])
            enviados += 1

        await db.commit()
    logger.info("vendas_cadencia_ciclo", enviados=enviados)
    return enviados


@shared_task(name="vendas.enriquecer_alvos")
def enriquecer_alvos() -> int:
    import asyncio

    return asyncio.run(_enriquecer_impl())


@shared_task(name="vendas.disparar_frios")
def disparar_frios() -> int:
    import asyncio

    return asyncio.run(_disparar_impl())


@shared_task(name="vendas.avancar_cadencia")
def avancar_cadencia() -> int:
    import asyncio

    return asyncio.run(_cadencia_impl())
