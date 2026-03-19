from decimal import Decimal
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from shared.models.interacao import Interacao


class CalculadoraAnalytics:
    """
    Agrupa funções e métricas de Analytics focadas na retenção e 
    satisfação de clientes (NPS), e no controle de custos e tempo.
    """

    MINUTOS_POR_INTERACAO = 8  # benchmark de tempo para resposta humana manual

    def __init__(self, db: AsyncSession, escritorio_id: int):
        self.db = db
        self.escritorio_id = escritorio_id

    async def obter_resumo(self) -> dict:
        """Calcula o resumo geral (interações, clientes_ativos, NPS)."""
        # Total de interações
        stmt_count = select(func.count(Interacao.id)).where(Interacao.escritorio_id == self.escritorio_id)
        total_interacoes = await self.db.scalar(stmt_count) or 0

        # Clientes ativos (distintos que tiveram interação)
        stmt_clientes = select(func.count(func.distinct(Interacao.cliente_id))).where(
            Interacao.escritorio_id == self.escritorio_id
        )
        clientes_ativos = await self.db.scalar(stmt_clientes) or 0

        # NPS médio
        stmt_nps = select(func.avg(Interacao.satisfacao)).where(
            Interacao.escritorio_id == self.escritorio_id,
            Interacao.satisfacao.is_not(None)
        )
        nps_medio_raw = await self.db.scalar(stmt_nps)
        nps_medio = round(float(nps_medio_raw), 1) if nps_medio_raw else 0.0

        return {
            "total_interacoes": total_interacoes,
            "clientes_ativos": clientes_ativos,
            "nps_medio": nps_medio,
            "nps_anterior": 0.0, # placeholder para MVP
            "variacao_nps": "+0.0" # placeholder para MVP
        }

    async def obter_eficiencia(self) -> dict:
        """Calcula as métricas de conversão e economia de horas da equipe."""
        # Tempo de resposta médio
        stmt_tempo = select(func.avg(Interacao.tempo_resposta_ms)).where(
            Interacao.escritorio_id == self.escritorio_id,
            Interacao.tempo_resposta_ms.is_not(None)
        )
        tempo_medio_raw = await self.db.scalar(stmt_tempo)
        tempo_resposta_medio_ms = int(tempo_medio_raw) if tempo_medio_raw else 0

        # Interações feitas de forma autônoma pela IA (saídas sem humano)
        stmt_ia = select(func.count(Interacao.id)).where(
            Interacao.escritorio_id == self.escritorio_id,
            Interacao.direcao == "saida"
        )
        interacoes_sem_humano = await self.db.scalar(stmt_ia) or 0

        # Economia em horas
        horas_economizadas_estimadas = (interacoes_sem_humano * self.MINUTOS_POR_INTERACAO) / 60.0

        # Percentual autonomia (exemplo hipotético, assumindo total de saídas como ref)
        percentual_autonomia = 100.0 if interacoes_sem_humano > 0 else 0.0

        # Custo
        stmt_custos = select(func.sum(Interacao.custo_estimado)).where(
            Interacao.escritorio_id == self.escritorio_id
        )
        custo_total_usd = await self.db.scalar(stmt_custos) or Decimal("0.0")

        return {
            "tempo_resposta_medio_ms": tempo_resposta_medio_ms,
            "interacoes_sem_humano": interacoes_sem_humano,
            "percentual_autonomia": round(percentual_autonomia, 1),
            "horas_economizadas_estimadas": round(horas_economizadas_estimadas, 1),
            "custo_total_usd": round(float(custo_total_usd), 2)
        }
