"""
feature_1_ia_personalizada/services/crm/aggregator.py
=======================================================
CRMDataAggregator — coleta e agrega dados reais de um cliente para análise CRM.

Todas as queries são feitas em uma única passagem com JOINs otimizados (sem N+1).
Multi-tenant: sempre filtra por escritorio_id.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models.cliente import Cliente
from shared.models.interacao import Interacao
from shared.models.processo import Processo

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Dataclasses de contexto
# ---------------------------------------------------------------------------


@dataclass
class ProcessoResumo:
    numero_cnj: str
    tipo_acao: str | None
    fase_processual: str | None
    score_nivel: str | None
    score_interpretacao: str | None


@dataclass
class UltimaMensagem:
    pergunta_cliente: str | None
    resposta_ia: str | None
    data: datetime | None = None


@dataclass
class CRMContexto:
    # Dados do cliente
    cliente_id: int
    escritorio_id: int
    nome: str
    profissao: str | None
    empresa: str | None
    data_nascimento: str | None  # ISO date string, para o prompt do Claude

    # Interações
    total_interacoes_30d: int
    total_interacoes_90d: int
    dias_desde_ultimo_contato: int
    ultimo_contato_at: datetime | None

    # Processos
    processos_ativos: list[ProcessoResumo]
    pior_score_risco: str | None  # baixo | moderado | alto | critico | None

    # Escalações
    escalacoes_pendentes: int
    escalacoes_rejeitadas_30d: int

    # Estado CRM anterior (para cache check no analyzer — evita roundtrip extra)
    crm_nivel_anterior: str | None
    crm_score_anterior: int | None
    crm_analisado_em_anterior: datetime | None
    crm_resumo_anterior: str | None
    crm_acao_sugerida_anterior: str | None

    # Histórico para contexto do Claude
    ultimas_mensagens: list[UltimaMensagem] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Agregador
# ---------------------------------------------------------------------------

_ORDEM_RISCO = {"critico": 4, "alto": 3, "moderado": 2, "baixo": 1}


class CRMDataAggregator:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def coletar_contexto_cliente(self, cliente_id: int, escritorio_id: int) -> CRMContexto:
        agora = datetime.now(UTC)
        ha_30d = agora - timedelta(days=30)
        ha_90d = agora - timedelta(days=90)

        log = logger.bind(cliente_id=cliente_id, escritorio_id=escritorio_id)
        log.debug("crm.aggregator.coletando")

        # --- 1. Dados básicos do cliente (valida multi-tenant) ---
        stmt_cliente = select(
            Cliente.nome,
            Cliente.profissao,
            Cliente.empresa_atual,
            Cliente.data_nascimento,
            Cliente.crm_nivel,
            Cliente.crm_score,
            Cliente.crm_analisado_em,
            Cliente.crm_resumo,
            Cliente.crm_acao_sugerida,
        ).where(
            Cliente.id == cliente_id,
            Cliente.escritorio_id == escritorio_id,
            Cliente.ativo.is_(True),
        )
        cliente = (await self._db.execute(stmt_cliente)).one_or_none()

        if cliente is None:
            raise ValueError(f"Cliente {cliente_id} não encontrado no escritório {escritorio_id}")

        def _tz(dt: datetime) -> datetime:
            return dt if dt.tzinfo else dt.replace(tzinfo=UTC)

        # --- 2. Contagens de interações e último contato ---
        stmt_stats = select(
            func.count().filter(Interacao.created_at >= ha_30d).label("total_30d"),
            func.count().filter(Interacao.created_at >= ha_90d).label("total_90d"),
            func.max(Interacao.created_at).label("ultimo_contato"),
        ).where(
            Interacao.cliente_id == cliente_id,
            Interacao.escritorio_id == escritorio_id,
        )
        stats = (await self._db.execute(stmt_stats)).one()

        ultimo_contato_at: datetime | None = stats.ultimo_contato
        if ultimo_contato_at:
            dias_desde = (agora - _tz(ultimo_contato_at)).days
        else:
            dias_desde = 999

        # --- 3. Processos ativos ---
        stmt_proc = select(
            Processo.numero_cnj,
            Processo.tipo_acao,
            Processo.fase_processual,
            Processo.score_nivel,
            Processo.score_interpretacao,
        ).where(
            Processo.cliente_id == cliente_id,
            Processo.escritorio_id == escritorio_id,
            Processo.status == "ativo",
        )
        rows_proc = (await self._db.execute(stmt_proc)).all()
        processos_ativos = [
            ProcessoResumo(
                numero_cnj=r.numero_cnj,
                tipo_acao=r.tipo_acao,
                fase_processual=r.fase_processual,
                score_nivel=r.score_nivel,
                score_interpretacao=r.score_interpretacao,
            )
            for r in rows_proc
        ]

        pior_score = max(
            (p.score_nivel for p in processos_ativos if p.score_nivel),
            key=lambda n: _ORDEM_RISCO.get(n, 0),
            default=None,
        )

        # --- 4. Escalações (uma única roundtrip com contagens condicionais) ---
        esc_status = Interacao.metadata_json["escalacao_status"].as_string()
        stmt_esc = select(
            func.count().filter(esc_status == "pendente").label("pendentes"),
            func.count()
            .filter(and_(esc_status == "rejeitada", Interacao.created_at >= ha_30d))
            .label("rejeitadas_30d"),
        ).where(
            Interacao.cliente_id == cliente_id,
            Interacao.escritorio_id == escritorio_id,
        )
        row_esc = (await self._db.execute(stmt_esc)).one()
        escalacoes_pendentes: int = row_esc.pendentes
        escalacoes_rejeitadas_30d: int = row_esc.rejeitadas_30d

        # --- 5. Conversa recente (últimos 15 pares pergunta/resposta) ---
        # É o insumo principal da classificação de relacionamento feita pelo Claude.
        stmt_msgs = (
            select(Interacao.mensagem_cliente, Interacao.mensagem_ia, Interacao.created_at)
            .where(
                Interacao.cliente_id == cliente_id,
                Interacao.escritorio_id == escritorio_id,
                and_(
                    Interacao.mensagem_cliente.isnot(None),
                    Interacao.mensagem_ia.isnot(None),
                ),
            )
            .order_by(Interacao.created_at.desc())
            .limit(15)
        )
        rows_msgs = (await self._db.execute(stmt_msgs)).all()
        # Invertido para ordem cronológica — mais legível para o modelo
        ultimas_mensagens = [
            UltimaMensagem(
                pergunta_cliente=r.mensagem_cliente,
                resposta_ia=r.mensagem_ia,
                data=r.created_at,
            )
            for r in reversed(rows_msgs)
        ]

        log.debug("crm.aggregator.concluido", processos=len(processos_ativos))

        return CRMContexto(
            cliente_id=cliente_id,
            escritorio_id=escritorio_id,
            nome=cliente.nome,
            profissao=cliente.profissao,
            empresa=cliente.empresa_atual,
            data_nascimento=(
                cliente.data_nascimento.isoformat() if cliente.data_nascimento else None
            ),
            crm_nivel_anterior=cliente.crm_nivel,
            crm_score_anterior=cliente.crm_score,
            crm_analisado_em_anterior=cliente.crm_analisado_em,
            crm_resumo_anterior=cliente.crm_resumo,
            crm_acao_sugerida_anterior=cliente.crm_acao_sugerida,
            total_interacoes_30d=stats.total_30d,
            total_interacoes_90d=stats.total_90d,
            dias_desde_ultimo_contato=dias_desde,
            ultimo_contato_at=ultimo_contato_at,
            processos_ativos=processos_ativos,
            pior_score_risco=pior_score,
            escalacoes_pendentes=escalacoes_pendentes,
            escalacoes_rejeitadas_30d=escalacoes_rejeitadas_30d,
            ultimas_mensagens=ultimas_mensagens,
        )
