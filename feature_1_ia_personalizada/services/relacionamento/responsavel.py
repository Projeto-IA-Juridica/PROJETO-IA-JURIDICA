"""
feature_1_ia_personalizada/services/relacionamento/responsavel.py
==================================================================
Descobre qual advogado responde por um cliente.

A responsabilidade pode estar gravada em dois lugares, e nem sempre está
preenchida — carteiras importadas por CSV antigo, por exemplo, não têm dono
definido. A resolução segue uma ordem de precedência:

  1. `Cliente.advogado_responsavel_id` — atribuição explícita, tem prioridade
  2. Responsável do processo ativo mais recente do cliente
  3. Nenhum — o chamador decide o que fazer (normalmente: não notificar)

Só devolve advogados **ativos e com WhatsApp cadastrado**, porque todo consumidor
deste módulo quer mandar mensagem para alguém. Um advogado desativado ou sem
número resolve para o próximo da precedência.
"""

from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models.cliente import Cliente
from shared.models.processo import Processo
from shared.models.usuario import Usuario

logger = structlog.get_logger(__name__)


async def _advogado_notificavel(
    db: AsyncSession, usuario_id: int | None, escritorio_id: int
) -> Usuario | None:
    """Carrega o usuário se ele puder receber mensagem."""
    if usuario_id is None:
        return None
    stmt = select(Usuario).where(
        Usuario.id == usuario_id,
        Usuario.escritorio_id == escritorio_id,
        Usuario.ativo.is_(True),
        Usuario.whatsapp_numero.is_not(None),
    )
    return (await db.execute(stmt)).scalars().first()


async def resolver_responsavel(db: AsyncSession, cliente: Cliente) -> Usuario | None:
    """
    Devolve o advogado responsável pelo cliente, ou None se não houver
    ninguém notificável.
    """
    direto = await _advogado_notificavel(db, cliente.advogado_responsavel_id, cliente.escritorio_id)
    if direto is not None:
        return direto

    # Fallback: responsável do processo ativo mais recente.
    stmt = (
        select(Processo.advogado_responsavel_id)
        .where(
            Processo.cliente_id == cliente.id,
            Processo.escritorio_id == cliente.escritorio_id,
            Processo.advogado_responsavel_id.is_not(None),
        )
        .order_by(Processo.status == "ativo", Processo.created_at.desc())
        .limit(1)
    )
    via_processo = (await db.execute(stmt)).scalars().first()
    advogado = await _advogado_notificavel(db, via_processo, cliente.escritorio_id)

    if advogado is None:
        logger.info(
            "relacionamento.sem_responsavel",
            cliente_id=cliente.id,
            escritorio_id=cliente.escritorio_id,
        )
    return advogado


async def clientes_por_responsavel(
    db: AsyncSession, escritorio_id: int
) -> dict[int, list[Cliente]]:
    """
    Agrupa os clientes ativos do escritório por advogado responsável.

    Feito em duas queries (clientes + responsáveis de processo) em vez de uma
    resolução por cliente, porque a agenda diária percorre a carteira inteira.
    Clientes sem responsável notificável ficam de fora do resultado.
    """
    clientes = (
        (
            await db.execute(
                select(Cliente).where(
                    Cliente.escritorio_id == escritorio_id,
                    Cliente.ativo.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )
    if not clientes:
        return {}

    # Responsável por processo, para os clientes sem atribuição direta.
    sem_direto = [c.id for c in clientes if c.advogado_responsavel_id is None]
    por_processo: dict[int, int] = {}
    if sem_direto:
        linhas = (
            await db.execute(
                select(Processo.cliente_id, Processo.advogado_responsavel_id)
                .where(
                    Processo.cliente_id.in_(sem_direto),
                    Processo.escritorio_id == escritorio_id,
                    Processo.advogado_responsavel_id.is_not(None),
                )
                .order_by(Processo.created_at.desc())
            )
        ).all()
        for cliente_id, advogado_id in linhas:
            por_processo.setdefault(cliente_id, advogado_id)

    # Um único carregamento dos advogados notificáveis do escritório.
    notificaveis = {
        u.id: u
        for u in (
            await db.execute(
                select(Usuario).where(
                    Usuario.escritorio_id == escritorio_id,
                    Usuario.ativo.is_(True),
                    Usuario.whatsapp_numero.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    }

    agrupado: dict[int, list[Cliente]] = {}
    for cliente in clientes:
        advogado_id = cliente.advogado_responsavel_id or por_processo.get(cliente.id)
        if advogado_id in notificaveis:
            agrupado.setdefault(advogado_id, []).append(cliente)
    return agrupado
