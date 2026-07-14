"""
feature_1_ia_personalizada/api/app.py
======================================
Entry point principal do FastAPI para o Concierge Jurídico Digital.

Inicializa o aplicativo, configura middlewares (CORS),
registra todos os roteadores de domínio e define tratadores de eventos de ciclo de vida.
"""

import asyncio
import re
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import redis.asyncio as redis
import sentry_sdk
import structlog
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

from shared.config.settings import settings

# Validar formato das chaves no startup


def _validar_config_no_startup() -> None:
    erros: list[str] = []

    if not settings.REDIS_URL.startswith(("redis://", "rediss://")):
        erros.append("REDIS_URL inválida (esperado 'redis://' ou 'rediss://').")

    if not settings.CELERY_BROKER_URL.startswith(("redis://", "rediss://")):
        erros.append("CELERY_BROKER_URL inválida (esperado 'redis://' ou 'rediss://').")

    if not settings.CELERY_RESULT_BACKEND.startswith(("redis://", "rediss://")):
        erros.append("CELERY_RESULT_BACKEND inválida (esperado 'redis://' ou 'rediss://').")

    def _req(cond: bool, msg: str) -> None:
        if not cond:
            erros.append(msg)

    # Obrigatórias para subir o core
    _req(bool(settings.REDIS_URL), "REDIS_URL ausente.")
    _req(
        settings.REDIS_URL.startswith(("redis://", "rediss://")),
        "REDIS_URL inválida (esperado 'redis://' ou 'rediss://').",
    )

    _req(bool(settings.DATABASE_URL), "DATABASE_URL ausente.")
    _req(
        settings.DATABASE_URL.startswith("postgresql+asyncpg://"),
        "DATABASE_URL inválida (esperado 'postgresql+asyncpg://').",
    )

    _req(bool(settings.JWT_SECRET_KEY), "JWT_SECRET_KEY ausente.")
    _req(
        len(settings.JWT_SECRET_KEY) >= 32,
        "JWT_SECRET_KEY muito curta (mínimo 32 caracteres).",
    )

    _req(bool(settings.ENCRYPTION_KEY), "ENCRYPTION_KEY ausente.")
    try:
        from cryptography.fernet import Fernet as _Fernet

        _Fernet(settings.ENCRYPTION_KEY.encode())
    except Exception:
        erros.append(
            "ENCRYPTION_KEY inválida (deve ser uma chave Fernet válida — "
            "44 chars base64url, gerada com Fernet.generate_key())."
        )

    # Evolution API — opcional (WhatsApp)
    if settings.EVOLUTION_API_URL:
        _req(
            bool(re.match(r"^https?://", settings.EVOLUTION_API_URL)),
            "EVOLUTION_API_URL inválida (esperado http:// ou https://).",
        )
    if settings.EVOLUTION_API_KEY:
        pass  # Validação básica: se tem valor, assume estar correto

    # IA — OpenAI é opcional (usado só para Whisper/transcrição)
    if settings.OPENAI_API_KEY:
        _req(
            settings.OPENAI_API_KEY.startswith("sk-"),
            "OPENAI_API_KEY inválida (esperado iniciar com 'sk-').",
        )

    _req(bool(settings.ANTHROPIC_API_KEY), "ANTHROPIC_API_KEY ausente.")
    _req(
        settings.ANTHROPIC_API_KEY.startswith("sk-ant-"),
        "ANTHROPIC_API_KEY inválida (esperado iniciar com 'sk-ant-').",
    )

    if erros:
        raise RuntimeError("Config inválida no startup:\n- " + "\n- ".join(erros))


# ==========================================
# SENTRY — rastreamento de erros em produção
# ==========================================
if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.ENVIRONMENT,
        integrations=[
            FastApiIntegration(transaction_style="endpoint"),
            SqlalchemyIntegration(),
            CeleryIntegration(),
        ],
        traces_sample_rate=0.1,  # 10% das requisições para performance
        profiles_sample_rate=0.1,
        send_default_pii=False,  # LGPD — não enviar dados de usuário
    )

