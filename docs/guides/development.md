# Guia de Desenvolvimento — Estrutura Raiz do Projeto

> Documento de referência para a **Fase 0.1** do Concierge Jurídico Digital.
> Cobre a estrutura base do repositório e como utilizar cada arquivo criado.

---

## Índice

1. [Visão Geral da Estrutura](#1-visão-geral-da-estrutura)
2. [.gitignore](#2-gitignore)
3. [pyproject.toml](#3-pyprojecttoml)
4. [Makefile](#4-makefile)
5. [.env.example](#5-envexample)
6. [Docker](#6-docker)
   - [docker-compose.yml](#61-docker-composeyml)
   - [Dockerfile.f1](#62-dockerfilef1)
7. [Fluxo de Setup Inicial](#7-fluxo-de-setup-inicial)
8. [Variáveis de Ambiente — Referência Completa](#8-variáveis-de-ambiente--referência-completa)

---

## 1. Visão Geral da Estrutura

Após a Fase 0.1, a raiz do repositório ficou assim:

```
PROJETO-IA-JURIDICA/
│
├── .gitignore                          ← O que o Git deve ignorar
├── .env.example                        ← Template de variáveis de ambiente
├── .env                                ← Suas credenciais reais (NÃO commitar!)
│
├── pyproject.toml                      ← Configuração do projeto Python
├── Makefile                            ← Atalhos de comandos (setup, dev, test...)
│
├── requirements-base.txt               ← Deps compartilhadas (criadas na Fase 0.4)
├── requirements-f1.txt                 ← Deps da Feature 1 (criadas na Fase 0.4)
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
| **Segredos** | `.env`, `.env.local`, `.env.*.local` | Contém credenciais reais — NUNCA commitar |
| **IDEs** | `.vscode/`, `.idea/`, `*.swp`, `.DS_Store` | Configurações pessoais de cada desenvolvedor |
| **Testes** | `.pytest_cache/`, `.coverage`, `htmlcov/` | Resultados de teste são gerados localmente |
| **ML Models** | `*.pkl`, `*.joblib`, `*.h5` | Modelos treinados são grandes demais para Git (usar S3) |
| **Terraform** | `**/.terraform/`, `*.tfstate` | Estado da infra contém dados sensíveis |
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

---

## 4. `Makefile`

**Localização:** [`Makefile`](../../Makefile)

### O que faz

Centraliza todos os comandos frequentes do projeto em atalhos simples. Em vez de memorizar comandos longos, você usa `make <comando>`.

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

## 7. Fluxo de Setup Inicial

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

## 8. Variáveis de Ambiente — Referência Completa

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

---

> **Última atualização:** Fevereiro 2026 — Fase 0.1 concluída
>
> **Próxima fase:** [0.2 — Banco de Dados Local](./database_setup.md) (configurar Alembic + criar migration inicial)
