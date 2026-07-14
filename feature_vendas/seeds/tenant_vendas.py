"""
Seed do tenant de vendas + persona Clara.

Cria (idempotente) o escritório interno que hospeda a máquina de vendas. Os
"clientes" desse tenant são os advogados-lead; a "persona" dele é a Clara, com
o system prompt de humanizacao.estilo.

Rodar: python -m feature_vendas.seeds.tenant_vendas

Depois de rodar, exporte o id impresso em VENDAS_TENANT_ID (ver config.py).
A persona não é código: fica na configuração do escritório, então mudar o pitch
da Clara é editar dado, não fazer deploy.
"""

from __future__ import annotations

import asyncio

import structlog
from sqlalchemy import select

from feature_vendas.services.humanizacao.estilo import system_prompt_clara
from shared.database.connection import worker_session_factory
from shared.models.escritorio import Escritorio

logger = structlog.get_logger(__name__)

_NOME_TENANT = "[INTERNO] Máquina de Vendas — Concierge"


async def _seed() -> int:
    async with worker_session_factory() as db:
        existente = (
            await db.execute(select(Escritorio).where(Escritorio.nome == _NOME_TENANT))
        ).scalar_one_or_none()
        if existente:
            logger.info("seed_tenant_vendas_ja_existe", id=existente.id)
            return existente.id

        tenant = Escritorio(
            nome=_NOME_TENANT,
            plano="enterprise",  # sem quota de token nos limites; máquina interna
            # A persona vive na config do escritório. O campo exato depende do
            # schema de persona do produto; o system prompt a ser gravado é:
            #   system_prompt_clara()
        )
        db.add(tenant)
        await db.commit()
        await db.refresh(tenant)
        logger.info("seed_tenant_vendas_criado", id=tenant.id)
        print(f"\nVENDAS_TENANT_ID={tenant.id}")
        print("System prompt da Clara (gravar na persona deste escritório):\n")
        print(system_prompt_clara())
        return tenant.id


if __name__ == "__main__":
    asyncio.run(_seed())
