"""
feature_1_ia_personalizada/api/routes/metrics.py
=================================================
Endpoint /metrics para scraping do Prometheus.
Expõe todas as métricas registradas no processo via prometheus_client.

Segurança em duas camadas (defense in depth):
  1. Bearer token via METRICS_TOKEN (env var) — verificado aqui no código.
  2. Restrição de IP/rede ao servidor Prometheus — configurar em nível de
     infraestrutura (nginx `allow`, firewall, security group). O token sozinho
     não é suficiente se a URL vazar; a restrição de rede garante que só o
     Prometheus consiga chegar ao endpoint.

Em desenvolvimento (METRICS_TOKEN=None): endpoint aberto com aviso no log.

Gauges de analytics (atualizados a cada cálculo do dashboard):
    crm_score_medio_gauge        — score CRM médio (0-100) por escritório
    ia_autonomia_percent_gauge   — % interações resolvidas sem humano por escritório
    escalacoes_pendentes_gauge   — escalações pendentes por escritório
"""

import hmac

import structlog
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

from shared.config.settings import settings

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["Monitoramento"])

# ---------------------------------------------------------------------------
# Gauges de analytics — definidos aqui e importados por quem os atualiza
# ---------------------------------------------------------------------------

crm_score_medio_gauge = Gauge(
    "crm_score_medio",
    "Score CRM médio do escritório (0-100, relacionamento classificado pela IA)",
    labelnames=["escritorio_id"],
)

ia_autonomia_percent_gauge = Gauge(
    "ia_autonomia_percent",
    "Percentual de interações resolvidas sem intervenção humana",
    labelnames=["escritorio_id"],
)

escalacoes_pendentes_gauge = Gauge(
    "escalacoes_pendentes",
    "Número de escalações com status pendente no escritório",
    labelnames=["escritorio_id"],
)

# ---------------------------------------------------------------------------
# Métricas de negócio — custo, tokens e latência da IA (por interação)
# ---------------------------------------------------------------------------

# Histograms NÃO têm escritorio_id: cada bucket cria N séries temporais,
# e (N_escritorios × N_intencoes × N_buckets) ultrapassa rapidamente o limite seguro
# do Prometheus (~100K séries). Use os Gauges por escritório abaixo para granularidade.
ia_custo_por_interacao_usd = Histogram(
    "ia_custo_por_interacao_usd",
    "Custo USD por interação processada pelo orchestrador (baseado em tokens Claude)",
    labelnames=["intencao"],
    buckets=(0.0001, 0.0005, 0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0),
)

# Counters com escritorio_id: cardinality = N_escritorios × N_intencoes.
# Aceitável enquanto N_escritorios < 500 (cada combo = 1 série, sem multiplicador de bucket).
ia_tokens_input_total = Counter(
    "ia_tokens_input_total",
    "Total de tokens de entrada consumidos pela IA",
    labelnames=["escritorio_id", "intencao"],
)

ia_tokens_output_total = Counter(
    "ia_tokens_output_total",
    "Total de tokens de saída gerados pela IA",
    labelnames=["escritorio_id", "intencao"],
)

ia_latencia_ms = Histogram(
    "ia_latencia_ms",
    "Latência ponta-a-ponta do orchestrador em milissegundos (recebimento → envio WhatsApp)",
    labelnames=["intencao"],
    buckets=(500, 1000, 2000, 3000, 5000, 8000, 12000, 20000, 30000),
)

# ---------------------------------------------------------------------------
# Métricas de negócio — CRM (saúde da carteira de clientes)
# ---------------------------------------------------------------------------

clientes_crm_analisados_total = Counter(
    "clientes_crm_analisados_total",
    "Total de análises CRM concluídas — agrupe por nivel para ver distribuição de risco",
    labelnames=["escritorio_id", "nivel"],
)

# ---------------------------------------------------------------------------
# Métricas de negócio — processos judiciais (distribuição de risco)
# ---------------------------------------------------------------------------

processos_por_risco_gauge = Gauge(
    "processos_por_risco_total",
    "Número atual de processos por nível de score de risco",
    labelnames=["escritorio_id", "nivel"],
)

