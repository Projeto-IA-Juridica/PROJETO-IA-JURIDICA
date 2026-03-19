"""
feature_1_ia_personalizada/services/analytics/exportador.py
============================================================
Exportação de relatórios de interações em CSV.
Usa apenas a stdlib (csv, io) — sem dependências extras.
"""

import csv
import io
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models.interacao import Interacao


_CABECALHO_CSV = [
    "id",
    "data",
    "tipo",
    "direcao",
    "mensagem_cliente",
    "mensagem_ia",
    "tokens_input",
    "tokens_output",
    "custo_estimado_usd",
    "satisfacao_nps",
    "tempo_resposta_ms",
]


def _parse_mes_ano(mes_ano: str) -> tuple[datetime, datetime]:
    """
    Converte 'YYYY-MM' em (inicio_mes, inicio_mes_seguinte) UTC.
    Levanta ValueError se o formato for inválido.
    """
    try:
        dt = datetime.strptime(mes_ano, "%Y-%m")
    except ValueError:
        raise ValueError(f"Formato inválido para 'mes': esperado YYYY-MM, recebido {mes_ano!r}")

    inicio = dt.replace(tzinfo=timezone.utc)
    # Avança para o primeiro dia do mês seguinte
    if inicio.month == 12:
        fim = inicio.replace(year=inicio.year + 1, month=1)
    else:
        fim = inicio.replace(month=inicio.month + 1)

    return inicio, fim


class ExportadorAnalytics:
    def __init__(self, db: AsyncSession, escritorio_id: int):
        self.db = db
        self.escritorio_id = escritorio_id

    async def gerar_csv(self, mes_ano: str) -> bytes:
        """
        Exporta todas as interações do mês indicado em formato CSV.

        Args:
            mes_ano: Mês no formato 'YYYY-MM' (ex: '2026-03').

        Returns:
            Bytes do arquivo CSV com encoding UTF-8-BOM (compatível com Excel).
        """
        inicio, fim = _parse_mes_ano(mes_ano)

        stmt = (
            select(
                Interacao.id,
                Interacao.created_at,
                Interacao.tipo,
                Interacao.direcao,
                Interacao.mensagem_cliente,
                Interacao.mensagem_ia,
                Interacao.tokens_input,
                Interacao.tokens_output,
                Interacao.custo_estimado,
                Interacao.satisfacao,
                Interacao.tempo_resposta_ms,
            )
            .where(
                Interacao.escritorio_id == self.escritorio_id,
                Interacao.created_at >= inicio,
                Interacao.created_at < fim,
            )
            .order_by(Interacao.created_at.asc())
        )
        result = await self.db.execute(stmt)
        rows = result.all()

        buffer = io.StringIO()
        writer = csv.writer(buffer, quoting=csv.QUOTE_ALL)
        writer.writerow(_CABECALHO_CSV)

        for row in rows:
            writer.writerow([
                row.id,
                row.created_at.isoformat() if row.created_at else "",
                row.tipo,
                row.direcao,
                row.mensagem_cliente or "",
                row.mensagem_ia or "",
                row.tokens_input,
                row.tokens_output,
                float(row.custo_estimado) if row.custo_estimado is not None else 0.0,
                row.satisfacao if row.satisfacao is not None else "",
                row.tempo_resposta_ms if row.tempo_resposta_ms is not None else "",
            ])

        # UTF-8-BOM para compatibilidade com Excel
        return buffer.getvalue().encode("utf-8-sig")