from feature_1_ia_personalizada.api.middleware.auth import (  # noqa: E402
    JWTAuthMiddleware,
)
from feature_1_ia_personalizada.api.middleware.csrf import CSRFMiddleware  # noqa: E402
from feature_1_ia_personalizada.api.middleware.rate_limit import (  # noqa: E402
    RateLimitMiddleware,
)
from feature_1_ia_personalizada.api.middleware.request_logging import (  # noqa: E402
    RequestLoggingMiddleware,
)

# Importando os roteadores das nossas subpastas
from feature_1_ia_personalizada.api.routes import (  # noqa: E402
    admin_import,
    agenda,
    agendamentos,
    auth,
    billing,
    chat,
    clientes,
    crm,
    escalacoes,
    escritorios,
    health,
    hub_advogado,
    metrics,
    onboarding,
    processos,
    prospeccao,
    rag,
    webhook_whatsapp,
)
from feature_1_ia_personalizada.api.routes.billing import (  # noqa: E402
    require_assinatura_ativa,
)

_QUERIES_FREQUENTES = [
    "qual o status do meu processo",
    "quando vai terminar meu processo",
    "o que aconteceu no meu processo",
    "houve alguma novidade",
    "qual a próxima audiência",
    "meu processo foi julgado",
]


async def _warmup_embeddings(redis_client: Any) -> None:
    """
    Pré-aquece embeddings das queries mais comuns no cache Redis (TTL 24h).
    Falha silenciosamente — nunca deve travar o startup.
    """
    try:
        import redis.asyncio as aioredis

        from feature_1_ia_personalizada.services.rag.embeddings import EmbeddingGenerator

        # Cria cliente Redis separado com decode_responses=False (embeddings são bytes JSON)
        redis_bytes = aioredis.from_url(settings.REDIS_URL, decode_responses=False)
        gen = EmbeddingGenerator(redis_client=redis_bytes)
        try:
            await gen.gerar_batch(_QUERIES_FREQUENTES)
            print(f"✅ Warm-up RAG: {len(_QUERIES_FREQUENTES)} embeddings pré-aquecidos.")
        finally:
            await gen.aclose()
            await redis_bytes.aclose()
    except Exception as exc:
        # Não bloqueia startup — embeddings serão gerados sob demanda
        print(f"⚠️  Warm-up de embeddings ignorado: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Executado ao iniciar o servidor (Startup)
    print("🚀 Iniciando o Concierge Jurídico Digital...")

    _validar_config_no_startup()  # valida formato das chaves/URLs

    # Ligando o Redis para o Rate Limit (timeout curto para não travar requests)
    app.state.redis_client = redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        socket_timeout=3,
        socket_connect_timeout=3,
    )

    try:
        await asyncio.wait_for(app.state.redis_client.ping(), timeout=5)
        print("✅ Redis conectado com sucesso (Rate Limit Ativo).")
    except TimeoutError:
        print("⚠️  Redis: timeout na conexão — rate limiting desativado.")
    except Exception as e:
        print(f"❌ Erro ao conectar no Redis: {e}")

    # Pré-aquece embeddings das queries mais comuns (P4) — com timeout para não travar startup
    try:
        await asyncio.wait_for(_warmup_embeddings(app.state.redis_client), timeout=15)
    except Exception:
        print("⚠️  Warm-up de embeddings: falhou — será gerado sob demanda.")

    yield

    # Executado ao desligar o servidor (Shutdown)
    print("🛑 Encerrando o servidor de forma graciosa...")
    if hasattr(app.state, "redis_client"):
        await app.state.redis_client.aclose()


logger = structlog.get_logger(__name__)

# Instanciando o App com o ciclo de vida
app = FastAPI(
    title="Concierge Jurídico Digital",
    description="Backend central da Inteligência Artificial via WhatsApp para Escritórios.",
    version="0.2.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ==========================================
# MIDDLEWARES GLOBAIS
# ==========================================
# CORS: em development permite qualquer origem; em staging/production restringe
# aos domínios declarados em CORS_ALLOWED_ORIGINS (separados por vírgula no .env)
if settings.ENVIRONMENT == "development":
    _cors_origins = ["*"]
    _cors_credentials = False  # allow_credentials=True é incompatível com allow_origins=["*"]
else:
    origins = settings.CORS_ALLOWED_ORIGINS
    if isinstance(origins, list):
        _cors_origins = [str(o).strip() for o in origins if str(o).strip()]
    else:
        _cors_origins = [o.strip() for o in str(origins).split(",") if o.strip()]
    _cors_credentials = True

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_credentials,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"],
)


