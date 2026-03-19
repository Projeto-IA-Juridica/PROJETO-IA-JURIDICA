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
    nps_score_gauge              — NPS médio atual por escritório
    ia_autonomia_percent_gauge   — % interações resolvidas sem humano por escritório
    escalacoes_pendentes_gauge   — escalações pendentes por escritório
"""

import hmac

import structlog
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, Gauge, generate_latest

from shared.config.settings import settings

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["Monitoramento"])

# ---------------------------------------------------------------------------
# Gauges de analytics — definidos aqui e importados por quem os atualiza
# ---------------------------------------------------------------------------

nps_score_gauge = Gauge(
    "nps_score",
    "NPS médio atual do escritório (escala 1-5)",
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
async def prometheus_metrics(request: Request):
    """
    Expõe métricas no formato text/plain para o Prometheus scraper.
    Protegido por Bearer token (METRICS_TOKEN) + restrição de IP na infra.
    """
    _verificar_token(request)
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