# ---------------------------------------------------------------------------
# Métricas de negócio — canal WhatsApp (áudio)
# ---------------------------------------------------------------------------

audio_transcritos_total = Counter(
    "audio_transcritos_total",
    "Total de mensagens de áudio processadas via Whisper",
    labelnames=["resultado"],  # sucesso | erro_duracao | erro_whisper | erro_inesperado
)

# ---------------------------------------------------------------------------
# Métricas de escalação — Claude Opus (ex-Harvey)
# ---------------------------------------------------------------------------

escalacao_requests_total = Counter(
    "escalacao_requests_total",
    "Total de chamadas ao modelo de escalação (Claude Opus)",
    labelnames=[
        "escritorio_id",
        "resultado",
    ],  # resultado: sucesso | fallback_claude | circuit_breaker
)

escalacao_roteamentos_total = Counter(
    "escalacao_roteamentos_total",
    "Total de mensagens roteadas para Claude Opus pelo ConfidenceRouter",
    labelnames=[
        "escritorio_id",
        "motivo",
    ],  # motivo: score_baixo | forcado_termos | forcado_intencao
)

escalacao_tokens_total = Counter(
    "escalacao_tokens_total",
    "Total de tokens consumidos pelo modelo de escalação por escritório",
    labelnames=["escritorio_id", "tipo"],  # tipo: input | output
)

escalacao_latencia_ms = Histogram(
    "escalacao_latencia_ms",
    "Latência das chamadas ao modelo de escalação em milissegundos",
    buckets=(1000, 2000, 5000, 10000, 20000, 30000, 45000, 60000),
)

# ---------------------------------------------------------------------------
# Métricas de negócio — Agendamento Inteligente
# ---------------------------------------------------------------------------

agendamentos_criados_total = Counter(
    "agendamentos_criados_total",
    "Total de propostas de agendamento criadas pela IA",
    labelnames=["escritorio_id"],
)

agendamentos_confirmados_total = Counter(
    "agendamentos_confirmados_total",
    "Total de agendamentos confirmados pelo advogado (qualquer canal)",
    labelnames=["escritorio_id"],
)

agendamentos_expirados_total = Counter(
    "agendamentos_expirados_total",
    "Total de propostas expiradas sem resposta do cliente (48h)",
    labelnames=["escritorio_id"],
)

agendamentos_conflito_prazo_total = Counter(
    "agendamentos_conflito_prazo_total",
    "Total de agendamentos com conflito de prazo processual detectado",
    labelnames=["escritorio_id"],
)

tempo_aprovacao_advogado_segundos = Histogram(
    "tempo_aprovacao_advogado_segundos",
    "Tempo entre a escolha do cliente e a aprovação do advogado",
    labelnames=["escritorio_id"],
    buckets=(30, 60, 300, 900, 1800, 3600, 7200, 14400, 43200, 86400, 172800),
)


def _verificar_token(request: Request) -> None:
    """
    Valida o Bearer token do scraper Prometheus.
    - Se METRICS_TOKEN não está configurado (dev): permite acesso com aviso.
    - Se configurado: exige header 'Authorization: Bearer <token>' correto.
      Usa comparação de tempo constante (hmac.compare_digest) contra timing attacks.
    """
    if not settings.METRICS_TOKEN:
        logger.warning(
            "metrics_endpoint_sem_autenticacao",
            hint="Defina METRICS_TOKEN em produção e restrinja acesso por IP na infra.",
        )
        return

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization header ausente ou inválido.")

    token_recebido = auth_header.removeprefix("Bearer ").strip()
    if not hmac.compare_digest(token_recebido, settings.METRICS_TOKEN):
        logger.warning("metrics_token_invalido", ip=request.client.host if request.client else "?")
        raise HTTPException(status_code=403, detail="Token de scraping inválido.")


@router.get("/metrics", include_in_schema=False)
async def prometheus_metrics(request: Request) -> Response:
    """
    Expõe métricas no formato text/plain para o Prometheus scraper.
    Protegido por Bearer token (METRICS_TOKEN) + restrição de IP na infra.
    """
    _verificar_token(request)
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
