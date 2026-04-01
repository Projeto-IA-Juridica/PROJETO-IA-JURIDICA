# feature_1_ia_personalizada/workers/celery_app.py
from __future__ import annotations

import os

import structlog
from celery import Celery, Task
from celery.schedules import crontab
from celery.signals import worker_process_init
from kombu import Queue
from redbeat import RedBeatScheduler  # noqa: F401 — importação necessária para registro do scheduler

_dlq_logger = structlog.get_logger("workers.dlq")

# (opcional) carregar .env automaticamente
try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1").replace("CERT_NONE", "none")
RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/2").replace("CERT_NONE", "none")
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
    # RedBeat — scheduler dinâmico armazenado no Redis.
    # Permite ajustar crons via CLI ou endpoint sem redeploy:
    #   redbeat -A workers.celery_app beat -l info
    # Para inspecionar/editar schedules:
    #   from redbeat import RedBeatSchedulerEntry
    #   RedBeatSchedulerEntry.from_key('redbeat:nome-da-task', app=celery_app)
    beat_scheduler="redbeat.RedBeatScheduler",
    redbeat_redis_url=BROKER_URL,
    # Intervalo máximo de loop do beat (segundos). Padrão RedBeat é 5 min;
    # reduzimos para 30s para que alterações de schedule se propaguem rapidamente.
    beat_max_loop_interval=30,
    # DLQ — garantia de entrega
    # task_acks_late=True: a mensagem só é removida da fila APÓS a task concluir
    # (sucesso ou falha definitiva). Se o worker cair durante a execução, a task
    # volta à fila automaticamente.
    # task_reject_on_worker_lost=True: complementa o acks_late — quando um worker
    # é perdido (SIGKILL, OOM), as tasks em execução são rejeitadas (não acked)
    # e redistribuídas para outros workers.
    # Pré-requisito: todas as tasks devem ser idempotentes. As tasks existentes
    # já usam locks Redis (nx=True) que garantem idempotência.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
)

# Filas separadas
celery_app.conf.task_queues = (
    Queue("monitoramento", routing_key="monitoramento"),
    Queue("notificacoes", routing_key="notificacoes"),
    Queue("ia", routing_key="ia"),
    Queue("relacionamento", routing_key="relacionamento"),
    # Dead Letter Queue: recebe tasks que esgotaram todos os retries.
    # Worker dedicado recomendado para não misturar com filas normais:
    #   celery -A ... worker -Q dead_letter -c 1 --prefetch-multiplier 1
    Queue("dead_letter", routing_key="dead_letter"),
)

celery_app.conf.task_default_queue = "monitoramento"
celery_app.conf.task_default_exchange = "monitoramento"
celery_app.conf.task_default_routing_key = "monitoramento"

#  ROTAS: usar o NOME REAL da task (module.path.function)
celery_app.conf.task_routes = {
    # monitor_processos.py — nomes explícitos definidos via name= no decorator
    "workers.monitorar_processos": {
        "queue": "monitoramento",
        "routing_key": "monitoramento",
    },
    "workers.monitorar_processo_individual": {
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
    "feature_1_ia_personalizada.workers.mensagens_relacionamento.verificar_escalacoes_pendentes": {
        "queue": "relacionamento",
        "routing_key": "relacionamento",
    },
    # ingest_documentos.py
    "feature_1_ia_personalizada.workers.ingest_documentos.ingest_documento": {
        "queue": "ia",
        "routing_key": "ia",
    },
    "feature_1_ia_personalizada.workers.ingest_documentos.ingest_jurisprudencia_publica": {
        "queue": "ia",
        "routing_key": "ia",
    },
    # crm_worker.py
    "feature_1_ia_personalizada.workers.crm_worker.crm_analisar_cliente": {
        "queue": "ia",
        "routing_key": "ia",
    },
    "feature_1_ia_personalizada.workers.crm_worker.crm_analisar_escritorio": {
        "queue": "ia",
        "routing_key": "ia",
    },
    # dead_letter.py
    "workers.dead_letter.processar_dlq": {
        "queue": "dead_letter",
        "routing_key": "dead_letter",
    },
}

#  BEAT: usar o NOME REAL da task (mesmo padrão)
celery_app.conf.beat_schedule = {
    "monitorar-processos-a-cada-6-horas": {
        "task": "workers.monitorar_processos",
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
    "monitorar-escalacoes-pendentes": {
        "task": "feature_1_ia_personalizada.workers.mensagens_relacionamento.verificar_escalacoes_pendentes",
        "schedule": crontab(minute="*/30"),
    },
}


class DLQTask(Task):
    """
    Classe base para tasks que devem ser roteadas para o Dead Letter Queue
    após esgotarem todos os retries.

    Quando on_failure é chamado e self.request.retries >= self.max_retries,
    a task é enviada para a fila "dead_letter" com todo o contexto necessário
    para diagnóstico e re-execução manual.

    Uso com @celery_app.task:
        @celery_app.task(base=DLQTask, max_retries=3, autoretry_for=(Exception,))
        def minha_task(...):
            ...

    Uso com @shared_task:
        @shared_task(base=DLQTask, max_retries=3, autoretry_for=(Exception,))
        def minha_task(...):
            ...

    Importante: max_retries deve ser declarado explicitamente no decorator.
    Tasks sem max_retries definido não usam DLQ (esgotamento nunca é detectado).
    """

    abstract = True

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        max_retries = self.max_retries if self.max_retries is not None else 0

        if self.request.retries >= max_retries:
            try:
                celery_app.send_task(
                    "workers.dead_letter.processar_dlq",
                    kwargs={
                        "nome_task": self.name,
                        "task_id": task_id,
                        "args": list(args),
                        "kwargs": kwargs,
                        "erro": str(exc),
                        "traceback": str(einfo),
                        "tentativas": self.request.retries,
                    },
                    queue="dead_letter",
                )
                _dlq_logger.warning(
                    "dlq.encaminhado",
                    task=self.name,
                    task_id=task_id,
                    tentativas=self.request.retries,
                    erro=str(exc),
                )
            except Exception as dlq_exc:
                # Falha ao encaminhar para DLQ — loga mas não relança.
                # O erro original já foi logado pelo Celery; não queremos
                # mascarar a exceção primária com uma falha de infraestrutura.
                _dlq_logger.error(
                    "dlq.falha_ao_encaminhar",
                    task=self.name,
                    task_id=task_id,
                    dlq_erro=str(dlq_exc),
                )

        super().on_failure(exc, task_id, args, kwargs, einfo)


# Inicializa o JuridicalTranslator (singleton síncrono seguro) em cada processo worker.
# Clientes assíncronos (Redis, Claude, Evolution) são criados por task — ver orchestrator.py.
@worker_process_init.connect
def _init_worker_process(**kwargs):
    from feature_1_ia_personalizada.services.ai.orchestrator import (
        inicializar_orchestrador_worker,
    )

    inicializar_orchestrador_worker()


#  IMPORT EXPLÍCITO (mais confiável no MVP)
import feature_1_ia_personalizada.workers.crm_worker  # noqa: F401
import feature_1_ia_personalizada.workers.dead_letter  # noqa: F401
import feature_1_ia_personalizada.workers.ingest_documentos  # noqa: F401
import feature_1_ia_personalizada.workers.mensagens_relacionamento  # noqa: F401
import feature_1_ia_personalizada.workers.monitor_processos  # noqa: F401
import feature_1_ia_personalizada.workers.send_notifications  # noqa: F401
