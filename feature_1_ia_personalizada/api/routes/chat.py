import json
from collections.abc import AsyncGenerator
from datetime import datetime
from decimal import Decimal
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from feature_1_ia_personalizada.workers.send_notifications import (
    processar_mensagem_recebida,
)
from shared.config.settings import settings
from shared.database.session import get_db
from shared.models.cliente import Cliente
from shared.models.interacao import Interacao
from shared.utils.lgpd import registrar_acesso

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/chat", tags=["Histórico e Chat"])

_CACHE_TTL_SEGUNDOS = 15 * 60  # 15 minutos
_DIAS_PERMITIDOS = {7, 30, 90}


def _get_user_id(request: Request) -> int:
    payload = getattr(request.state, "user_payload", {})
    return int(payload.get("sub", 0))


def _get_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return str(forwarded).split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _get_escritorio_id(request: Request) -> int:
    if not hasattr(request.state, "user_payload"):
        raise HTTPException(status_code=401, detail="Não autenticado")
    return int(request.state.user_payload.get("escritorio_id"))


async def get_redis() -> AsyncGenerator[Redis, None]:
    """Conexão Redis com ciclo de vida atrelado ao request — única conexão por request."""
    redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        yield redis
    finally:
        await redis.aclose()


# --- Schemas ---

class InteracaoResponse(BaseModel):
    id: int
    data: datetime
    direcao: str
    mensagem_cliente: str | None
    mensagem_ia: str | None
    tokens_input: int
    tokens_output: int
    custo_estimado: Decimal


class SendMessageRequest(BaseModel):
    mensagem: str
    tipo: str = "texto"


class ResumoDashboard(BaseModel):
    total_interacoes: int
    clientes_ativos: int
    nps_medio: float
    nps_anterior: float
    variacao_nps: str


class EficienciaDashboard(BaseModel):
    tempo_resposta_medio_ms: int
    interacoes_sem_humano: int
    percentual_autonomia: float
    horas_economizadas_estimadas: float
    custo_total_usd: float


class ClienteRankingItem(BaseModel):
    cliente_id: int
    nome: str
    nps_medio: float | None
    total_interacoes: int
    ultimo_contato: str | None
    em_risco: bool
    sem_avaliacao: bool


class TendenciaSemanal(BaseModel):
    semana: str
    total_interacoes: int
    nps_medio: float
    autonomia_pct: float


class ChatStatsDashboardResponse(BaseModel):
    resumo: ResumoDashboard
    eficiencia: EficienciaDashboard
    por_cliente: list[ClienteRankingItem]
    tendencia_semanal: list[TendenciaSemanal]
    score_risco_distribuicao: dict[str, int]


# --- Rotas ---

