"""
Configuração de cenários e metas de performance do load test.

Uso:
    from tests.load.config import CENARIOS, SLA_TARGETS, AMBIENTES
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Ambientes pré-configurados
# ---------------------------------------------------------------------------

AMBIENTES: dict[str, dict] = {
    "local": {
        "host": "http://localhost:8000",
        "users": 10,
        "spawn_rate": 2,
        "run_time": "2m",
        "description": "Dev local — smoke test rápido",
    },
    "staging": {
        "host": "http://staging.concierge.internal",
        "users": 50,
        "spawn_rate": 5,
        "run_time": "5m",
        "description": "Staging — validação pré-deploy",
    },
    "producao": {
        "host": "https://seu-dominio.com",
        "users": 100,
        "spawn_rate": 10,
        "run_time": "10m",
        "description": "Produção — teste de carga real (cuidado!)",
    },
}

# ---------------------------------------------------------------------------
# Metas de SLA (p95 em ms) — Sprint 9–10 production-readiness.md seção 7.4
# ---------------------------------------------------------------------------

# Chave: (locust_name, HTTP_method) — espelha stats.entries do Locust.
# Alterar aqui propaga automaticamente para o sumário de CI em locustfile.py.
SLA_TARGETS: dict[tuple[str, str], int] = {
    # Health / infra
    ("/health",                           "GET"):  200,
    ("/health/ready",                     "GET"):  300,
    ("/health/detailed",                  "GET"):  500,
    ("/metrics",                          "GET"):  200,
    # Auth
    ("/auth/login",                       "POST"): 1000,
    ("/auth/refresh",                     "POST"): 500,
    ("/auth/me",                          "GET"):  300,
    # Chat — rota principal (p95 < 500ms)
    ("/chat/history/{cliente_id}",        "GET"):  500,
    ("/chat/stats/dashboard",             "GET"):  500,
    ("/chat/send/{cliente_id}",           "POST"): 1000,  # enfileira no Celery
    # Processos
    ("/processos (list)",                 "GET"):  500,
    ("/processos/{id}",                   "GET"):  300,
    ("/processos (create)",               "POST"): 800,
    ("/processos/{id} (update)",          "PUT"):  500,
    # Webhook WhatsApp — p95 < 2s (meta do doc)
    ("/webhook/whatsapp (texto)",         "POST"): 2000,
    ("/webhook/whatsapp (evento ignorado)", "POST"): 500,
}

# Taxa máxima de erro aceitável (%)
MAX_ERROR_RATE_PCT = 1.0

# ---------------------------------------------------------------------------
# Perfis de usuário e pesos por cenário
# ---------------------------------------------------------------------------

CENARIOS: dict[str, dict] = {
    "padrao": {
        "description": "Cenário padrão — mix realista de usuários",
        "users": {
            "HealthChecker": {"weight": 1},
            "AdvogadoAutenticado": {"weight": 5},
            "EvolutionWebhookSimulator": {"weight": 3},
        },
        "total_users": 50,
        "spawn_rate": 5,
        "run_time": "5m",
    },
    "pico_chat": {
        "description": "Pico de uso do chat — horário de pico escritório",
        "users": {
            "HealthChecker": {"weight": 1},
            "AdvogadoAutenticado": {"weight": 10},
            "EvolutionWebhookSimulator": {"weight": 2},
        },
        "total_users": 80,
        "spawn_rate": 10,
        "run_time": "5m",
    },
    "pico_webhook": {
        "description": "Pico de mensagens WhatsApp — campanha ou evento",
        "users": {
            "HealthChecker": {"weight": 1},
            "AdvogadoAutenticado": {"weight": 2},
            "EvolutionWebhookSimulator": {"weight": 10},
        },
        "total_users": 100,
        "spawn_rate": 20,
        "run_time": "5m",
    },
    "soak": {
        "description": "Soak test — carga moderada por longo período (detecta memory leaks)",
        "users": {
            "HealthChecker": {"weight": 1},
            "AdvogadoAutenticado": {"weight": 3},
            "EvolutionWebhookSimulator": {"weight": 2},
        },
        "total_users": 20,
        "spawn_rate": 2,
        "run_time": "60m",
    },
    "spike": {
        "description": "Spike test — pico repentino e queda (resiliência a tráfego explosivo)",
        "users": {
            "HealthChecker": {"weight": 1},
            "AdvogadoAutenticado": {"weight": 5},
            "EvolutionWebhookSimulator": {"weight": 3},
        },
        "total_users": 200,
        "spawn_rate": 50,   # sobe rápido
        "run_time": "3m",
    },
}

# ---------------------------------------------------------------------------
# Comandos de execução por cenário (referência)
# ---------------------------------------------------------------------------

COMANDOS_EXECUCAO = {
    "local_basico": (
        "locust -f tests/load/locustfile.py "
        "--host=http://localhost:8000 "
        "--users=10 --spawn-rate=2 --run-time=2m --headless"
    ),
    "staging_padrao": (
        "locust -f tests/load/locustfile.py "
        "--host=http://staging.concierge.internal "
        "--users=50 --spawn-rate=5 --run-time=5m --headless"
    ),
    "staging_pico_chat": (
        "locust -f tests/load/locustfile.py "
        "--host=http://staging.concierge.internal "
        "--users=80 --spawn-rate=10 --run-time=5m --headless"
    ),
    "staging_soak": (
        "locust -f tests/load/locustfile.py "
        "--host=http://staging.concierge.internal "
        "--users=20 --spawn-rate=2 --run-time=60m --headless"
    ),
    "interativo": (
        "locust -f tests/load/locustfile.py "
        "--host=http://localhost:8000"
        "  # Abre UI em http://localhost:8089"
    ),
    "relatorio_html": (
        "locust -f tests/load/locustfile.py "
        "--host=http://localhost:8000 "
        "--users=50 --spawn-rate=5 --run-time=5m --headless "
        "--html=tests/load/reports/load_report.html"
    ),
    "csv_metricas": (
        "locust -f tests/load/locustfile.py "
        "--host=http://localhost:8000 "
        "--users=50 --spawn-rate=5 --run-time=5m --headless "
        "--csv=tests/load/reports/load"
    ),
}
