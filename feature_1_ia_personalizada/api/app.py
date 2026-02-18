"""
Entry point da Feature 1 — IA Personalizada (MVP).

Este arquivo é o ponto de entrada do servidor Uvicorn:
    uvicorn feature_1_ia_personalizada.api.app:app --reload

Fase atual: 0.6 — placeholder mínimo para validar o entry point.
Fase 2 expandirá este arquivo com routers, middlewares, Sentry e Prometheus.
"""

from fastapi import FastAPI

app = FastAPI(
    title="Concierge Jurídico Digital",
    description="IA conversacional para escritórios de advocacia",
    version="0.1.0",
)


@app.get("/health")
async def health():
    """Health check básico — expande na Fase 2."""
    return {"status": "ok", "service": "concierge-juridico-f1"}
