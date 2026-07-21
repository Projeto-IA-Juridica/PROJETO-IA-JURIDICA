from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models.cliente import Cliente
from shared.models.interacao import Interacao


class CalculadoraAnalytics:
    """
    Agrupa funções e métricas de Analytics focadas na retenção e
    relacionamento com clientes (score CRM classificado pela IA),
    e no controle de custos e tempo.
    """

    MINUTOS_POR_INTERACAO = 8  # benchmark de tempo para resposta humana manual

    def __init__(self, db: AsyncSession, escritorio_id: int, dias: int = 30):
        self.db = db
        self.escritorio_id = escritorio_id
        self.dias = dias

        agora = datetime.now(UTC)
        self.dt_inicio = agora - timedelta(days=dias)
        self.dt_inicio_anterior = agora - timedelta(days=dias * 2)

    async def obter_resumo(self) -> dict:
        """Calcula o resumo geral (interações, clientes_ativos, score CRM) no período."""
        total_interacoes = await self._total_interacoes_periodo()

        # Clientes únicos ativos no período
        stmt_clientes = select(func.count(func.distinct(Interacao.cliente_id))).where(
            Interacao.escritorio_id == self.escritorio_id,
            Interacao.created_at >= self.dt_inicio,
        )
        clientes_ativos = await self.db.scalar(stmt_clientes) or 0

        # Score CRM médio — relacionamento classificado pela IA (0-100)
        stmt_score = select(
            func.avg(Cliente.crm_score).label("score_medio"),
            func.count(Cliente.crm_score).label("analisados"),
        ).where(
            Cliente.escritorio_id == self.escritorio_id,
            Cliente.ativo.is_(True),
            Cliente.crm_score.is_not(None),
        )
        row_score = (await self.db.execute(stmt_score)).one()
        score_crm_medio = (
            round(float(row_score.score_medio), 1) if row_score.score_medio is not None else None
        )

        return {
            "total_interacoes": total_interacoes,
            "clientes_ativos": clientes_ativos,
            "score_crm_medio": score_crm_medio,
            "clientes_analisados": row_score.analisados or 0,
        }

    async def _total_interacoes_periodo(self) -> int:
        """Query base de contagem — reutilizada por obter_resumo e obter_eficiencia."""
        stmt = select(func.count(Interacao.id)).where(
            Interacao.escritorio_id == self.escritorio_id,
            Interacao.created_at >= self.dt_inicio,
        )
        return await self.db.scalar(stmt) or 0

    async def obter_eficiencia(self) -> dict:
        """Calcula as métricas de conversão e economia de horas da equipe."""
        # Tempo de resposta médio no período
        stmt_tempo = select(func.avg(Interacao.tempo_resposta_ms)).where(
            Interacao.escritorio_id == self.escritorio_id,
            Interacao.tempo_resposta_ms.is_not(None),
            Interacao.created_at >= self.dt_inicio,
        )
        tempo_medio_raw = await self.db.scalar(stmt_tempo)
        tempo_resposta_medio_ms = int(tempo_medio_raw) if tempo_medio_raw else 0

        total_interacoes = await self._total_interacoes_periodo()

        # Interações autônomas da IA (saídas no período)
        stmt_ia = select(func.count(Interacao.id)).where(
            Interacao.escritorio_id == self.escritorio_id,
            Interacao.direcao == "saida",
            Interacao.created_at >= self.dt_inicio,
        )
        interacoes_sem_humano = await self.db.scalar(stmt_ia) or 0

        horas_economizadas_estimadas = (interacoes_sem_humano * self.MINUTOS_POR_INTERACAO) / 60.0
        percentual_autonomia = (
            (interacoes_sem_humano / total_interacoes * 100.0) if total_interacoes > 0 else 0.0
        )

        # Custo total no período
        stmt_custos = select(func.sum(Interacao.custo_estimado)).where(
            Interacao.escritorio_id == self.escritorio_id,
            Interacao.created_at >= self.dt_inicio,
        )
        custo_total_usd = await self.db.scalar(stmt_custos) or Decimal("0.0")

        return {
            "tempo_resposta_medio_ms": tempo_resposta_medio_ms,
            "interacoes_sem_humano": interacoes_sem_humano,
            "percentual_autonomia": round(percentual_autonomia, 1),
            "horas_economizadas_estimadas": round(horas_economizadas_estimadas, 1),
            "custo_total_usd": round(float(custo_total_usd), 2),
        }

    async def tendencia_semanal(self, semanas: int = 8) -> list[dict]:
        """
        Agrega interações por semana ISO para os últimos N semanas.
        Query única com date_trunc — performance garantida pelos índices de 5.1.
        """
        dt_inicio = datetime.now(UTC) - timedelta(weeks=semanas)

        from sqlalchemy import text

        stmt = (
            select(
                func.date_trunc("week", Interacao.created_at).label("semana"),
                func.count(Interacao.id).label("total_interacoes"),
                func.count(Interacao.id).filter(Interacao.direcao == "saida").label("saidas"),
            )
            .where(
                Interacao.escritorio_id == self.escritorio_id,
                Interacao.created_at >= dt_inicio,
            )
            .group_by(text("semana"))
            .order_by(text("semana"))
        )
        result = await self.db.execute(stmt)
        rows = result.all()

        tendencia = []
        for row in rows:
            total = row.total_interacoes or 0
            saidas = row.saidas or 0
            autonomia_pct = (saidas / total * 100.0) if total > 0 else 0.0
            tendencia.append(
                {
                    "semana": row.semana.strftime("%Y-W%W") if row.semana else "",
                    "total_interacoes": total,
                    "autonomia_pct": round(autonomia_pct, 1),
                }
            )
        return tendencia

    async def ranking_clientes(self, limite: int = 20) -> list[dict]:
        """
        Top N clientes por score CRM (piores primeiro) com identificação de risco.
        Clientes em risco: classificados pela IA como em_risco ou critico.
        """
        stmt = (
            select(
                Interacao.cliente_id,
                Cliente.nome,
                Cliente.crm_score,
                Cliente.crm_nivel,
                func.count(Interacao.id).label("total_interacoes"),
                func.max(Interacao.created_at).label("ultimo_contato"),
            )
            .join(Cliente, Interacao.cliente_id == Cliente.id)
            .where(
                Interacao.escritorio_id == self.escritorio_id,
                Interacao.created_at >= self.dt_inicio,
            )
            .group_by(Interacao.cliente_id, Cliente.nome, Cliente.crm_score, Cliente.crm_nivel)
            .order_by(Cliente.crm_score.asc().nulls_last())
            .limit(limite)
        )
        result = await self.db.execute(stmt)
        rows = result.all()

        ranking = []
        for row in rows:
            ultimo = row.ultimo_contato
            if ultimo is not None and ultimo.tzinfo is None:
                ultimo = ultimo.replace(tzinfo=UTC)
            ranking.append(
                {
                    "cliente_id": row.cliente_id,
                    "nome": row.nome,
                    "crm_score": row.crm_score,
                    "crm_nivel": row.crm_nivel,
                    "total_interacoes": row.total_interacoes,
                    "ultimo_contato": ultimo.isoformat() if ultimo else None,
                    "em_risco": row.crm_nivel in ("em_risco", "critico"),
                    # sem_analise: cliente ainda não classificado pela IA
                    "sem_analise": row.crm_nivel is None,
                }
            )
        return ranking
