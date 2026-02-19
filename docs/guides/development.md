# Guia de Desenvolvimento — Estrutura Raiz do Projeto

> Documento de referência para a **Fase 0 — Setup do Projeto** do Concierge Jurídico Digital.
> Cobre toda a configuração inicial: estrutura do repositório, banco de dados, ferramentas de desenvolvimento e dependências.

---

## Índice

**Progresso da Fase 0:**

| Sub-fase | Status | Descrição |
|---|---|---|
| 0.1 Estrutura Raiz | ✅ Concluída | `.gitignore`, `pyproject.toml`, `Makefile`, `.env.example`, Docker |
| 0.2 Banco de Dados Local | ✅ Concluída | PostgreSQL/Redis via docker-compose, `alembic.ini` + `env.py` async configurados |
| 0.3 Ferramentas de Desenvolvimento | ✅ Concluída | `ruff`, `pytest`, `pre-commit` |
| 0.4 Instalar Dependências Python | ✅ Concluída | `requirements-base.txt`, `requirements-f1.txt`, virtualenv |
| 0.5 Criar `__init__.py` nos Módulos | ✅ Concluída | Todos os diretórios Python (shared + feature_1) |
| 0.6 Configurar Entry Point Uvicorn | ✅ Concluída | `app.py` placeholder + `make dev` funcional |

---

