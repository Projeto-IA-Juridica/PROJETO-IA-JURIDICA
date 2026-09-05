"""
feature_1_ia_personalizada/services/relacionamento/relatorio_cliente.py
========================================================================
Relatório de acompanhamento de um cliente específico.

Reúne, em um texto pronto para enviar, o que o cliente corporativo quer saber:
situação dos processos dele, andamentos recentes, próximos prazos e um resumo
do atendimento no período.

Duas escolhas guiam o conteúdo:

- **É um documento que o cliente pode ler.** Por isso nada de score de risco,
  classificação de relacionamento ou anotação interna — esses são dados do
  escritório sobre o cliente, não para o cliente.
- **Nenhuma promessa de resultado.** Compliance OAB: o relatório descreve o que
  aconteceu, sem prognóstico. O resumo das conversas vem do serviço de
  sumarização, cujo prompt já proíbe opinião jurídica.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from feature_1_ia_personalizada.services.relacionamento.resumo_conversa import (
    resumir_conversa,
)
from shared.models.cliente import Cliente
from shared.models.interacao import Interacao
from shared.models.processo import Processo

logger = structlog.get_logger(__name__)

DIAS_PADRAO = 30
JANELA_PRAZOS = 30


@dataclass
class RelatorioCliente:
    cliente_id: int
    cliente_nome: str
    periodo_dias: int
    gerado_em: datetime
    processos: list[dict[str, Any]] = field(default_factory=list)
    prazos: list[dict[str, Any]] = field(default_factory=list)
    total_interacoes: int = 0
    resumo_atendimento: str = ""
    texto: str = ""


def _formatar(rel: RelatorioCliente, nome_escritorio: str) -> str:
    linhas = [
        "*RELATÓRIO DE ACOMPANHAMENTO*",
        f"{rel.cliente_nome}",
        f"Período: últimos {rel.periodo_dias} dias · {rel.gerado_em.strftime('%d/%m/%Y')}",
    ]

    if rel.processos:
        linhas += ["", f"*PROCESSOS ({len(rel.processos)})*"]
        for p in rel.processos:
            linhas.append(f"• {p['numero_cnj']} — {p['status']}")
            if p.get("fase"):
                linhas.append(f"  Fase: {p['fase']}")
            if p.get("ultimo_andamento"):
                quando = f" ({p['data_andamento']})" if p.get("data_andamento") else ""
                linhas.append(f"  Último andamento{quando}: {p['ultimo_andamento']}")
    else:
        linhas += ["", "*PROCESSOS*", "Nenhum processo ativo no período."]

    if rel.prazos:
        linhas += ["", f"*PRÓXIMOS PRAZOS ({len(rel.prazos)})*"]
        for pr in rel.prazos:
            aprox = "≈ " if pr.get("estimado") else ""
            linhas.append(f"• {aprox}{pr['data']} — {pr['descricao']}")

    linhas += [
        "",
        "*ATENDIMENTO*",
        f"{rel.total_interacoes} mensagens trocadas no período.",
    ]
    if rel.resumo_atendimento:
        linhas.append(rel.resumo_atendimento)

    linhas += ["", f"_{nome_escritorio}_"]
    return "\n".join(linhas)


async def gerar_relatorio(
    db: AsyncSession,
    claude: Any,
    cliente_id: int,
    escritorio_id: int,
    *,
    dias: int = DIAS_PADRAO,
    nome_escritorio: str = "",
    incluir_resumo: bool = True,
) -> RelatorioCliente | None:
    """
    Monta o relatório do cliente. Devolve None se o cliente não existir no
    escritório (ou estiver inativo).
    """
    cliente = (
        (
            await db.execute(
                select(Cliente).where(
                    Cliente.id == cliente_id,
                    Cliente.escritorio_id == escritorio_id,
                    Cliente.ativo.is_(True),
                )
            )
        )
        .scalars()
        .first()
    )
    if cliente is None:
        return None

    agora = datetime.now(UTC)
    desde = agora - timedelta(days=dias)
    hoje = agora.date()

    rel = RelatorioCliente(
        cliente_id=cliente.id,
        cliente_nome=cliente.nome,
        periodo_dias=dias,
        gerado_em=agora,
    )

    # Processos ativos
    processos = (
        (
            await db.execute(
                select(Processo)
                .where(
                    Processo.cliente_id == cliente_id,
                    Processo.escritorio_id == escritorio_id,
                    Processo.status == "ativo",
                )
                .order_by(Processo.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    rel.processos = [
        {
            "numero_cnj": p.numero_cnj,
            "status": p.status,
            "fase": p.fase_processual,
            "ultimo_andamento": p.ultimo_andamento,
            "data_andamento": (
                p.data_ultimo_andamento.strftime("%d/%m/%Y") if p.data_ultimo_andamento else None
            ),
        }
        for p in processos
    ]

    # Prazos do cliente na janela
    try:
        from feature_1_ia_personalizada.services.agendamento.prazos import (
            buscar_prazos_escritorio,
        )

        limite = hoje + timedelta(days=JANELA_PRAZOS)
        rel.prazos = [
            {
                "data": prazo.data.strftime("%d/%m/%Y"),
                "descricao": prazo.descricao,
                "estimado": getattr(prazo, "estimado", False),
            }
            for prazo in await buscar_prazos_escritorio(
                db, escritorio_id, cliente_id=cliente_id, hoje=hoje
            )
            if hoje <= prazo.data <= limite
        ]
    except Exception as exc:
        logger.warning(
            "relatorio_cliente.prazos_indisponiveis", cliente_id=cliente_id, erro=str(exc)
        )

    # Volume de atendimento
    rel.total_interacoes = (
        await db.execute(
            select(func.count())
            .select_from(Interacao)
            .where(
                Interacao.cliente_id == cliente_id,
                Interacao.escritorio_id == escritorio_id,
                Interacao.created_at >= desde,
            )
        )
    ).scalar() or 0

    # Resumo do atendimento (reutiliza o serviço de sumarização)
    if incluir_resumo and rel.total_interacoes:
        resumo = await resumir_conversa(
            db, claude, cliente_id, escritorio_id, cliente.nome, dias=dias
        )
        rel.resumo_atendimento = resumo.texto

    rel.texto = _formatar(rel, nome_escritorio or "Seu escritório")
    return rel