# Registrando nossos custom middlewares (a ordem de registro importa, o último empilhado executa ANTES)
# Fluxo ao receber requisição: 1. Rate Limit -> 2. CSRF -> 3. Autenticação JWT -> 4. Rotas
app.add_middleware(JWTAuthMiddleware)
app.add_middleware(CSRFMiddleware)
app.add_middleware(RateLimitMiddleware)
# RequestLoggingMiddleware adicionado por último = executa PRIMEIRO (outermost)
# Garante que request_id está disponível para todos os middlewares internos e rotas
app.add_middleware(RequestLoggingMiddleware)

# ==========================================
# REGISTRO DE ROTEADORES (ENDPOINTS)
# ==========================================

# Guard de assinatura — aplicado em routers que exigem assinatura ativa.
# Escritórios com assinatura_status em ('trialing', 'active') passam livremente.
# Demais recebem HTTP 402 com instruções de reativação.
_guard = [Depends(require_assinatura_ativa)]

app.include_router(health)
app.include_router(metrics)
app.include_router(auth)
app.include_router(onboarding)
app.include_router(escritorios)
app.include_router(billing.router)

# Routers de features pagas — protegidos pelo guard de assinatura
app.include_router(processos, dependencies=_guard)
app.include_router(clientes.router, dependencies=_guard)
app.include_router(escalacoes.router, dependencies=_guard)
app.include_router(prospeccao.router, dependencies=_guard)
app.include_router(hub_advogado.router, dependencies=_guard)
app.include_router(crm.router, dependencies=_guard)
app.include_router(chat, dependencies=_guard)
app.include_router(rag, dependencies=_guard)
# routes/__init__.py já exporta estes nomes como APIRouter (não como módulo)
app.include_router(agenda, dependencies=_guard)
app.include_router(agendamentos, dependencies=_guard)

# Google Calendar — auth-url/status/disconnect exigem JWT (middleware);
# /callback é público (redirect do Google), validado por state de uso único
from feature_1_ia_personalizada.api.routes import (  # noqa: E402
    google_calendar as google_calendar_routes,
)

app.include_router(google_calendar_routes.router)

# Webhook WhatsApp — sem guard (recebe de terceiros, não de usuários logados)
app.include_router(webhook_whatsapp)
app.include_router(admin_import)

# ==========================================
# MÁQUINA DE VENDAS (feature_vendas) — OPT-IN, ISOLADA
# ==========================================
# Ponto de contato ÚNICO e guardado: se a feature estiver desligada
# (VENDAS_TENANT_ID ausente) ou a pasta feature_vendas removida, este bloco é
# um no-op e o produto roda idêntico. Nenhuma rota de cliente é afetada.
try:
    from feature_vendas.integration import incluir_rotas as _incluir_vendas

    _incluir_vendas(app)
except Exception:  # pragma: no cover — isolamento total: vendas nunca quebra o app
    logger.debug("feature_vendas indisponível — seguindo sem a máquina de vendas")

# ==========================================
# INSTRUMENTAÇÃO HTTP (Prometheus)
# ==========================================
# Adiciona métricas HTTP automáticas:
#   http_requests_total{method, handler, status}
#   http_request_duration_seconds{method, handler, status}
#   http_requests_in_progress{method, handler}
Instrumentator(
    should_group_status_codes=False,  # separa 200, 201, 404, etc.
    excluded_handlers=["/metrics"],  # não mede o endpoint de métricas em si
).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)


# ==========================================
# ERROR HANDLER GLOBAL
# ==========================================
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Captura explícita necessária: o handler impede que o Sentry capture automaticamente
    sentry_sdk.capture_exception(exc)
    logger.error("erro_nao_tratado", path=request.url.path, erro=str(exc), exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Erro interno do servidor"},
    )
