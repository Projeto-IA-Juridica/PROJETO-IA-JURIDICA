# feature_1_ia_personalizada/workers/celery_app.py
from __future__ import annotations

import os

from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_process_init
from kombu import Queue

# (opcional) carregar .env automaticamente
try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1")
RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")
TIMEZONE = os.getenv("CELERY_TIMEZONE", "America/Sao_Paulo")

celery_app = Celery(
    "concierge_worker",
    broker=BROKER_URL,
    backend=RESULT_BACKEND,
)

celery_app.conf.update(
    timezone=TIMEZONE,
    enable_utc=False,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_track_started=True,
    task_time_limit=60 * 20,
    task_soft_time_limit=60 * 18,
    broker_connection_retry_on_startup=True,
)

# Filas separadas
celery_app.conf.task_queues = (
    Queue("monitoramento", routing_key="monitoramento"),
    Queue("notificacoes", routing_key="notificacoes"),
    Queue("ia", routing_key="ia"),
    Queue("relacionamento", routing_key="relacionamento"),
)

celery_app.conf.task_default_queue = "monitoramento"
celery_app.conf.task_default_exchange = "monitoramento"
celery_app.conf.task_default_routing_key = "monitoramento"

#  ROTAS: usar o NOME REAL da task (module.path.function)
celery_app.conf.task_routes = {
    # monitor_processos.py
    "feature_1_ia_personalizada.workers.monitor_processos.monitorar_todos_processos": {
        "queue": "monitoramento",
        "routing_key": "monitoramento",
    },
    "feature_1_ia_personalizada.workers.monitor_processos.monitorar_processo_individual": {
        "queue": "monitoramento",
        "routing_key": "monitoramento",
    },
    # send_notifications.py
    "feature_1_ia_personalizada.workers.send_notifications.enviar_notificacao_andamento": {
        "queue": "notificacoes",
        "routing_key": "notificacoes",
    },
    "feature_1_ia_personalizada.workers.send_notifications.enviar_lote_sem_movimentacao": {
        "queue": "notificacoes",
        "routing_key": "notificacoes",
    },
    "feature_1_ia_personalizada.workers.send_notifications.enviar_pesquisa_satisfacao": {
        "queue": "relacionamento",
        "routing_key": "relacionamento",
    },
    # ia (se existir)
    "feature_1_ia_personalizada.workers.send_notifications.processar_mensagem_recebida": {
        "queue": "ia",
        "routing_key": "ia",
    },
    # mensagens_relacionamento.py
    "feature_1_ia_personalizada.workers.mensagens_relacionamento.verificar_aniversarios_diarios": {
        "queue": "relacionamento",
        "routing_key": "relacionamento",
    },
    "feature_1_ia_personalizada.workers.mensagens_relacionamento.verificar_datas_comemorativas": {
        "queue": "relacionamento",
        "routing_key": "relacionamento",
    },
    "feature_1_ia_personalizada.workers.mensagens_relacionamento.verificar_clientes_sem_contato": {
        "queue": "relacionamento",
        "routing_key": "relacionamento",
    },
}

#  BEAT: usar o NOME REAL da task (mesmo padrão)
celery_app.conf.beat_schedule = {
    "monitorar-processos-a-cada-6-horas": {
        "task": "feature_1_ia_personalizada.workers.monitor_processos.monitorar_todos_processos",
        "schedule": crontab(minute=0, hour="0,6,12,18"),
    },
    "enviar-sem-movimentacao-semanal-seg-10h": {
        "task": "feature_1_ia_personalizada.workers.send_notifications.enviar_lote_sem_movimentacao",
        "schedule": crontab(minute=0, hour=10, day_of_week=1),
    },
    "pesquisa-satisfacao-mensal-dia-1-14h": {
        "task": "feature_1_ia_personalizada.workers.send_notifications.enviar_pesquisa_satisfacao",
        "schedule": crontab(minute=0, hour=14, day_of_month="1"),
    },
    "relacionamento-aniversarios-08h": {
        "task": "feature_1_ia_personalizada.workers.mensagens_relacionamento.verificar_aniversarios_diarios",
        "schedule": crontab(hour=8, minute=0),
    },
    "relacionamento-datas-0830": {
        "task": "feature_1_ia_personalizada.workers.mensagens_relacionamento.verificar_datas_comemorativas",
        "schedule": crontab(hour=8, minute=30),
    },
    "relacionamento-sem-contato-seg-10h": {
        "task": "feature_1_ia_personalizada.workers.mensagens_relacionamento.verificar_clientes_sem_contato",
        "schedule": crontab(day_of_week=1, hour=10, minute=0),
    },
}


# Inicializa o JuridicalTranslator (singleton síncrono seguro) em cada processo worker.
# Clientes assíncronos (Redis, Claude, Evolution) são criados por task — ver orchestrator.py.
@worker_process_init.connect
def _init_worker_process(**kwargs):
    from feature_1_ia_personalizada.services.ai.orchestrator import (
        inicializar_orchestrador_worker,
    )

    inicializar_orchestrador_worker()


#  IMPORT EXPLÍCITO (mais confiável no MVP)
import feature_1_ia_personalizada.workers.mensagens_relacionamento  # noqa: F401
import feature_1_ia_personalizada.workers.monitor_processos  # noqa: F401
import feature_1_ia_personalizada.workers.send_notifications  # noqa: F401
