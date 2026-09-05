"""
feature_1_ia_personalizada/services/relacionamento/alerta_risco.py
===================================================================
Avisa o advogado responsável quando a IA classifica um cliente como em risco.

Roda logo depois da análise de CRM: se o relacionamento foi classificado como
`em_risco` ou `critico`, o advogado dono da conta recebe uma mensagem no
WhatsApp com o resumo e a ação sugerida — para agir antes de perder o cliente.

Duas decisões que evitam que isso vire ruído:

- **Só piora alerta.** A análise roda de novo a cada conversa nova; um cliente
  que continua no mesmo nível não gera aviso repetido (trava por cliente+nível,
  em `notificador.chave_alerta_risco`). Uma piora de `em_risco` para `critico`
  usa outra chave e alerta na hora.
- **Sem responsável, sem alerta.** Mandar para "todo mundo" transformaria o
  aviso em spam e ninguém assumiria a ação. Fica registrado no log para a
  carteira ser atribuída.
"""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from feature_1_ia_personalizada.services.relacionamento.notificador import (
    chave_alerta_risco,
    notificar_advogado,
)
from feature_1_ia_personalizada.services.relacionamento.responsavel import (
    resolver_responsavel,
)
from shared.models.cliente import Cliente
from shared.models.escritorio import Escritorio

logger = structlog.get_logger(__name__)

# Níveis que disparam alerta, do pior para o menos grave.
NIVEIS_DE_RISCO = ("critico", "em_risco")

_ROTULO = {
    "critico": "CRÍTICO",
    "em_risco": "EM RISCO",
}


def montar_mensagem(
    cliente_nome: str,
    nivel: str,
    score: int,
    resumo: str | None,
    acao_sugerida: str | None,
) -> str:
    """Monta o texto do alerta. Separado para poder ser testado sem I/O."""
    linhas = [
        f"⚠️ *CLIENTE {_ROTULO.get(nivel, nivel.upper())}*",
        "",
        f"*{cliente_nome}* — relacionamento {score}/100",
    ]
    if resumo:
        linhas += ["", f"_{resumo}_"]
    if acao_sugerida:
        linhas += ["", f"*Ação sugerida:* {acao_sugerida}"]
    linhas += ["", "_Análise automática do CRM._"]
    return "\n".join(linhas)


async def alertar_se_em_risco(
    db: AsyncSession,
    cliente_id: int,
    escritorio_id: int,
    nivel: str,
    score: int,
    *,
    redis: Any = None,
) -> bool:
    """
    Envia o alerta se o nível for de risco. Devolve True se alertou.

    Nunca levanta: é um efeito colateral da análise de CRM e não pode fazer a
    análise (já persistida) parecer que falhou.
    """
    if nivel not in NIVEIS_DE_RISCO:
        return False

    try:
        cliente = (
            (
                await db.execute(
                    select(Cliente).where(
                        Cliente.id == cliente_id,
                        Cliente.escritorio_id == escritorio_id,
                    )
                )
            )
            .scalars()
            .first()
        )
        if cliente is None:
            return False

        advogado = await resolver_responsavel(db, cliente)
        if advogado is None:
            logger.info(
                "alerta_risco.sem_responsavel_definido",
                cliente_id=cliente_id,
                nivel=nivel,
            )
            return False

        instancia = (
            await db.execute(
                select(Escritorio.webhook_whatsapp_instance).where(Escritorio.id == escritorio_id)
            )
        ).scalar_one_or_none()

        texto = montar_mensagem(
            cliente_nome=cliente.nome,
            nivel=nivel,
            score=score,
            resumo=cliente.crm_resumo,
            acao_sugerida=cliente.crm_acao_sugerida,
        )

        enviado = await notificar_advogado(
            advogado,
            instancia,
            texto,
            redis=redis,
            chave_trava=chave_alerta_risco(cliente_id, nivel),
        )
        if enviado:
            logger.info(
                "alerta_risco.enviado",
                cliente_id=cliente_id,
                advogado_id=advogado.id,
                nivel=nivel,
            )
        return enviado

    except Exception as exc:
        logger.warning("alerta_risco.falhou", cliente_id=cliente_id, erro=str(exc))
        return False
