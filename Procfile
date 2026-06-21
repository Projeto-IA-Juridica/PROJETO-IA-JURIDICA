release: alembic upgrade head
web: uvicorn feature_1_ia_personalizada.api.app:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2 --log-level info
worker: celery -A feature_1_ia_personalizada.workers.celery_app worker --loglevel=info --queues=monitoramento,notificacoes,ia,relacionamento,hub_advogado --concurrency=4
beat: celery -A feature_1_ia_personalizada.workers.celery_app beat --loglevel=info --schedule=/tmp/celerybeat-schedule
