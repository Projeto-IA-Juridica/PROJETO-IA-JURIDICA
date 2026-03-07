.PHONY: setup install-base dev worker beat flower \
       migrate migrate-create migrate-down migrate-history seed create-admin init-db \
       lint format lint-check type-check \
       test test-unit test-integration test-fast test-file \
       docker-up docker-down docker-logs docker-build docker-restart \
       health clean verify-install help

PYTHON := python3.12
VENV := .venv
PIP := $(VENV)/bin/pip
PYTEST := $(VENV)/bin/pytest
RUFF := $(VENV)/bin/ruff
BLACK := $(VENV)/bin/black
ALEMBIC := $(VENV)/bin/alembic
UVICORN := $(VENV)/bin/uvicorn
CELERY := $(VENV)/bin/celery

# ==============================================================================
# SETUP
# ==============================================================================

setup: ## Cria virtualenv e instala dependências
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements-f1.txt
	$(PIP) install -e ".[dev]"
	cp -n .env.example .env || true
	@echo "✅ Setup concluído! Edite o arquivo .env com suas credenciais."
	@echo "   Em seguida rode: make migrate && make seed"

install-base: ## Instala apenas dependências base (shared)
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements-base.txt

# ==============================================================================
# DESENVOLVIMENTO
# ==============================================================================

dev: ## Inicia servidor de desenvolvimento (Feature 1)
	$(UVICORN) feature_1_ia_personalizada.api.app:app \
		--host 0.0.0.0 \
		--port 8000 \
		--reload \
		--log-level info

worker: ## Inicia Celery worker
	$(CELERY) -A feature_1_ia_personalizada.workers.celery_app worker \
		--loglevel=info \
		--queues=monitoramento,notificacoes,ia

beat: ## Inicia Celery beat (agendador de tarefas)
	$(CELERY) -A feature_1_ia_personalizada.workers.celery_app beat \
		--loglevel=info

flower: ## Inicia Flower (monitoramento Celery) em localhost:5555
	$(CELERY) -A feature_1_ia_personalizada.workers.celery_app flower \
		--port=5555 \
		--basic_auth=${FLOWER_USER}:${FLOWER_PASSWORD}

# ==============================================================================
# BANCO DE DADOS
# ==============================================================================

migrate: ## Aplica migrations Alembic (upgrade head)
	$(ALEMBIC) upgrade head

migrate-create: ## Cria nova migration (use: make migrate-create MSG="descrição")
	$(ALEMBIC) revision --autogenerate -m "$(MSG)"

migrate-down: ## Reverte última migration
	$(ALEMBIC) downgrade -1

migrate-history: ## Exibe histórico de migrations
	$(ALEMBIC) history --verbose

seed: ## Popula banco com dados de desenvolvimento
	$(VENV)/bin/python scripts/setup/seed_data.py

create-admin: ## Cria usuário admin interativo
	$(VENV)/bin/python scripts/setup/create_admin.py

init-db: ## Inicializa banco (migrations + verifica tabelas + seed)
	$(VENV)/bin/python -m scripts.setup.init_db
	$(MAKE) seed

# ==============================================================================
# QUALIDADE DE CÓDIGO
# ==============================================================================

lint: ## Roda ruff linter
	$(RUFF) check . --fix

format: ## Formata código com black
	$(BLACK) .

lint-check: ## Verifica lint sem corrigir (para CI)
	$(RUFF) check .
	$(BLACK) --check .

type-check: ## Verifica tipos com mypy
	$(VENV)/bin/mypy shared/ feature_1_ia_personalizada/

# ==============================================================================
# TESTES
# ==============================================================================

test: ## Roda todos os testes
	$(PYTEST)

test-unit: ## Roda apenas testes unitários
	$(PYTEST) feature_1_ia_personalizada/tests/unit/ -v

test-integration: ## Roda apenas testes de integração
	$(PYTEST) feature_1_ia_personalizada/tests/integration/ -v

test-fast: ## Roda testes sem coverage (mais rápido)
	$(PYTEST) --no-cov -v

test-file: ## Roda um arquivo de teste específico (use: make test-file FILE=tests/unit/test_foo.py)
	$(PYTEST) $(FILE) -v

# ==============================================================================
# DOCKER
# ==============================================================================

docker-up: ## Sobe todos os serviços Docker (dev)
	docker compose -f infrastructure/docker/docker-compose.yml up -d

docker-down: ## Para todos os serviços Docker
	docker compose -f infrastructure/docker/docker-compose.yml down

docker-logs: ## Exibe logs dos serviços Docker
	docker compose -f infrastructure/docker/docker-compose.yml logs -f

docker-build: ## Reconstrói a imagem da Feature 1
	docker build -t concierge-f1:latest -f infrastructure/docker/Dockerfile.f1 .

docker-restart: ## Para e sobe novamente todos os serviços
	$(MAKE) docker-down
	$(MAKE) docker-up

# ==============================================================================
# MONITORAMENTO
# ==============================================================================

health: ## Verifica saúde de todos os serviços
	$(VENV)/bin/python scripts/monitoring/health_check.py

# ==============================================================================
# UTILITÁRIOS
# ==============================================================================

clean: ## Remove arquivos temporários e cache
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	find . -name ".coverage" -delete 2>/dev/null || true
	@echo "🧹 Limpeza concluída!"

verify-install: ## Verifica se todas as dependências estão instaladas
	$(VENV)/bin/python -c "import fastapi, sqlalchemy, anthropic, langgraph, celery, structlog; print('✅ Todas as dependências OK!')"

help: ## Exibe esta ajuda
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