1. [Visão Geral da Estrutura](#1-visão-geral-da-estrutura)
2. [.gitignore](#2-gitignore)
3. [pyproject.toml](#3-pyprojecttoml)
4. [Makefile](#4-makefile)
5. [.env.example](#5-envexample)
6. [Docker](#6-docker)
   - [docker-compose.yml](#61-docker-composeyml)
   - [Dockerfile.f1](#62-dockerfilef1)
7. [Banco de Dados Local (Fase 0.2)](#7-banco-de-dados-local-fase-02)
   - [PostgreSQL 16](#71-postgresql-16)
   - [Redis 7](#72-redis-7)
   - [Configurar Alembic](#73-configurar-alembic)
8. [Dependências Python (Fase 0.4)](#8-dependências-python-fase-04)
   - [requirements-base.txt](#81-requirements-basetxt)
   - [requirements-f1.txt](#82-requirements-f1txt)
   - [Instalar e verificar](#83-instalar-e-verificar)
9. [Fluxo de Setup Inicial](#9-fluxo-de-setup-inicial)
10. [Variáveis de Ambiente — Referência Completa](#10-variáveis-de-ambiente--referência-completa)
11. [.pre-commit-config.yaml (Fase 0.3)](#11-pre-commit-configyaml-fase-03)

---

## 1. Visão Geral da Estrutura

Estrutura da raiz após a Fase 0 (Setup completo):

```
PROJETO-IA-JURIDICA/
│
├── .gitignore                          ← O que o Git deve ignorar
├── .env.example                        ← Template de variáveis de ambiente
├── .env                                ← Suas credenciais reais (NÃO commitar!)
│
├── pyproject.toml                      ← Configuração do projeto Python + configs ruff/pytest
├── Makefile                            ← Atalhos de comandos (setup, dev, test...)
├── .pre-commit-config.yaml             ← Hooks automáticos de qualidade (Fase 0.3)
│
├── requirements-base.txt               ← Deps compartilhadas (Fase 0.4)
├── requirements-f1.txt                 ← Deps da Feature 1 (Fase 0.4)
│
├── feature_1_ia_personalizada/         ← Feature 1: IA Personalizada (MVP)
│   ├── __init__.py
│   └── api/
│       ├── __init__.py
│       └── app.py                      ← Entry point Uvicorn (Fase 0.6 — placeholder)
│
├── infrastructure/
│   └── docker/
│       ├── docker-compose.yml          ← Todos os serviços em container
│       └── Dockerfile.f1               ← Imagem da API Feature 1
│
├── docs/
│   └── guides/
│       └── development.md              ← Este arquivo
│
├── README.md                           ← Visão geral do projeto
└── TASKS.md                            ← Lista detalhada de tarefas
```

---

## 2. `.gitignore`

**Localização:** [`.gitignore`](../../.gitignore)

### O que faz

Define quais arquivos e pastas o Git deve **ignorar completamente** — ou seja, nunca rastrear nem commitar.

### O que está sendo ignorado e por quê

| Categoria | Padrões ignorados | Motivo |
|---|---|---|
| **Python** | `__pycache__/`, `*.pyc`, `*.egg-info/`, `dist/`, `build/` | Arquivos gerados automaticamente, não pertencem ao repositório |
| **Virtualenv** | `.venv/`, `venv/`, `env/` | Cada dev tem o seu próprio, não deve ser compartilhado |
| **Segredos** | `.env`, `.env.*`, `*.pem`, `*.key`, `*.crt`, `secrets/` | Contém credenciais reais — NUNCA commitar |
| **IDEs** | `.vscode/`, `.idea/`, `*.swp`, `.DS_Store` | Configurações pessoais de cada desenvolvedor |
| **Testes/Lint** | `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `.coverage`, `htmlcov/` | Resultados de teste e cache de linters são gerados localmente |
| **ML Models** | `*.pkl`, `*.joblib`, `*.h5`, `*.pt`, `*.pth`, `*.onnx` | Modelos treinados são grandes demais para Git (usar DVC/S3) |
| **Dados (LGPD)** | `data/raw/`, `data/processed/`, `data/**/*.csv`, `data/**/*.xlsx`, `data/**/*.pdf` | Dados de clientes restritos a `data/` — compliance LGPD |
| **Terraform** | `.terraform/`, `*.tfstate`, `*.tfvars` | Estado da infra contém dados sensíveis |
| **Logs** | `*.log`, `celerybeat-schedule`, `celerybeat.pid` | Logs são gerados em runtime |

### Exceção importante

```gitignore
# O .env.example É commitado (não tem credenciais reais)
!.env.example
```

O `.env.example` serve como documentação das variáveis necessárias. O `.env` real (com credenciais) é ignorado.

---

## 3. `pyproject.toml`

**Localização:** [`pyproject.toml`](../../pyproject.toml)

### O que faz

Arquivo central de configuração do projeto Python. Substitui o antigo `setup.py` e centraliza configurações de dependências, ferramentas de lint, testes e build.

### Seções principais

#### `[project]` — Metadados e dependências base

```toml
[project]
name = "concierge-juridico"
version = "0.1.0"
requires-python = ">=3.12"
```

As dependências em `dependencies = [...]` são as **dependências base** (shared) — instaladas em todas as features.

> **Errata aplicada:** O documento original especificava `sqlalchemy==0.0.25` (versão inexistente). O arquivo correto usa `sqlalchemy==2.0.25` e inclui `asyncpg==0.29.0` (driver assíncrono obrigatório para `create_async_engine`).

#### `[project.optional-dependencies]` — Grupos de dependências

```toml
[project.optional-dependencies]
feature1 = [...]   # Instalar com: pip install -e ".[feature1]"
dev = [...]        # Instalar com: pip install -e ".[dev]"
```

| Grupo | Comando de instalação | Quando usar |
|---|---|---|
| `feature1` | `pip install -e ".[feature1]"` | Para rodar a Feature 1 (IA + Celery) |
| `dev` | `pip install -e ".[dev]"` | Para desenvolver (pytest, ruff, black, mypy) |

#### `[tool.pytest.ini_options]` — Configuração do pytest

```toml
asyncio_mode = "auto"    # Testes async funcionam automaticamente
testpaths = [...]        # Onde o pytest procura testes
addopts = "-v --cov=..."  # Coverage automático em todo run de teste
```

#### `[tool.ruff]` — Configuração do linter

```toml
target-version = "py312"
line-length = 100
select = ["E", "W", "F", "I", "B", "C4", "UP"]
```

O ruff verifica: erros de estilo (E/W), bugs comuns (F/B), imports desorganizados (I), código desatualizado (UP) e comprehensions ineficientes (C4).

#### `[build-system]` — Backend de build

```toml
[build-system]
requires = ["setuptools>=68.0", "wheel"]
build-backend = "setuptools.build_meta"
```

> **Correção aplicada (setup inicial):** O valor original `setuptools.backends.legacy:build` não existe no setuptools e causava `BackendUnavailable` ao rodar `pip install -e ".[dev]"`. O backend padrão e correto é `setuptools.build_meta`.

---

## 4. `Makefile`

**Localização:** [`Makefile`](../../Makefile)

### O que faz

Centraliza todos os comandos frequentes do projeto em atalhos simples. Em vez de memorizar comandos longos, você usa `make <comando>`.

> **Nota técnica:** Todos os 25 targets estão declarados como `.PHONY` no topo do arquivo, garantindo que o Make os execute sempre — mesmo que exista um arquivo ou diretório com o mesmo nome de um target.

### Referência de comandos

#### Setup e Instalação

```bash
make setup          # Cria .venv + instala requirements-f1.txt + copia .env.example
make install-base   # Instala apenas dependências base (sem feature1)
```

#### Desenvolvimento

```bash
make dev            # Inicia servidor FastAPI com hot-reload em localhost:8000
make worker         # Inicia Celery worker (filas: monitoramento, notificacoes, ia)
make beat           # Inicia Celery Beat (agendador de tarefas cron)
make flower         # Interface web de monitoramento Celery em localhost:5555
```

#### Banco de Dados

```bash
make migrate                        # Aplica todas as migrations pendentes
make migrate-create MSG="descrição"  # Cria nova migration via autogenerate
make migrate-down                   # Reverte a última migration aplicada
make migrate-history                # Exibe histórico de migrations
make seed                           # Popula banco com dados de desenvolvimento
make create-admin                   # Cria usuário admin via CLI interativo
make init-db                        # Atalho: migrate + seed em sequência
```

#### Qualidade de Código

```bash
make lint           # Roda ruff e corrige automaticamente o que for possível
make format         # Formata todo o código com black
make lint-check     # Verifica lint SEM corrigir (ideal para uso em CI/CD)
make type-check     # Verifica tipos com mypy
```

#### Testes

```bash
make test                     # Roda todos os testes com coverage
make test-unit                # Apenas testes unitários
make test-integration         # Apenas testes de integração
make test-fast                # Testes sem coverage (mais rápido para dev)
make test-file FILE=caminho   # Roda um arquivo específico
```

#### Docker

```bash
make docker-up      # Sobe todos os serviços em background
make docker-down    # Para todos os serviços
make docker-logs    # Exibe logs em tempo real
make docker-build   # Reconstrói a imagem da Feature 1
make docker-restart # Para e sobe novamente
```

#### Utilitários

```bash
make health         # Verifica saúde de todos os serviços
make clean          # Remove __pycache__, .pytest_cache, .coverage, htmlcov
make verify-install # Confirma que as dependências críticas estão instaladas
make help           # Lista todos os comandos disponíveis com descrição
```

> **Dica:** rode `make help` a qualquer momento para ver todos os comandos com suas descrições.

---

## 5. `.env.example`

**Localização:** [`.env.example`](../../.env.example)

### O que faz

Template documentado de **todas** as variáveis de ambiente que a aplicação precisa. Serve como contrato: se uma variável nova é necessária, ela deve aparecer aqui antes de ir para produção.

### Como usar

```bash
# 1. Copiar para .env (feito automaticamente pelo make setup)
cp .env.example .env

# 2. Editar .env com suas credenciais reais
nano .env   # ou use seu editor preferido
```

### Grupos de variáveis

#### Ambiente e Log

```env
ENVIRONMENT=development   # development | staging | production
LOG_LEVEL=INFO            # DEBUG | INFO | WARNING | ERROR | CRITICAL
```

#### Banco de Dados

```env
DATABASE_URL=postgresql+asyncpg://concierge:concierge_pass@localhost:5432/concierge_dev
```

> O scheme `postgresql+asyncpg://` é obrigatório. O driver `asyncpg` é necessário para o SQLAlchemy funcionar de forma assíncrona com FastAPI.

#### Segurança — Gerando as chaves

```bash
# JWT_SECRET_KEY (string aleatória de 64 chars)
python -c "import secrets; print(secrets.token_hex(32))"

# ENCRYPTION_KEY (chave Fernet para AES-256)
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### Variáveis obrigatórias para o MVP (Feature 1)

| Variável | Como obter |
|---|---|
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) |
| `OPENAI_API_KEY` | [platform.openai.com](https://platform.openai.com/api-keys) |
| `EVOLUTION_API_KEY` | Configurar na interface do Evolution API |
| `JUSBRASIL_API_KEY` | Entrar em contato com Jusbrasil |
| `JWT_SECRET_KEY` | Gerar localmente (ver acima) |
| `ENCRYPTION_KEY` | Gerar localmente (ver acima) |

---

## 6. Docker

### 6.1 `docker-compose.yml`

**Localização:** [`infrastructure/docker/docker-compose.yml`](../docker/docker-compose.yml)

#### O que faz

Define e orquestra **todos os serviços** necessários para rodar o ambiente de desenvolvimento completo em containers.

#### Serviços

| Serviço | Imagem | Porta | Descrição |
|---|---|---|---|
| `postgres` | `postgres:16-alpine` | `5432` | Banco de dados principal |
| `redis` | `redis:7-alpine` | `6379` | Cache + broker Celery |
| `evolution-api` | `atendai/evolution-api` | `8080` | WhatsApp (self-hosted) |
| `app-f1` | `Dockerfile.f1` | `8000` | API FastAPI Feature 1 |
| `celery-worker` | `Dockerfile.f1` | — | Processamento assíncrono |
| `celery-beat` | `Dockerfile.f1` | — | Agendador de tarefas cron |
| `flower` | `Dockerfile.f1` | `5555` | UI de monitoramento Celery |

#### Mapa de Redis databases

O Redis usa databases separados para não misturar dados:

```
redis/0  → Dados da aplicação (cache de processos, sessões)
redis/1  → Broker Celery (fila de tasks)
redis/2  → Result backend Celery (resultados das tasks)
redis/3  → Evolution API (state interno)
redis/4  → Evolution API (pub/sub)
```

#### Dependências entre serviços

```
postgres ←── app-f1 ←── celery-worker
redis    ←── app-f1     celery-beat
         ←── celery-worker
         ←── celery-beat
         ←── flower
         ←── evolution-api
```

Os serviços que dependem do banco ou cache só sobem depois que o `healthcheck` dos dependentes passa.

#### Como usar

```bash
# Subir tudo
make docker-up
# ou diretamente:
docker compose -f infrastructure/docker/docker-compose.yml up -d

# Verificar status
docker compose -f infrastructure/docker/docker-compose.yml ps

# Ver logs de um serviço específico
docker compose -f infrastructure/docker/docker-compose.yml logs -f app-f1

# Parar tudo
make docker-down
```

#### Acesso aos serviços

| Serviço | URL/Endereço |
|---|---|
| API FastAPI | http://localhost:8000 |
| Docs Swagger | http://localhost:8000/docs |
| Flower (Celery) | http://localhost:5555 (admin/admin) |
| Evolution API | http://localhost:8080 |
| PostgreSQL | localhost:5432 (concierge/concierge_pass) |
| Redis | localhost:6379 |

> **Hot-reload em dev:** O `docker-compose.yml` monta o código local como volume (`../../:/app`), então alterações no código são refletidas imediatamente sem rebuild da imagem.

---

### 6.2 `Dockerfile.f1`

**Localização:** [`infrastructure/docker/Dockerfile.f1`](../docker/Dockerfile.f1)

#### O que faz

Define a imagem Docker da **Feature 1 (IA Personalizada)**. Usa multi-stage build para separar o ambiente de compilação do ambiente de runtime, resultando em uma imagem final menor e mais segura.

#### Estratégia multi-stage

```
Stage 1: builder (python:3.12-slim)
  ├── Instala ferramentas de compilação (build-essential, libpq-dev)
  ├── Cria virtualenv em /opt/venv
  └── Instala todos os pacotes Python

Stage 2: runtime (python:3.12-slim) ← imagem final
  ├── Instala apenas runtime deps (ffmpeg, libpq5, curl)
  ├── Copia /opt/venv do builder
  ├── Cria usuário não-root (appuser:1000)
  ├── Copia código da aplicação
  └── EXPOSE 8000
```

#### Por que ffmpeg?

O WhatsApp envia áudios no formato `.ogg` (Opus). O `pydub` (Python) precisa do `ffmpeg` (binário do SO) para converter esses áudios para `.mp3` antes de enviar para a API Whisper da OpenAI para transcrição.

```
Usuário envia áudio (WhatsApp)
    → Evolution API recebe o .ogg
    → Nossa API baixa o arquivo
    → pydub + ffmpeg converte ogg → mp3
    → OpenAI Whisper transcreve para texto
    → Orchestrator processa o texto
```

#### Segurança

O container roda com usuário **não-root** (`appuser`, UID 1000). Isso é uma boa prática de segurança — se o container for comprometido, o atacante não tem privilégios de root no sistema host.

#### Build manual

```bash
# Na raiz do projeto:
docker build -t concierge-f1:latest -f infrastructure/docker/Dockerfile.f1 .

# Ou via Makefile:
make docker-build
```

---

## 7. Banco de Dados Local (Fase 0.2)

> **Status:** ⏳ Pendente — esta seção documenta o que será configurado na Fase 0.2.

A Fase 0.2 configura o PostgreSQL e o Redis localmente (ou via Docker) e inicializa o Alembic para controle de migrations.

---

### 7.1 PostgreSQL 16

#### Opção A — Via Docker (recomendado para desenvolvimento)

O `docker-compose.yml` já inclui o serviço `postgres`. Basta subir o ambiente:

```bash
make docker-up
# → postgres:16-alpine rodando em localhost:5432
# → usuário: concierge | senha: concierge_pass | database: concierge_dev
```

Para verificar que está rodando:

```bash
docker compose -f infrastructure/docker/docker-compose.yml ps postgres
```

Para conectar via `psql`:

```bash
docker exec -it concierge-postgres psql -U concierge -d concierge_dev
```

#### Opção B — Instalação local

```bash
# macOS (Homebrew)
brew install postgresql@16
brew services start postgresql@16

# Ubuntu/Debian
sudo apt install postgresql-16
sudo systemctl start postgresql

# Criar usuário e database
psql -U postgres -c "CREATE USER concierge WITH PASSWORD 'concierge_pass';"
psql -U postgres -c "CREATE DATABASE concierge_dev OWNER concierge;"
psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE concierge_dev TO concierge;"
```

#### Variável de ambiente

```env
DATABASE_URL=postgresql+asyncpg://concierge:concierge_pass@localhost:5432/concierge_dev
```

> **Atenção:** O scheme `postgresql+asyncpg://` é obrigatório. O driver `asyncpg` é o que permite ao SQLAlchemy operar de forma assíncrona com FastAPI. O `psycopg2-binary` (síncrono) não é compatível com `create_async_engine`.

---

### 7.2 Redis 7

#### Opção A — Via Docker (recomendado)

Também já incluído no `docker-compose.yml`:

```bash
make docker-up
# → redis:7-alpine rodando em localhost:6379
```

Para verificar:

```bash
docker exec -it concierge-redis redis-cli ping
# → PONG
```

#### Opção B — Instalação local

```bash
# macOS
brew install redis
brew services start redis

# Ubuntu/Debian
sudo apt install redis-server
sudo systemctl start redis-server

# Testar conexão
redis-cli ping
# → PONG
```

#### Databases Redis utilizados

| Database | URL | Uso |
|---|---|---|
| `redis/0` | `REDIS_URL` | Cache da aplicação (processos, sessões) |
| `redis/1` | `CELERY_BROKER_URL` | Fila de tasks Celery |
| `redis/2` | `CELERY_RESULT_BACKEND` | Resultados das tasks Celery |

---

### 7.3 Configurar Alembic

O Alembic é o sistema de migrations do SQLAlchemy — permite criar, versionar e aplicar mudanças no schema do banco de forma incremental e reversível.

#### Inicialização (uma vez por projeto)

```bash
# Na raiz do projeto, com o virtualenv ativado:
alembic init alembic
```

Isso cria:
```
alembic/
├── env.py          ← Script de configuração do ambiente
├── script.py.mako  ← Template de migration
└── versions/       ← Arquivos de migration gerados
alembic.ini         ← Configuração principal
```

#### Ajustes necessários após `alembic init`

**`alembic.ini`** — apontar para variável de ambiente em vez de URL hardcoded:

```ini
# Trocar a linha sqlalchemy.url por:
sqlalchemy.url = %(DATABASE_URL)s
```

**`alembic/env.py`** — carregar `.env` e importar os models:

```python
from dotenv import load_dotenv
load_dotenv()

# Importar todos os models para o autogenerate funcionar
from shared.models import Base  # noqa: F401 (precisa ser importado)

target_metadata = Base.metadata
```

#### Fluxo de uso

```bash
# Criar migration após alterar um model
make migrate-create MSG="create initial tables"
# → gera: alembic/versions/xxxx_create_initial_tables.py

# Aplicar todas as migrations pendentes
make migrate
# → alembic upgrade head

# Reverter última migration
make migrate-down
# → alembic downgrade -1

# Ver histórico de migrations
make migrate-history
```

> **Dependência:** A Fase 1 (shared/models) deve ser implementada antes de criar a migration inicial, pois o Alembic usa os models SQLAlchemy para gerar o schema automaticamente via `--autogenerate`.

---

## 8. Dependências Python (Fase 0.4)

O projeto usa dois arquivos de requirements com hierarquia — o `requirements-f1.txt` inclui o `requirements-base.txt` via `-r`, evitando duplicação.

---

### 8.1 `requirements-base.txt`

**Localização:** [`requirements-base.txt`](../../requirements-base.txt)

Contém as dependências **compartilhadas** entre todas as features — tudo que está em `shared/`. Qualquer feature nova parte daqui.

| Pacote | Versão | Para quê |
|---|---|---|
| `fastapi` | 0.109.0 | Framework web assíncrono |
| `uvicorn[standard]` | 0.27.0 | Servidor ASGI (com websockets e http/2) |
| `python-multipart` | 0.0.9 | Obrigatório para FastAPI processar `Form` data e upload de arquivos (PDFs) |
| `sqlalchemy` | 2.0.25 | ORM — modelos e queries |
| `asyncpg` | 0.29.0 | Driver async PostgreSQL (obrigatório com `create_async_engine`) |
| `alembic` | 1.13.1 | Migrations do banco |
| `redis` | 5.0.1 | Cache + broker Celery |
| `cryptography` | 42.0.0 | AES-256 para CPFs (Fernet) |
| `python-jose[cryptography]` | 3.3.0 | Geração e validação de JWTs |
| `bcrypt` | 4.1.2 | Hash de senhas |
| `httpx` | 0.26.0 | Cliente HTTP async (chamadas a APIs externas) |
| `pydantic` | 2.5.0 | Validação de dados |
| `pydantic-settings` | 2.1.0 | `BaseSettings` para variáveis de ambiente (separado do pydantic desde v2) |
| `email-validator` | 2.1.0 | Obrigatório para usar `EmailStr` no Pydantic |
| `prometheus-client` | 0.19.0 | Métricas expostas no `/metrics` |
| `sentry-sdk[fastapi]` | 1.40.0 | Rastreamento de erros em produção |
| `structlog` | 24.1.0 | Logging estruturado (JSON em prod, colorido em dev) |
| `python-dotenv` | 1.0.0 | Carrega `.env` no Alembic (`env.py`) antes das migrations |

---

### 8.2 `requirements-f1.txt`

**Localização:** [`requirements-f1.txt`](../../requirements-f1.txt)

Contém as dependências **específicas da Feature 1** (IA + WhatsApp + Celery). A primeira linha inclui automaticamente todas as deps base:

```
-r requirements-base.txt
```

| Pacote | Versão | Para quê |
|---|---|---|
| `langchain` | 0.2.16 | Integração de LLMs e ferramentas |
| `langgraph` | 0.2.28 | Workflow stateful da IA (orquestrador) |
| `anthropic` | 0.34.2 | Cliente Claude API (IA conversacional) |
| `openai` | 1.50.2 | Cliente Whisper API (transcrição de áudios) |
| `langchain-anthropic` | 0.1.23 | Integração nativa LangChain + Claude (`ChatAnthropic`) |
| `langchain-openai` | 0.1.25 | Integração nativa LangChain + OpenAI (`ChatOpenAI`) |
| `langchain-community` | 0.2.16 | Ferramentas de busca, loaders de docs e utilitários do agente |
| `tiktoken` | 0.7.0 | Contagem de tokens para gerenciar contexto e memória |
| `celery` | 5.3.6 | Workers assíncronos (monitoramento, notificações) |
| `flower` | 2.0.1 | UI web de monitoramento do Celery |
| `aiohttp` | 3.9.3 | HTTP async (para workers Celery) |
| `pydub` | 0.25.1 | Conversão ogg→mp3 de áudios WhatsApp |
| `google-api-python-client` | 2.116.0 | Cliente Google Sheets API |
| `google-auth` | 2.27.0 | Autenticação service account Google |

> **Nota sobre `pydub`:** requer o binário `ffmpeg` instalado no sistema operacional.
> - macOS: `brew install ffmpeg`
> - Docker: já incluído no `Dockerfile.f1` via `apt install ffmpeg`

> **Versões do ecossistema LangChain:** As versões originais (`langchain==0.1.0`, `langgraph==0.0.20`, `anthropic==0.18.0`) causavam conflito de dependência com `langsmith` — `langchain 0.1.x` exige `langsmith<0.1`, mas `langchain-anthropic` e `langchain-community` exigem `langsmith>=0.1.0`. A solução foi migrar para `langchain>=0.2.0`, que usa `langsmith>=0.1.0` de forma consistente em todo o ecossistema.

---

### 8.3 Instalar e Verificar

#### Criar virtualenv e instalar

```bash
# Criar virtualenv com Python 3.12
python3.12 -m venv .venv

# Ativar (macOS/Linux)
source .venv/bin/activate

# Atualizar pip
pip install --upgrade pip

# Instalar deps da Feature 1 (inclui base automaticamente)
pip install -r requirements-f1.txt

# Instalar deps de dev (pytest, ruff, black, mypy, pre-commit)
pip install -e ".[dev]"
```

Ou usando o Makefile (faz tudo em um comando):

```bash
make setup
```

#### Verificar instalação

```bash
python -c "import fastapi, sqlalchemy, anthropic, langgraph, celery, structlog; print('OK')"
# → OK
```

Ou via Makefile:

```bash
make verify-install
# → ✅ Todas as dependências OK!
```

#### Estrutura de grupos

```
requirements-base.txt        ← instala shared/ (core)
    └── requirements-f1.txt  ← instala feature_1/ + base

pyproject.toml [dev]         ← instala ferramentas de desenvolvimento
    pytest, ruff, black, mypy, pre-commit, factory-boy, faker
```

---

## 9. Fluxo de Setup Inicial

Para um novo desenvolvedor começar do zero:

```bash
# 1. Clonar repositório
git clone <url-do-repo>
cd PROJETO-IA-JURIDICA

# 2. Instalar Python 3.12 (se necessário)
# macOS: brew install python@3.12
# Ubuntu: sudo apt install python3.12

# 3. Rodar setup completo
make setup
# → cria .venv
# → instala requirements-f1.txt
# → copia .env.example para .env

# 4. Preencher credenciais no .env
nano .env

# 5. Subir serviços de infraestrutura via Docker
make docker-up
# → postgres:16 em :5432
# → redis:7 em :6379
# → evolution-api em :8080

# 6. Aplicar migrations e popular dados de dev
make init-db
# → alembic upgrade head
# → seed_data.py

# 7. Verificar instalação
make verify-install

# 8. Iniciar servidor de desenvolvimento
make dev
# → http://localhost:8000
# → http://localhost:8000/docs (Swagger UI)
```

---

## 10. Variáveis de Ambiente — Referência Completa

| Variável | Obrigatória | Default | Descrição |
|---|---|---|---|
| `ENVIRONMENT` | Não | `development` | Ambiente atual |
| `LOG_LEVEL` | Não | `INFO` | Nível de log |
| `DATABASE_URL` | **Sim** | — | URL PostgreSQL com asyncpg |
| `REDIS_URL` | **Sim** | — | URL Redis (database 0) |
| `CELERY_BROKER_URL` | **Sim** | — | Redis para fila Celery (database 1) |
| `CELERY_RESULT_BACKEND` | **Sim** | — | Redis para resultados Celery (database 2) |
| `ANTHROPIC_API_KEY` | **Sim** | — | API key Claude (IA conversacional) |
| `OPENAI_API_KEY` | **Sim** | — | API key Whisper (transcrição áudio) |
| `EVOLUTION_API_URL` | **Sim** | — | URL da instância Evolution API |
| `EVOLUTION_API_KEY` | **Sim** | — | API key Evolution API |
| `JUSBRASIL_API_KEY` | **Sim** | — | API key Jusbrasil |
| `JWT_SECRET_KEY` | **Sim** | — | Chave secreta para assinar JWTs |
| `JWT_ALGORITHM` | Não | `HS256` | Algoritmo JWT |
| `JWT_EXPIRATION_MINUTES` | Não | `60` | Validade do access token |
| `ENCRYPTION_KEY` | **Sim** | — | Chave Fernet (AES-256) para CPFs |
| `SENTRY_DSN` | Não | `None` | DSN Sentry (deixar vazio em dev) |
| `GOOGLE_SHEETS_ID` | Não | `None` | ID da planilha Google Sheets (integração opcional no MVP local) |
| `GOOGLE_CREDENTIALS_PATH` | Não | `None` | Caminho para JSON de service account Google |

---

## 11. `.pre-commit-config.yaml` (Fase 0.3)

**Localização:** [`.pre-commit-config.yaml`](../../.pre-commit-config.yaml)

### O que faz

Configura hooks que rodam **automaticamente antes de cada `git commit`**, garantindo que código com problemas de lint, formatação ou tipos nunca entre no repositório.

### Instalação

```bash
# Instalar o pre-commit no virtualenv (já incluído em [dev] do pyproject.toml)
pip install pre-commit

# Registrar os hooks no repositório Git local (feito uma vez por dev)
pre-commit install
```

Após rodar `pre-commit install`, os hooks passam a ser executados automaticamente em todo `git commit`.

### Hooks configurados

| Hook | Versão | O que faz |
|---|---|---|
| `ruff` | v0.2.1 | Linting + correção automática de imports e estilo |
| `black` | 24.1.1 | Formatação do código (PEP 8 + opinionated) |
| `mypy` | v1.8.0 | Checagem estática de tipos |
| `trailing-whitespace` | pre-commit-hooks | Remove espaços no final de linhas |
| `end-of-file-fixer` | pre-commit-hooks | Garante newline no final de cada arquivo |
| `check-yaml` | pre-commit-hooks | Valida sintaxe de arquivos YAML |
| `check-json` | pre-commit-hooks | Valida sintaxe de arquivos JSON |
| `check-merge-conflict` | pre-commit-hooks | Detecta marcadores de conflito esquecidos |
| `debug-statements` | pre-commit-hooks | Detecta `pdb`, `ipdb`, `breakpoint()` acidentais |

### Fluxo de uso

```bash
# Commit normal — hooks rodam automaticamente
git add .
git commit -m "feat: adicionar endpoint de processos"
# → ruff verifica e corrige imports
# → black formata o código
# → mypy checa tipos
# → hooks gerais verificam YAML, JSON, whitespace
# Se tudo passar → commit criado
# Se algum hook falhar → commit abortado, você corrige e tenta novamente

# Rodar hooks manualmente (sem fazer commit)
pre-commit run --all-files

# Rodar apenas um hook específico
pre-commit run ruff --all-files
pre-commit run black --all-files
pre-commit run mypy --all-files

# Pular hooks em situação de emergência (não recomendado)
git commit --no-verify -m "mensagem"
```

### Relação com o Makefile

Os hooks do pre-commit e os targets do Makefile fazem a mesma coisa — a diferença é o momento:

| Ferramenta | Quando roda | Uso ideal |
|---|---|---|
| `pre-commit` | Automático no `git commit` | Barreira final antes de commitar |
| `make lint` | Manual, quando quiser | Durante desenvolvimento, para checar rapidamente |
| `make format` | Manual, quando quiser | Para formatar antes do commit |
| `make lint-check` | CI/CD pipeline | Verificação sem correção automática |

> **Dica:** O `ruff` com `--fix` (configurado no hook) corrige automaticamente boa parte dos problemas de lint. Se o hook falhar e corrigir arquivos, basta re-adicionar os arquivos corrigidos (`git add .`) e tentar o commit novamente.

---

## 12. Entry Point Uvicorn (Fase 0.6)

### O que foi criado

Para o servidor Uvicorn conseguir importar a aplicação, dois arquivos são necessários:

**`feature_1_ia_personalizada/__init__.py`** — marca o diretório como pacote Python.

**`feature_1_ia_personalizada/api/app.py`** — define a instância `app` do FastAPI que o Uvicorn importa:

```python
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
```

> **Fase 2** expandirá este arquivo com: routers, middlewares (CORS, auth, rate limit), Sentry, Prometheus e event handlers de startup/shutdown.

### Comando de execução

```bash
# Via Makefile (recomendado)
make dev

# Equivalente manual
uvicorn feature_1_ia_personalizada.api.app:app \
    --host 0.0.0.0 \
    --port 8000 \
    --reload \
    --log-level info
```

### Por que underscores no nome da pasta?

O Python exige que nomes de pacotes (pastas importáveis) usem **underscores**, não hífens.

```bash
# ❌ Inválido como módulo Python
feature-1-ia-personalizada/

# ✅ Válido — importável normalmente
feature_1_ia_personalizada/
```

O nome com hífens causaria `ModuleNotFoundError` ao tentar importar `feature-1-ia-personalizada.api.app`.

### Verificar que o import funciona

Com o virtualenv ativado e as deps instaladas:

```bash
python -c "from feature_1_ia_personalizada.api.app import app; print('Entry point OK:', app.title)"
# → Entry point OK: Concierge Jurídico Digital
```

---

> **Última atualização:** Fevereiro 2026 — **Fase 0 completa** (0.1 ✅ | 0.2 ✅ | 0.3 ✅ | 0.4 ✅ | 0.5 ✅ | 0.6 ✅)
>
> **Correções aplicadas no setup real (fevereiro 2026):**
> - `pyproject.toml`: build-backend corrigido de `setuptools.backends.legacy:build` → `setuptools.build_meta`
> - `requirements-base.txt`: adicionados `python-multipart`, `email-validator` e `python-dotenv` que estavam faltando
> - `requirements-f1.txt`: ecossistema LangChain migrado para `0.2.x` — versões originais (`langchain==0.1.0`, etc.) causavam conflito irresolvível com `langsmith`; adicionados `langchain-anthropic`, `langchain-openai`, `langchain-community` e `tiktoken` que estavam ausentes
>
> **Próxima etapa:** Fase 1 — Shared (models, schemas, security, utils, database)
