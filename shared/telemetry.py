"""
shared/telemetry.py
===================
Configura OpenTelemetry para propagação de trace context entre:
  FastAPI → Celery workers → chamadas HTTP externas (DataJud, Evolution API, Claude, Voyage)

Estratégia em dois modos:
  1. Com OTLP_ENDPOINT configurado: exporta spans para Grafana Tempo / Jaeger.
  2. Sem OTLP_ENDPOINT: apenas configura o propagador W3C — trace_id fica disponível
     nos logs estruturados e nos headers das chamadas httpx, sem custo de rede.

Auto-instrumentações ativas (não requerem código nos serviços):
  - FastAPIInstrumentor   → span por endpoint, injeta trace_id no request
  - HTTPXClientInstrumentor → injeta W3C traceparent em DataJud, Evolution, Voyage
  - CeleryInstrumentor    → propaga trace context em .delay() / .apply_async()

trace_id nos logs:
  O middleware RequestLoggingMiddleware injeta o trace_id do span ativo no contexto
  structlog. Assim, cada linha de log do request (e do worker Celery correspondente)
  carrega o mesmo trace_id, permitindo correlação ponta-a-ponta sem OTel collector.
"""

import os

import structlog
from opentelemetry import trace
from opentelemetry.instrumentation.celery import CeleryInstrumentor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.propagate import set_global_textmap
from opentelemetry.propagators.composite import CompositePropagator
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

logger = structlog.get_logger(__name__)


def setup_telemetry(app=None) -> None:
    """
    Inicializa OpenTelemetry.

    Deve ser chamado UMA VEZ no startup do FastAPI (app.py) e UMA VEZ
    no startup de cada worker Celery (celery_app.py via worker_init signal).

    Parâmetros:
        app — instância FastAPI para instrumentação de endpoints (None em workers Celery).
    """
    # W3C Trace Context: padrão interoperável (Jaeger, Tempo, Datadog, etc.)
    set_global_textmap(CompositePropagator([TraceContextTextMapPropagator()]))

    resource = Resource.create({SERVICE_NAME: "concierge-juridico"})
    provider = TracerProvider(resource=resource)

    otlp_endpoint = os.getenv("OTLP_ENDPOINT")
    if otlp_endpoint:
        # Exporta spans para Grafana Tempo, Jaeger ou qualquer coletor OTLP HTTP.
        # Exemplo .env: OTLP_ENDPOINT=http://localhost:4318/v1/traces
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint)))
        logger.info("otel_exporter_ativado", otlp_endpoint=otlp_endpoint)
    else:
        logger.info(
            "otel_sem_exporter",
            msg="OTLP_ENDPOINT não configurado — trace_id disponível nos logs, spans não exportados",
        )

    trace.set_tracer_provider(provider)

    # Auto-instrumentações — propagam W3C traceparent sem alterações nos serviços
    HTTPXClientInstrumentor().instrument()  # DataJud, Evolution API, Voyage AI, LinkedIn
    CeleryInstrumentor().instrument()  # propaga contexto em .delay() / .apply_async()

    if app is not None:
        FastAPIInstrumentor.instrument_app(app)

    logger.info("otel_inicializado", exportando_spans=bool(otlp_endpoint))


def get_trace_id() -> str | None:
    """
    Retorna o trace_id do span ativo no contexto atual, ou None.

    Usado pelo RequestLoggingMiddleware para injetar o trace_id no contexto
    structlog de cada request, correlacionando logs com spans OTel.
    """
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if ctx.is_valid:
        return format(ctx.trace_id, "032x")
    return None
