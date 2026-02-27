"""
feature_1_ia_personalizada/api/routes/metrics.py
=================================================
Endpoint /metrics para scraping do Prometheus.
Expõe todas as métricas registradas no processo via prometheus_client.
"""

from fastapi import APIRouter
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

router = APIRouter(tags=["Monitoramento"])


@router.get("/metrics", include_in_schema=False)
async def prometheus_metrics():
    """Expõe métricas no formato text/plain para o Prometheus scraper."""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
