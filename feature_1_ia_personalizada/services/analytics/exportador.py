"""
feature_1_ia_personalizada/services/analytics/exportador.py
============================================================
Exportação de relatório executivo do advogado em CSV.
Uma linha por cliente — foco no que gera valor para o advogado.
"""

import csv
import io
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models.cliente import Cliente
from shared.models.interacao import Interacao
from shared.models.processo import Processo

_VALOR_HORA_ADV_BRL = 350.0
_MIN_POR_INTERACAO = 3.0

_CABECALHO_CSV = [
    "Cliente",
    "Processo (CNJ)",
    "Tipo de Ação",
    "Risco",
    "Último Andamento",
    "Data do Andamento",
    "Satisfação",
    "Economia Estimada no Mês",
]


def _parse_mes_ano(mes_ano: str) -> tuple[datetime, datetime]:
    try:
        dt = datetime.strptime(mes_ano, "%Y-%m")
    except ValueError as e:
        raise ValueError(
            f"Formato inválido para 'mes': esperado YYYY-MM, recebido {mes_ano!r}"
        ) from e

    inicio = dt.replace(tzinfo=UTC)
    fim = inicio.replace(year=inicio.year + 1, month=1) if inicio.month == 12 \
        else inicio.replace(month=inicio.month + 1)
    return inicio, fim


def _fmt_brl(valor: float) -> str:
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


class ExportadorAnalytics:
    def __init__(self, db: AsyncSession, escritorio_id: int):
        self.db = db
        self.escritorio_id = escritorio_id

    async def gerar_csv(self, mes_ano: str) -> bytes:
        inicio, fim = _parse_mes_ano(mes_ano)

        # Clientes do escritório
        clientes_result = await self.db.execute(
            select(Cliente.id, Cliente.nome)
            .where(Cliente.escritorio_id == self.escritorio_id)
            .order_by(Cliente.nome.asc())
        )
        clientes = clientes_result.all()

        if not clientes:
            buf = io.StringIO()
            csv.writer(buf, quoting=csv.QUOTE_ALL).writerow(_CABECALHO_CSV)
            return buf.getvalue().encode("utf-8-sig")

        cliente_ids = [c.id for c in clientes]

        # Processo ativo mais recente por cliente
        sub = (
            select(Processo.cliente_id, func.max(Processo.id).label("max_id"))
            .where(
                Processo.escritorio_id == self.escritorio_id,
                Processo.cliente_id.in_(cliente_ids),
                Processo.status == "ativo",
            )
            .group_by(Processo.cliente_id)
            .subquery()
        )
        proc_result = await self.db.execute(
            select(
                Processo.cliente_id,
                Processo.numero_cnj,
                Processo.tipo_acao,
                Processo.score_nivel,
                Processo.ultimo_andamento,
                Processo.data_ultimo_andamento,
            )
            .join(sub, (Processo.cliente_id == sub.c.cliente_id) & (Processo.id == sub.c.max_id))
        )
        processos = {row.cliente_id: row for row in proc_result.all()}

        # Interações da IA no mês: contagem e NPS médio por cliente
        int_result = await self.db.execute(
            select(
                Interacao.cliente_id,
                func.count(Interacao.id).label("total"),
                func.avg(Interacao.satisfacao).label("nps_medio"),
            )
            .where(
                Interacao.escritorio_id == self.escritorio_id,
                Interacao.cliente_id.in_(cliente_ids),
                Interacao.created_at >= inicio,
                Interacao.created_at < fim,
                Interacao.direcao == "saida",
            )
            .group_by(Interacao.cliente_id)
        )
        interacoes = {row.cliente_id: row for row in int_result.all()}

        # Montar CSV
        buf = io.StringIO()
        writer = csv.writer(buf, quoting=csv.QUOTE_ALL)
        writer.writerow(_CABECALHO_CSV)

        for cliente in clientes:
            proc = processos.get(cliente.id)
            ints = interacoes.get(cliente.id)

            cnj = proc.numero_cnj if proc else "Sem processo"
            tipo = proc.tipo_acao or "—" if proc else "—"
            risco = (proc.score_nivel or "—").capitalize() if proc else "—"
            andamento = (proc.ultimo_andamento or "Sem andamentos") if proc else "—"
            data_and = (
                proc.data_ultimo_andamento.strftime("%d/%m/%Y")
                if proc and proc.data_ultimo_andamento else "—"
            )

            nps = float(ints.nps_medio) if ints and ints.nps_medio is not None else None
            if nps is None:
                satisfacao = "N/D"
            elif nps >= 4.0:
                satisfacao = "Satisfeito"
            elif nps >= 3.0:
                satisfacao = "Neutro"
            else:
                satisfacao = "Insatisfeito"

            total_msgs = ints.total if ints else 0
            horas = round(total_msgs * _MIN_POR_INTERACAO / 60, 1)
            economia = _fmt_brl(round(horas * _VALOR_HORA_ADV_BRL, 2))

            writer.writerow([
                cliente.nome,
                cnj,
                tipo,
                risco,
                andamento,
                data_and,
                satisfacao,
                economia,
            ])

        return buf.getvalue().encode("utf-8-sig")
