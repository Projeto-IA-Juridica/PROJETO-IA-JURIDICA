"""
shared/database/worker_queries.py
==================================
Queries ORM síncronas para uso nos workers Celery.

Os workers Celery rodam em processos síncronos sem event loop ativo.
Cada função pública usa asyncio.run() para executar a query assíncrona —
padrão seguro nesse contexto pois o Celery não instancia event loops
nos worker processes por padrão.

Funções públicas exportadas
----------------------------
Processos (monitor_processos.py):
    query_processos_monitorados(limite)
    query_processo_por_id(id_processo)
    update_ultimo_andamento(id_processo, texto, data_iso)

Relacionamento (mensagens_relacionamento.py):
    query_clientes_relacionamento()
    query_processo_ativo_do_cliente(id_cliente)
    insert_interacao(id_cliente, id_processo, texto, metadata_json, tipo, direcao)
    query_ultima_interacao_batch(ids_clientes)
    enviar_mensagem_whatsapp(id_cliente, telefone, texto)

Notificações (send_notifications.py):
    query_processo_e_cliente(id_processo)
    query_processos_sem_movimentacao()
    query_clientes_para_pesquisa()
    query_clientes_ativos_por_escritorio(escritorio_id)
    update_ultimo_andamento(id_processo, texto, data_iso)

"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.orm import selectinload

from shared.database.connection import async_session_factory
from shared.models.cliente import Cliente as ClienteModel
from shared.models.escritorio import Escritorio
from shared.models.interacao import Interacao
from shared.models.processo import Processo as ProcessoModel

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Tipos de retorno (dataclasses leves, desacoplados do SQLAlchemy)
# ---------------------------------------------------------------------------


@dataclass
class ClienteWorker:
    id: int
    nome: str
    telefone: str
    escritorio_id: int


@dataclass
class ProcessoWorker:
    id: int
    numero_cnj: str
    cliente_id: int
    escritorio_id: int
    cliente: ClienteWorker | None = None


# ---------------------------------------------------------------------------
# Helper interno
# ---------------------------------------------------------------------------


def _run(coro):
    """Executa uma corrotina bloqueante. Seguro em workers Celery."""
    return asyncio.run(coro)


# ===========================================================================
# PROCESSOS  (monitor_processos.py)
# ===========================================================================


async def _query_processos_monitorados(limite: int) -> list[dict[str, Any]]:
    async with async_session_factory() as session:
        result = await session.execute(
            select(ProcessoModel)
            .where(ProcessoModel.monitoramento_ativo == True)  # noqa: E712
            .limit(limite)
        )
        return [
            {
                "id": p.id,
                "numero": p.numero_cnj,
                "data_ultimo_andamento": p.data_ultimo_andamento,
            }
            for p in result.scalars().all()
        ]


def query_processos_monitorados(limite: int) -> list[dict[str, Any]]:
    """SELECT processos WHERE monitoramento_ativo = true LIMIT :limite."""
    return _run(_query_processos_monitorados(limite))  # type: ignore[no-any-return]


async def _query_processo_por_id(id_processo: int) -> dict[str, Any] | None:
    async with async_session_factory() as session:
        result = await session.execute(select(ProcessoModel).where(ProcessoModel.id == id_processo))
        p = result.scalar_one_or_none()
        if p is None:
            return None
        return {
            "id": p.id,
            "numero": p.numero_cnj,
            "data_ultimo_andamento": p.data_ultimo_andamento,
        }


def query_processo_por_id(id_processo: int) -> dict[str, Any] | None:
    """SELECT processo WHERE id = :id."""
    return _run(_query_processo_por_id(id_processo))  # type: ignore[no-any-return]


async def _update_ultimo_andamento(id_processo: int, texto: str, data_iso: str) -> None:
    try:
        data_dt: datetime | None = datetime.fromisoformat(data_iso)
    except (ValueError, TypeError):
        data_dt = None

    async with async_session_factory() as session:
        await session.execute(
            update(ProcessoModel)
            .where(ProcessoModel.id == id_processo)
            .values(ultimo_andamento=texto, data_ultimo_andamento=data_dt)
        )
        await session.commit()


def update_ultimo_andamento(id_processo: int, texto: str, data_iso: str) -> None:
    """UPDATE processos SET ultimo_andamento, data_ultimo_andamento WHERE id."""
    _run(_update_ultimo_andamento(id_processo, texto, data_iso))


# ===========================================================================
# RELACIONAMENTO  (mensagens_relacionamento.py)
# ===========================================================================


async def _query_clientes_relacionamento() -> list[dict[str, Any]]:
    async with async_session_factory() as session:
        result = await session.execute(
            select(ClienteModel).where(ClienteModel.ativo == True)  # noqa: E712
        )
        clientes = []
        for c in result.scalars().all():
            clientes.append(
                {
                    "id": c.id,
                    "nome": c.nome,
                    "telefone": c.telefone_whatsapp,
                    "status": "ativo",
                    "data_nascimento": (str(c.data_nascimento) if c.data_nascimento else None),
                    "profissao": c.profissao,
                }
            )
        return clientes


def query_clientes_relacionamento() -> list[dict[str, Any]]:
    """
    SELECT clientes WHERE ativo = true.

    Retorna lista de dicts com: id, nome, telefone, status, data_nascimento
    (str 'YYYY-MM-DD' ou None), profissao.
    Compatível com o dataclass Cliente de mensagens_relacionamento.py.
    """
    return _run(_query_clientes_relacionamento())  # type: ignore[no-any-return]


async def _query_processo_ativo_do_cliente(
    id_cliente: int,
) -> dict[str, Any] | None:
    async with async_session_factory() as session:
        result = await session.execute(
            select(ProcessoModel)
            .where(
                ProcessoModel.cliente_id == id_cliente,
                ProcessoModel.status == "ativo",
            )
            .limit(1)
        )
        p = result.scalar_one_or_none()
        if p is None:
            return None
        return {"id": p.id, "numero": p.numero_cnj, "status": p.status}


def query_processo_ativo_do_cliente(
    id_cliente: int,
) -> dict[str, Any] | None:
    """SELECT processo ativo do cliente (1 resultado)."""
    return _run(_query_processo_ativo_do_cliente(id_cliente))  # type: ignore[no-any-return]


async def _insert_interacao(
    *,
    id_cliente: int,
    id_processo: int | None,
    texto: str | None,
    metadata_json: dict,
    tipo: str,
    direcao: str,
) -> None:
    async with async_session_factory() as session:
        # Obtém escritorio_id do cliente para respeitar multi-tenancy
        result = await session.execute(
            select(ClienteModel.escritorio_id).where(ClienteModel.id == id_cliente)
        )
        escritorio_id = result.scalar_one_or_none()
        if escritorio_id is None:
            logger.warning("insert_interacao_cliente_nao_encontrado", id_cliente=id_cliente)
            return

        interacao = Interacao(
            cliente_id=id_cliente,
            processo_id=id_processo,
            tipo=tipo,
            direcao=direcao,
            mensagem_ia=texto,
            metadata_json=metadata_json,
            escritorio_id=escritorio_id,
        )
        session.add(interacao)
        await session.commit()


def insert_interacao(
    *,
    id_cliente: int,
    id_processo: int | None,
    texto: str | None = None,
    metadata_json: dict,
    tipo: str = "notificacao",
    direcao: str = "saida",
) -> None:
    """INSERT INTO interacoes. Obtém escritorio_id automaticamente do cliente."""
    _run(
        _insert_interacao(
            id_cliente=id_cliente,
            id_processo=id_processo,
            texto=texto,
            metadata_json=metadata_json,
            tipo=tipo,
            direcao=direcao,
        )
    )


async def _query_ultima_interacao_batch(
    ids_clientes: list[int],
) -> dict[int, datetime]:
    if not ids_clientes:
        return {}
    async with async_session_factory() as session:
        result = await session.execute(
            select(Interacao.cliente_id, func.max(Interacao.created_at))
            .where(Interacao.cliente_id.in_(ids_clientes))
            .group_by(Interacao.cliente_id)
        )
        return {row[0]: row[1] for row in result.all()}


def query_ultima_interacao_batch(
    ids_clientes: list[int],
) -> dict[int, datetime]:
    """
    SELECT cliente_id, MAX(created_at) FROM interacoes
    WHERE cliente_id IN (...) GROUP BY cliente_id.

    Retorna dict {id_cliente: ultima_interacao}.
    Clientes sem interação não aparecem no resultado (usar .get()).
    """
    return _run(_query_ultima_interacao_batch(ids_clientes))  # type: ignore[no-any-return]


# ===========================================================================
# NOTIFICAÇÕES  (send_notifications.py)
# ===========================================================================


async def _query_processo_e_cliente(
    id_processo: int,
) -> tuple[ProcessoWorker, ClienteWorker] | None:
    async with async_session_factory() as session:
        result = await session.execute(
            select(ProcessoModel)
            .where(ProcessoModel.id == id_processo)
            .options(selectinload(ProcessoModel.cliente))
        )
        p = result.scalar_one_or_none()
        if p is None or p.cliente is None:
            return None
        c = p.cliente
        return (
            ProcessoWorker(
                id=p.id,
                numero_cnj=p.numero_cnj,
                cliente_id=p.cliente_id,
                escritorio_id=p.escritorio_id,
            ),
            ClienteWorker(
                id=c.id,
                nome=c.nome,
                telefone=c.telefone_whatsapp,
                escritorio_id=c.escritorio_id,
            ),
        )


def query_processo_e_cliente(
    id_processo: int,
) -> tuple[ProcessoWorker, ClienteWorker] | None:
    """SELECT processo + cliente (eager load) WHERE processo.id = :id."""
    return _run(_query_processo_e_cliente(id_processo))  # type: ignore[no-any-return]


async def _query_processos_sem_movimentacao() -> list[ProcessoWorker]:
    limite_data = datetime.now(UTC) - timedelta(days=30)
    async with async_session_factory() as session:
        result = await session.execute(
            select(ProcessoModel)
            .where(
                ProcessoModel.monitoramento_ativo == True,  # noqa: E712
                ProcessoModel.status == "ativo",
                (ProcessoModel.data_ultimo_andamento == None)  # noqa: E711
                | (ProcessoModel.data_ultimo_andamento < limite_data),
            )
            .options(selectinload(ProcessoModel.cliente))
        )
        processos: list[ProcessoWorker] = []
        for p in result.scalars().all():
            c = p.cliente
            if c is None:
                continue
            processos.append(
                ProcessoWorker(
                    id=p.id,
                    numero_cnj=p.numero_cnj,
                    cliente_id=p.cliente_id,
                    escritorio_id=p.escritorio_id,
                    cliente=ClienteWorker(
                        id=c.id,
                        nome=c.nome,
                        telefone=c.telefone_whatsapp,
                        escritorio_id=c.escritorio_id,
                    ),
                )
            )
        return processos


def query_processos_sem_movimentacao() -> list[ProcessoWorker]:
    """
    SELECT processos sem andamento nos últimos 30 dias
    (monitoramento_ativo=true, status='ativo').
    Cada ProcessoWorker traz .cliente preenchido.
    """
    return _run(_query_processos_sem_movimentacao())  # type: ignore[no-any-return]


async def _query_clientes_para_pesquisa() -> list[ClienteWorker]:
    async with async_session_factory() as session:
        result = await session.execute(
            select(ClienteModel).where(
                ClienteModel.ativo == True,  # noqa: E712
                ClienteModel.aceite_lgpd == True,  # noqa: E712
            )
        )
        return [
            ClienteWorker(
                id=c.id,
                nome=c.nome,
                telefone=c.telefone_whatsapp,
                escritorio_id=c.escritorio_id,
            )
            for c in result.scalars().all()
        ]


def query_clientes_para_pesquisa() -> list[ClienteWorker]:
    """SELECT clientes ativos com aceite_lgpd=true para pesquisa de satisfação."""
    return _run(_query_clientes_para_pesquisa())  # type: ignore[no-any-return]


async def _query_clientes_ativos_por_escritorio(
    escritorio_id: int,
) -> list[ClienteWorker]:
    async with async_session_factory() as session:
        result = await session.execute(
            select(ClienteModel).where(
                ClienteModel.escritorio_id == escritorio_id,
                ClienteModel.ativo == True,  # noqa: E712
            )
        )
        return [
            ClienteWorker(
                id=c.id,
                nome=c.nome,
                telefone=c.telefone_whatsapp,
                escritorio_id=c.escritorio_id,
            )
            for c in result.scalars().all()
        ]


def query_clientes_ativos_por_escritorio(
    escritorio_id: int,
) -> list[ClienteWorker]:
    """SELECT clientes ativos de um escritório específico (para boas-vindas em lote)."""
    return _run(_query_clientes_ativos_por_escritorio(escritorio_id))  # type: ignore[no-any-return]


# ===========================================================================
# ENVIO WHATSAPP  (mensagens_relacionamento.py)
# ===========================================================================


async def _enviar_mensagem_whatsapp(id_cliente: int, telefone: str, texto: str) -> None:
    from feature_1_ia_personalizada.services.messaging.evolution_client import (
        EvolutionClient,
    )
    from shared.config.settings import settings

    # Resolve o webhook_whatsapp_instance do escritório do cliente em uma query
    async with async_session_factory() as session:
        result = await session.execute(
            select(Escritorio.webhook_whatsapp_instance)
            .join(ClienteModel, ClienteModel.escritorio_id == Escritorio.id)
            .where(ClienteModel.id == id_cliente)
        )
        instance = result.scalar_one_or_none()

    if not instance:
        logger.warning(
            "instancia_whatsapp_nao_configurada",
            id_cliente=id_cliente,
            telefone=telefone,
        )
        return

    client = EvolutionClient(
        base_url=settings.EVOLUTION_API_URL,
        api_key=settings.EVOLUTION_API_KEY,
    )
    try:
        await client.enviar_texto(instance, telefone, texto)
    finally:
        await client.close()


def enviar_mensagem_whatsapp(id_cliente: int, telefone: str, texto: str) -> None:
    """
    Resolve o escritório do cliente, obtém o webhook_whatsapp_instance
    e envia a mensagem via EvolutionClient.enviar_texto.
    Loga aviso e retorna silenciosamente se a instância não estiver configurada.
    """
    _run(_enviar_mensagem_whatsapp(id_cliente, telefone, texto))