@router.get("/history/{cliente_id}", response_model=list[InteracaoResponse])
async def get_history(
    cliente_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, le=200),
):
    """Retorna o histórico de conversas recentes de um cliente."""
    escritorio_id = _get_escritorio_id(request)

    cliente = await db.get(Cliente, cliente_id)
    if not cliente or cliente.escritorio_id != escritorio_id:
        raise HTTPException(status_code=404, detail="Cliente não encontrado ou acesso restrito.")

    registrar_acesso(
        _get_user_id(request),
        f"chat:historico:cliente:{cliente_id}",
        "leitura",
        _get_ip(request),
    )

    stmt = (
        select(Interacao)
        .where(Interacao.cliente_id == cliente_id)
        .order_by(Interacao.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    interacoes = result.scalars().all()

    return [
        InteracaoResponse(
            id=i.id,
            data=i.created_at,
            direcao=i.direcao,
            mensagem_cliente=i.mensagem_cliente,
            mensagem_ia=i.mensagem_ia,
            tokens_input=i.tokens_input,
            tokens_output=i.tokens_output,
            custo_estimado=i.custo_estimado,
        )
        for i in interacoes
    ]


@router.post("/send/{cliente_id}", status_code=status.HTTP_202_ACCEPTED)
async def send_proactive_message(
    cliente_id: int,
    payload: SendMessageRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Envia uma mensagem ativamente (proativa) para um cliente da base via Celery."""
    escritorio_id = _get_escritorio_id(request)

    cliente = await db.get(Cliente, cliente_id)
    if not cliente or cliente.escritorio_id != escritorio_id:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")

    registrar_acesso(
        _get_user_id(request),
        f"chat:envio_proativo:cliente:{cliente_id}",
        "escrita",
        _get_ip(request),
    )

    processar_mensagem_recebida.delay(
        id_escritorio=escritorio_id,
        id_cliente=cliente_id,
        mensagem=payload.mensagem,
        tipo=payload.tipo,
    )
    return {
        "status": "enfileirado",
        "message": "A mensagem foi encaminhada aos workers para envio.",
    }


@router.get("/stats/dashboard", response_model=ChatStatsDashboardResponse)
async def get_chat_stats(
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    dias: Annotated[int, Query(description="Janela de análise em dias (7, 30 ou 90)")] = 30,
):
    """
    Dashboard completo de analytics do escritório.
    Resultado cacheado no Redis por 15 minutos por (escritorio_id, dias).
    """
    if dias not in _DIAS_PERMITIDOS:
        raise HTTPException(
            status_code=422,
            detail=f"Parâmetro 'dias' deve ser um de: {sorted(_DIAS_PERMITIDOS)}",
        )

    escritorio_id = _get_escritorio_id(request)
    cache_key = f"analytics:{escritorio_id}:{dias}"

    # --- Tenta cache ---
    try:
        cached = await redis.get(cache_key)
        if cached:
            logger.debug("analytics_cache_hit", escritorio_id=escritorio_id, dias=dias)
            return ChatStatsDashboardResponse(**json.loads(cached))
    except Exception as e:
        logger.warning("analytics_cache_read_error", error=str(e))

    # --- Cache miss: calcula ---
    from feature_1_ia_personalizada.services.analytics.calculadora import CalculadoraAnalytics

    calc = CalculadoraAnalytics(db, escritorio_id, dias=dias)

    resumo_raw, eficiencia_raw, tendencia_raw, ranking_raw = (
        await calc.obter_resumo(),
        await calc.obter_eficiencia(),
        await calc.tendencia_semanal(semanas=8),
        await calc.ranking_clientes(limite=20),
    )

    # score_risco_distribuicao: contagem de processos por nível (Feature 2)
    # Retorna vazio se colunas ainda não existirem (Feature 2 pendente)
    score_risco_dist: dict[str, int] = {}
    try:
        from shared.models.processo import Processo
        stmt_score = (
            select(Processo.score_nivel, func.count(Processo.id))
            .where(
                Processo.escritorio_id == escritorio_id,
                Processo.score_nivel.is_not(None),
            )
            .group_by(Processo.score_nivel)
        )
        result = await db.execute(stmt_score)
        score_risco_dist = {nivel: count for nivel, count in result.all()}
    except Exception:
        pass  # Feature 2 ainda não migrada — degradação graciosa

    payload = ChatStatsDashboardResponse(
        resumo=ResumoDashboard(**resumo_raw),
        eficiencia=EficienciaDashboard(**eficiencia_raw),
        por_cliente=[ClienteRankingItem(**c) for c in ranking_raw],
        tendencia_semanal=[TendenciaSemanal(**t) for t in tendencia_raw],
        score_risco_distribuicao=score_risco_dist,
    )

    # --- Atualiza métricas Prometheus ---
    _atualizar_metricas_prometheus(escritorio_id, payload, db)

    # --- Salva no cache (mesma conexão do request) ---
    try:
        await redis.setex(cache_key, _CACHE_TTL_SEGUNDOS, payload.model_dump_json())
        logger.debug("analytics_cache_set", escritorio_id=escritorio_id, dias=dias)
    except Exception as e:
        logger.warning("analytics_cache_write_error", error=str(e))

    return payload


def _atualizar_metricas_prometheus(
    escritorio_id: int,
    payload: "ChatStatsDashboardResponse",
    db: AsyncSession,
) -> None:
    """
    Atualiza os gauges Prometheus com os valores recém-calculados.
    Executado apenas em cache miss (cálculo real) — não em cache hit.
    Falhas são silenciosas para não impactar a resposta ao cliente.
    """
    import asyncio

    from feature_1_ia_personalizada.api.routes.metrics import (
        escalacoes_pendentes_gauge,
        ia_autonomia_percent_gauge,
        nps_score_gauge,
    )

    label = str(escritorio_id)
    try:
        nps_score_gauge.labels(escritorio_id=label).set(payload.resumo.nps_medio)
        ia_autonomia_percent_gauge.labels(escritorio_id=label).set(
            payload.eficiencia.percentual_autonomia
        )
    except Exception as e:
        logger.warning("prometheus_gauge_update_error", error=str(e))

    # escalacoes_pendentes: conta interações com escalacao.status=pendente
    async def _contar_escalacoes() -> int:
        from sqlalchemy import text
        result = await db.execute(
            text(
                "SELECT COUNT(*) FROM interacoes "
                "WHERE escritorio_id = :eid "
                "AND metadata_json->'escalacao'->>'status' = 'pendente'"
            ),
            {"eid": escritorio_id},
        )
        return result.scalar() or 0

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Já estamos em contexto async — agenda como task sem bloquear
            asyncio.ensure_future(
                _atualizar_gauge_escalacoes(escalacoes_pendentes_gauge, label, db)
            )
    except Exception as e:
        logger.warning("prometheus_escalacoes_gauge_error", error=str(e))


async def _atualizar_gauge_escalacoes(gauge, label: str, db: AsyncSession) -> None:
    from sqlalchemy import text

    try:
        result = await db.execute(
            text(
                "SELECT COUNT(*) FROM interacoes "
                "WHERE escritorio_id = :eid "
                "AND metadata_json->'escalacao'->>'status' = 'pendente'"
            ),
            {"eid": int(label)},
        )
        total = result.scalar() or 0
        gauge.labels(escritorio_id=label).set(total)
    except Exception as e:
        logger.warning("prometheus_escalacoes_count_error", error=str(e))


@router.get("/stats/export")
async def exportar_relatorio(
    request: Request,
    db: AsyncSession = Depends(get_db),
    mes: Annotated[str, Query(description="Mês no formato YYYY-MM (ex: 2026-03)")] = "",
    formato: Annotated[str, Query(description="Formato de exportação")] = "csv",
):
    """
    Exporta todas as interações do mês indicado.
    Suporta formato=csv (padrão). PDF em backlog.
    """
    if formato != "csv":
        raise HTTPException(status_code=422, detail="Formato não suportado. Use formato=csv.")

    if not mes:
        raise HTTPException(status_code=422, detail="Parâmetro 'mes' obrigatório (ex: ?mes=2026-03).")

    escritorio_id = _get_escritorio_id(request)

    from feature_1_ia_personalizada.services.analytics.exportador import ExportadorAnalytics

    exportador = ExportadorAnalytics(db, escritorio_id)
    try:
        conteudo = await exportador.gerar_csv(mes)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    nome_arquivo = f"relatorio_interacoes_{mes}.csv"
    return Response(
        content=conteudo,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nome_arquivo}"'},
    )
