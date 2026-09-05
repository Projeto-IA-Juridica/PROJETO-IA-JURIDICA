"""
feature_1_ia_personalizada/services/relacionamento/agenda_diaria.py
====================================================================
"O seu dia em uma mensagem" — o que exige atenção do advogado hoje.

Reúne, por advogado, três sinais que já existiam espalhados pelo sistema e que
antes só apareciam se alguém abrisse a tela certa:

  1. Prazos processuais próximos (dos processos dele)
  2. Reuniões confirmadas para hoje
  3. Clientes que a IA classificou como em risco

O corte é sempre a **carteira do advogado** — cada um recebe só o que é seu,
resolvido por `responsavel.clientes_por_responsavel`. Advogado sem nada de
relevante não recebe mensagem: um "bom dia, nada para hoje" diário treina a
equipe a ignorar o aviso.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from feature_1_ia_personalizada.services.relacionamento.responsavel import (
    clientes_por_responsavel,
)
from shared.models.agendamento import Agendamento
from shared.models.cliente import Cliente

logger = structlog.get_logger(__name__)

# Janela de prazos incluída no aviso. Uma semana é curto o bastante para ser
# acionável e longo o bastante para dar tempo de reagir.
DIAS_DE_PRAZO = 7

NIVEIS_DE_RISCO = ("critico", "em_risco")


@dataclass
class ItemAgenda:
    prazos: list[Any] = field(default_factory=list)
    reunioes: list[Agendamento] = field(default_factory=list)
    clientes_em_risco: list[Cliente] = field(default_factory=list)

    @property
    def vazio(self) -> bool:
        return not (self.prazos or self.reunioes or self.clientes_em_risco)


def _fuso(timezone_escritorio: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_escritorio or "America/Sao_Paulo")
    except Exception:
        return ZoneInfo("America/Sao_Paulo")


def montar_mensagem(
    nome_advogado: str, item: ItemAgenda, hoje: date, nomes_clientes: dict[int, str]
) -> str:
    """Monta o texto do aviso diário. Sem I/O, para poder ser testado direto."""
    partes = [
        f"☀️ *SEU DIA — {hoje.strftime('%d/%m')}*",
        f"Bom dia, {nome_advogado.split()[0]}!",
    ]

    if item.prazos:
        linhas = []
        for prazo in sorted(item.prazos, key=lambda p: p.data):
            quando = "HOJE" if prazo.data == hoje else prazo.data.strftime("%d/%m")
            aprox = "≈ " if getattr(prazo, "estimado", False) else ""
            cliente = nomes_clientes.get(prazo.cliente_id, "cliente")
            linhas.append(f"• {aprox}{quando} — {cliente}: {prazo.descricao}")
        partes += ["", f"*PRAZOS ({len(item.prazos)})*", *linhas]

    if item.reunioes:
        linhas = []
        for reuniao in sorted(
            item.reunioes, key=lambda r: r.data_hora_inicio or datetime.max.replace(tzinfo=UTC)
        ):
            hora = reuniao.data_hora_inicio.strftime("%H:%M") if reuniao.data_hora_inicio else "--"
            cliente = nomes_clientes.get(reuniao.cliente_id, "cliente")
            linhas.append(f"• {hora} — {cliente}")
        partes += ["", f"*REUNIÕES HOJE ({len(item.reunioes)})*", *linhas]

    if item.clientes_em_risco:
        linhas = [
            f"• {c.nome} ({c.crm_score}/100)"
            for c in sorted(item.clientes_em_risco, key=lambda c: c.crm_score or 0)
        ]
        partes += ["", f"*CLIENTES EM RISCO ({len(item.clientes_em_risco)})*", *linhas]

    return "\n".join(partes)


async def montar_agenda_do_escritorio(
    db: AsyncSession,
    escritorio_id: int,
    hoje: date | None = None,
    timezone_escritorio: str | None = None,
) -> dict[int, ItemAgenda]:
    """
    Monta a agenda de cada advogado do escritório.

    Devolve `{advogado_id: ItemAgenda}` já sem os advogados que não têm nada
    para hoje.
    """
    from feature_1_ia_personalizada.services.agendamento.prazos import (
        buscar_prazos_escritorio,
    )

    tz = _fuso(timezone_escritorio)
    hoje = hoje or datetime.now(tz).date()
    limite_prazo = hoje + timedelta(days=DIAS_DE_PRAZO)

    carteiras = await clientes_por_responsavel(db, escritorio_id)
    if not carteiras:
        return {}

    # cliente_id -> advogado_id, para distribuir prazos e reuniões
    dono: dict[int, int] = {}
    for advogado_id, clientes in carteiras.items():
        for cliente in clientes:
            dono[cliente.id] = advogado_id

    agendas: dict[int, ItemAgenda] = {aid: ItemAgenda() for aid in carteiras}

    # 1. Prazos da janela
    try:
        for prazo in await buscar_prazos_escritorio(db, escritorio_id, hoje=hoje):
            if hoje <= prazo.data <= limite_prazo:
                dono_do_prazo = dono.get(prazo.cliente_id)
                if dono_do_prazo is not None:
                    agendas[dono_do_prazo].prazos.append(prazo)
    except Exception as exc:
        # Um parser de prazo com problema não pode zerar a agenda inteira.
        logger.warning("agenda_diaria.prazos_indisponiveis", erro=str(exc))

    # 2. Reuniões confirmadas para hoje
    inicio_dia = datetime.combine(hoje, datetime.min.time(), tzinfo=tz)
    reunioes = (
        (
            await db.execute(
                select(Agendamento).where(
                    Agendamento.escritorio_id == escritorio_id,
                    Agendamento.status == "confirmado",
                    Agendamento.data_hora_inicio >= inicio_dia,
                    Agendamento.data_hora_inicio < inicio_dia + timedelta(days=1),
                )
            )
        )
        .scalars()
        .all()
    )
    for reuniao in reunioes:
        dono_da_reuniao = dono.get(reuniao.cliente_id)
        if dono_da_reuniao is not None:
            agendas[dono_da_reuniao].reunioes.append(reuniao)

    # 3. Clientes em risco na carteira
    for advogado_id, clientes in carteiras.items():
        agendas[advogado_id].clientes_em_risco = [
            c for c in clientes if c.crm_nivel in NIVEIS_DE_RISCO
        ]

    return {aid: item for aid, item in agendas.items() if not item.vazio}
