
# feature_1_ia_personalizada/workers/celery_app.py

from __future__ import annotations

import os
from celery import Celery
from celery.schedules import crontab

# (opcional) carregar .env automaticamente
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1")
RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")
TIMEZONE = os.getenv("CELERY_TIMEZONE", "America/Sao_Paulo")


celery_app = Celery( #verificar
    "concierge_worker",
    broker=BROKER_URL,
    backend=RESULT_BACKEND,
    include=[
        "feature_1_ia_personalizada.workers.monitor_processos",
        "feature_1_ia_personalizada.workers.send_notifications",
        "feature_1_ia_personalizada.workers.mensagens_relacionamento",
    ],
)

# Configuração base do Celery
celery_app.conf.update(
    timezone=TIMEZONE,
    enable_utc=False,  # importante se você quer crontab bater com horário Brasil
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_track_started=True,
    task_time_limit=60 * 20,        # hard limit (20 min) - ajuste se precisar
    task_soft_time_limit=60 * 18,   # soft limit (18 min)
)

# Filas separadas (monitoramento, notificacoes, ia, relacionamento)
celery_app.conf.task_queues = {
    "monitoramento": {"exchange": "monitoramento", "routing_key": "monitoramento"},
    "notificacoes": {"exchange": "notificacoes", "routing_key": "notificacoes"},
    "ia": {"exchange": "ia", "routing_key": "ia"},
    "relacionamento": {"exchange": "relacionamento", "routing_key": "relacionamento"},
}

# Routes: manda cada task para a fila certa
celery_app.conf.task_routes = {
    "workers.monitorar_processos": {"queue": "monitoramento", "routing_key": "monitoramento"},
    "workers.enviar_sem_movimentacao": {"queue": "notificacoes", "routing_key": "notificacoes"},
    "workers.pesquisa_satisfacao": {"queue": "relacionamento", "routing_key": "relacionamento"},
    "workers.limpar_cache_expirado": {"queue": "monitoramento", "routing_key": "monitoramento"},
    "workers.verificar_aniversarios": {"queue": "relacionamento", "routing_key": "relacionamento"},
    "workers.verificar_datas_profissoes": {"queue": "relacionamento", "routing_key": "relacionamento"},
    "workers.mensagens_trimestrais": {"queue": "relacionamento", "routing_key": "relacionamento"},
}

# Beat schedule 
celery_app.conf.beat_schedule = {
    "monitorar-processos-a-cada-6-horas": {
        "task": "workers.monitorar_processos",
        "schedule": crontab(minute=0, hour="0,6,12,18"),
    },
    "enviar-sem-movimentacao-semanal-seg-10h": {
        "task": "workers.enviar_sem_movimentacao",
        "schedule": crontab(minute=0, hour=10, day_of_week=1),  # segunda
    },
    "pesquisa-satisfacao-mensal-dia-1-14h": {
        "task": "workers.pesquisa_satisfacao",
        "schedule": crontab(minute=0, hour=14, day_of_month="1"),
    },
    "limpar-cache-expirado-diario-03h": {
        "task": "workers.limpar_cache_expirado",
        "schedule": crontab(minute=0, hour=3),
    },
    "verificar-aniversarios-diario-08h": {
        "task": "workers.verificar_aniversarios",
        "schedule": crontab(minute=0, hour=8),
    },
    "verificar-datas-profissoes-diario-08h30": {
        "task": "workers.verificar_datas_profissoes",
        "schedule": crontab(minute=30, hour=8),
    },
    "mensagens-trimestrais-semanal-seg-10h": {
        "task": "workers.mensagens_trimestrais",
        "schedule": crontab(minute=0, hour=10, day_of_week=1),  # segunda
    },
}

# (opcional) para evitar warning de "no hostname supplied"
celery_app.conf.broker_connection_retry_on_startup = True



