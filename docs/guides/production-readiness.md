# Plano de Production Readiness — Concierge Jurídico Digital

> **Objetivo:** Levar a Feature 1 (IA Personalizada) de MVP avançado para produção real.
> **Auditoria realizada em:** Fevereiro 2026 | **Última atualização:** Março 2026 (Sprint 1 concluída parcialmente)
> **Estimativa total:** 8–10 sprints (2–3 meses com 2 engenheiros)

---

## Índice

1. [Diagnóstico Atual](#1-diagnóstico-atual)
2. [Sprint 1 — Lógica de Negócio Quebrada](#2-sprint-1--lógica-de-negócio-quebrada-blockers-críticos)
3. [Sprint 2 — Segurança](#3-sprint-2--segurança)
4. [Sprint 3–4 — Testes e CI/CD](#4-sprint-34--testes-e-cicd)
5. [Sprint 5–6 — Observabilidade e Alertas](#5-sprint-56--observabilidade-e-alertas)
6. [Sprint 7–8 — Infraestrutura de Produção](#6-sprint-78--infraestrutura-de-produção)
7. [Sprint 9–10 — Resiliência e Escalabilidade](#7-sprint-910--resiliência-e-escalabilidade)
8. [Checklist Final de Deploy](#8-checklist-final-de-deploy)

---

## 1. Diagnóstico Atual

### Resumo por área

| Área | % Completo | Pronto Prod? | Principal gap |
|---|---|---|---|
| API routes + middleware | 90% | ⚠️ Quase | CORS aberto, sem error handler global |
| Auth JWT + segurança | 95% | ✅ Sim | — |
| Workers Celery | 80% | ⚠️ Quase | Imports Jusbrasil/DataJud comentados (aguarda Fase 3) |
| Banco de dados + ORM | 95% | ✅ Sim | — |
| Logging estruturado | 95% | ✅ Sim | Falta centralização em produção |
| Métricas Prometheus | 90% | ⚠️ Quase | Sem servidor Prometheus/Grafana |
| Health checks | 95% | ✅ Sim | — |
| Testes | 40% | ❌ Não | Sem testes HTTP, cobertura desconhecida |
| CI/CD | 30% | ❌ Não | Sem GitHub Actions |
| Docker | 85% | ⚠️ Quase | Sem resource limits, sem registry |
| Secrets management | 10% | ❌ Não | `.env` no git, sem Vault |
| APIs externas (Jusbrasil/DataJud) | 15% | ❌ Não | Mocks, imports comentados |
| Alertas | 0% | ❌ Não | Nenhuma regra de alerta |

### O que está funcionando hoje

- ✅ Estrutura FastAPI completa (rotas, middlewares, auth, rate limit)
- ✅ JWT + bcrypt + Fernet AES-256 + LGPD (audit trail, anonimização, exportação)
- ✅ Health checks detalhados (6 serviços em paralelo com timeout)
- ✅ Logging estruturado com structlog + JSON em produção
- ✅ Métricas Prometheus declaradas e incrementadas corretamente
- ✅ Docker multi-stage com usuário não-root + healthchecks
- ✅ Alembic migrations configurado
- ✅ Queries ORM em todos os workers (`shared/database/worker_queries.py`)
- ✅ `WhatsAppService.enviar_mensagem` integrado ao `EvolutionClient` real
- ✅ `whatsapp.py` — `enviar_notificacao_andamento` e `enviar_sem_movimentacao` implementados
- ✅ Celery Beat tasks de relacionamento executam sem `NotImplementedError`

### O que ainda está quebrado (não chega em produção assim)

- ❌ `DataJudClient`, `JusbrasilClient`, `JuridicalTranslator` com imports comentados em `monitor_processos.py` — `monitorar_processos` busca dados do banco mas não processa andamentos (aguarda Fase 3)
- ❌ Webhook WhatsApp aceita qualquer payload sem validação de assinatura
- ❌ CORS aberto para `*` — vulnerabilidade de CSRF

---

## 2. Sprint 1 — Lógica de Negócio Quebrada (Blockers Críticos)

> **Meta:** Todos os workers Celery executam sem erros. Monitor de processos busca dados reais do banco.

### 2.1 Implementar queries ORM nos workers ✅ IMPLEMENTADO

**Arquivo criado:** `shared/database/worker_queries.py`

Todas as queries foram centralizadas em um módulo único. A abordagem adotada foi `asyncio.run()` sobre o engine asyncpg existente (em vez de criar um engine psycopg2 separado), evitando adicionar dependências. Cada função pública é um wrapper síncrono que executa a coroutine no event loop.

| Função (worker_queries.py) | Query |
|---|---|
| `query_processos_monitorados(limite)` | `SELECT ... WHERE monitoramento_ativo = true LIMIT :limite` |
| `query_processo_por_id(id)` | `SELECT ... WHERE id = :id` |
| `update_ultimo_andamento(id, texto, data_iso)` | `UPDATE processos SET ultimo_andamento, data_ultimo_andamento WHERE id` |
| `query_processo_ativo_do_cliente(id_cliente)` | `SELECT ... WHERE cliente_id = :id AND status = 'ativo' LIMIT 1` |
| `insert_interacao(...)` | `INSERT INTO interacoes` (obtém `escritorio_id` automaticamente do cliente) |
| `query_ultima_interacao_batch(ids)` | `SELECT cliente_id, MAX(created_at) ... GROUP BY cliente_id` |
| `enviar_mensagem_whatsapp(id_cliente, telefone, texto)` | Resolve `webhook_whatsapp_instance` + chama `EvolutionClient.enviar_texto` |
| `query_processo_e_cliente(id)` | JOIN processos + clientes com `selectinload` |
| `query_processos_sem_movimentacao()` | `WHERE data_ultimo_andamento < NOW()-30d OR NULL` com cliente eager-loaded |
| `query_clientes_para_pesquisa()` | `WHERE ativo = true AND aceite_lgpd = true` |

> **Nota:** Para migrar para psycopg2 (engine síncrono dedicado), substituir `asyncio.run(coro)` por `Session(_engine)` e adicionar `psycopg2-binary` ao `requirements-f1.txt`. A interface pública das funções não muda.

### 2.2 Descomentar imports da Fase 3 ⏳ AGUARDA FASE 3

**Arquivo:** `feature_1_ia_personalizada/workers/monitor_processos.py` linhas 12–18

Remover os comentários e garantir que os clientes existem e funcionam:

```python
# ANTES (quebrado):
# from feature_1_ia_personalizada.services.legal_data.datajud_client import DataJudClient
# from feature_1_ia_personalizada.services.legal_data.jusbrasil_client import JusbrasilClient

# DEPOIS:
from feature_1_ia_personalizada.services.legal_data.datajud_client import DataJudClient
from feature_1_ia_personalizada.services.legal_data.jusbrasil_client import JusbrasilClient
```

**Verificar que os clientes têm implementação real** (não apenas mocks) em:
- `services/legal_data/datajud_client.py`
- `services/legal_data/jusbrasil_client.py`

### 2.3 Implementar funções de banco em send_notifications.py ✅ IMPLEMENTADO

**Arquivo:** `feature_1_ia_personalizada/workers/send_notifications.py`

| Função | Delegação |
|---|---|
| `buscar_processo_e_cliente(id_processo)` | → `query_processo_e_cliente` em `worker_queries.py` |
| `buscar_processos_sem_movimentacao()` | → `query_processos_sem_movimentacao` em `worker_queries.py` |
| `buscar_clientes_para_pesquisa()` | → `query_clientes_para_pesquisa` em `worker_queries.py` |
| `registrar_interacao(id_cliente, id_processo, tipo, dados)` | → `insert_interacao` em `worker_queries.py` |

`enviar_notificacao_andamento` agora trata `None` quando o processo não é encontrado (retorna `{"status": "processo_nao_encontrado"}` em vez de lançar `TypeError`).

### 2.4 Implementar funções de integração em mensagens_relacionamento.py ✅ IMPLEMENTADO

**Arquivo:** `feature_1_ia_personalizada/workers/mensagens_relacionamento.py`

| Função | Implementação |
|---|---|
| `WhatsAppService.enviar_mensagem(id_cliente, telefone, texto)` | Resolve `webhook_whatsapp_instance` via JOIN `clientes→escritorios` + chama `EvolutionClient.enviar_texto`. Assinatura recebeu `id_cliente` (necessário para resolver a instância). |
| `buscar_processo_ativo_do_cliente(id_cliente)` | → `query_processo_ativo_do_cliente` em `worker_queries.py`, converte para dataclass local `Processo` |
| `salvar_interacao(id_cliente, id_processo, texto, metadata_json)` | → `insert_interacao` em `worker_queries.py` |
| ~~`buscar_data_ultima_interacao(id_cliente)`~~ | **Removida** — substituída por `query_ultima_interacao_batch` (uma query para todos os clientes, eliminando N+1 em `verificar_clientes_sem_contato`) |

**Observação arquitetural:** as tasks lêem dados de clientes **diretamente do Google Sheets** (via `GoogleSheetsClient.get_clientes()`), não do banco. Isso é intencional — a planilha é a fonte de verdade para o módulo de relacionamento. As variáveis `GOOGLE_CREDENTIALS_PATH` e `GOOGLE_SHEETS_ID` devem estar configuradas em produção para essas tasks funcionarem.

### 2.5 Resolver NotImplementedError no whatsapp.py ✅ IMPLEMENTADO

**Arquivo:** `feature_1_ia_personalizada/services/messaging/whatsapp.py`

Implementado via helper privado `_obter_contexto_processo(processo_id)` que usa o async session factory diretamente (o serviço já é `async def`, sem necessidade de `asyncio.run()`):

```python
async def _obter_contexto_processo(self, processo_id: int) -> Optional[tuple[int, int]]:
    async with async_session_factory() as session:
        result = await session.execute(
            select(ProcessoModel.escritorio_id, ProcessoModel.cliente_id)
            .where(ProcessoModel.id == processo_id)
        )
        row = result.one_or_none()
    if row is None:
        logger.warning("processo_nao_encontrado", processo_id=processo_id)
        return None
    return row.escritorio_id, row.cliente_id
```

- `enviar_notificacao_andamento` — usa o helper e formata o texto de andamento
- `enviar_sem_movimentacao` — usa o helper e envia mensagem de sem movimentação

### Critério de aceite da Sprint 1

- [x] Beat executa `verificar_aniversarios_diarios` sem exceção ✅
- [x] Beat executa `verificar_datas_comemorativas` sem exceção ✅
- [x] Beat executa `verificar_clientes_sem_contato` sem exceção ✅
- [x] `send_notifications` — nenhuma função lança `NotImplementedError` ✅
- [x] `whatsapp.py` — zero `NotImplementedError` ✅
- [ ] `make worker` roda por 10 minutos sem `NameError` → bloqueado pelo item 2.2 (imports Fase 3 comentados em `monitor_processos.py`)
- [ ] Task `monitorar_processos` processa andamentos reais → bloqueado pelo item 2.2

---

## 3. Sprint 2 — Segurança

> **Meta:** Nenhuma vulnerabilidade conhecida do OWASP Top 10. Secrets fora do repositório.

### 3.1 Remover secrets do repositório

**Problema:** `.env` pode ter sido commitado com credenciais reais.

```bash
# Verificar se .env está no histórico
git log --oneline --all -- .env

# Se estiver, limpar o histórico (CUIDADO — reescreve commits)
git filter-branch --force --index-filter \
  "git rm --cached --ignore-unmatch .env" \
  --prune-empty --tag-name-filter cat -- --all

# Após limpar, forçar push (avisar o time antes)
git push origin --force --all
```

**Após limpar:**
1. Revogar e regenerar TODAS as chaves comprometidas (Anthropic, OpenAI, Evolution, JWT, Fernet)
2. Garantir que `.gitignore` tem `.env` e `.env.*` (já tem — manter)
3. Documentar geração de chaves em `docs/guides/secrets.md`

### 3.2 Restringir CORS

**Arquivo:** `feature_1_ia_personalizada/api/app.py`

```python
# ANTES (vulnerável):
allow_origins=["*"]

# DEPOIS:
from shared.config.settings import settings

CORS_ORIGINS = (
    settings.CORS_ALLOWED_ORIGINS.split(",")
    if settings.ENVIRONMENT == "production"
    else ["*"]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
```

**Adicionar em `shared/config/settings.py`:**

```python
CORS_ALLOWED_ORIGINS: str = "https://seu-dominio.com"
```

### 3.3 Validar assinatura do webhook WhatsApp

**Arquivo:** `feature_1_ia_personalizada/api/routes/webhook_whatsapp.py`

A Evolution API envia um header `apikey` em cada requisição de webhook. Validar antes de processar:

```python
from fastapi import Header, HTTPException

@router.post("")
async def receber_webhook(
    payload: dict,
    apikey: str = Header(None, alias="apikey"),
):
    if apikey != settings.EVOLUTION_API_KEY:
        raise HTTPException(status_code=401, detail="Webhook não autorizado")
    # ... resto do handler
```

### 3.4 Error handler global

**Arquivo:** `feature_1_ia_personalizada/api/app.py`

Sem um handler global, erros não capturados retornam stack traces para o cliente em produção:

```python
from fastapi.responses import JSONResponse
from fastapi import Request

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("erro_nao_tratado", path=request.url.path, erro=str(exc), exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Erro interno do servidor"},
    )
```

### 3.5 Validar formato das chaves no startup

**Arquivo:** `shared/config/settings.py`

```python
from pydantic import Field, field_validator
from cryptography.fernet import Fernet

class Settings(BaseSettings):
    JWT_SECRET_KEY: str = Field(min_length=32)
    ENCRYPTION_KEY: str

    @field_validator("ENCRYPTION_KEY")
    @classmethod
    def validar_fernet_key(cls, v: str) -> str:
        try:
            Fernet(v.encode())
        except Exception:
            raise ValueError("ENCRYPTION_KEY deve ser uma chave Fernet válida (use Fernet.generate_key())")
        return v
```

### 3.6 Mascarar dados sensíveis nos logs

Verificar que CPFs, tokens e senhas nunca aparecem em logs estruturados. Adicionar filtro ao structlog:

```python
# shared/config/logging.py
import re

_PATTERNS = [
    (re.compile(r"\d{3}\.\d{3}\.\d{3}-\d{2}"), "***.***.***-**"),  # CPF
    (re.compile(r"sk-ant-[A-Za-z0-9-_]+"), "sk-ant-***"),           # Anthropic key
    (re.compile(r"Bearer [A-Za-z0-9._-]+"), "Bearer ***"),           # JWT header
]

def _mask_sensitive(logger, method, event_dict):
    for key, value in event_dict.items():
        if isinstance(value, str):
            for pattern, replacement in _PATTERNS:
                value = pattern.sub(replacement, value)
            event_dict[key] = value
    return event_dict
```

### Critério de aceite da Sprint 2

- [ ] `git log --oneline --all -- .env` não retorna nenhum commit
- [ ] Request para `/webhook/whatsapp` sem header `apikey` correto retorna 401
- [ ] Request cross-origin de domínio não autorizado retorna CORS error em produção
- [ ] CPF e tokens não aparecem nos logs em texto claro

---

## 4. Sprint 3–4 — Testes e CI/CD

> **Meta:** ≥70% de cobertura de código. Nenhum PR entra em main sem passar nos testes.

### 4.1 Testes HTTP das rotas FastAPI

Criar arquivo `feature_1_ia_personalizada/tests/integration/test_api_routes.py` usando `httpx.AsyncClient`:

```python
import pytest
from httpx import AsyncClient, ASGITransport
from feature_1_ia_personalizada.api.app import app

@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

class TestHealth:
    async def test_health_basico(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    async def test_health_ready_sem_db(self, client):
        # Com DB mockado como indisponível → deve retornar 503
        resp = await client.get("/health/ready")
        assert resp.status_code in (200, 503)

class TestAuth:
    async def test_login_credenciais_invalidas(self, client):
        resp = await client.post("/auth/login", json={"email": "x@x.com", "password": "wrong"})
        assert resp.status_code == 401

    async def test_rota_protegida_sem_token(self, client):
        resp = await client.get("/chat/history/1")
        assert resp.status_code == 401

class TestWebhook:
    async def test_webhook_sem_apikey(self, client):
        resp = await client.post("/webhook/whatsapp", json={})
        assert resp.status_code == 401

    async def test_webhook_payload_invalido(self, client, mocker):
        mocker.patch("...settings.EVOLUTION_API_KEY", "test-key")
        resp = await client.post(
            "/webhook/whatsapp",
            json={"invalid": "payload"},
            headers={"apikey": "test-key"},
        )
        assert resp.status_code in (200, 422)
```

**Rotas que precisam de teste:**

| Rota | Cenários |
|---|---|
| `GET /health` | 200 ok |
| `GET /health/ready` | 200 ok, 503 sem DB |
| `POST /auth/login` | 200 com credenciais válidas, 401 inválidas |
| `POST /auth/refresh` | 200 com token válido, 401 expirado |
| `GET /chat/history/{id}` | 200 autenticado, 401 sem token |
| `POST /webhook/whatsapp` | 401 sem apikey, 200 payload válido |
| `GET /metrics` | 200 com conteúdo Prometheus |

### 4.2 Definir meta de cobertura

**Arquivo:** `pyproject.toml`

```toml
[tool.pytest.ini_options]
addopts = """
  -v
  --cov=feature_1_ia_personalizada
  --cov=shared
  --cov-report=html
  --cov-report=term-missing
  --cov-fail-under=70
"""
```

O `--cov-fail-under=70` faz o pytest retornar exit code 1 se a cobertura ficar abaixo de 70% — necessário para o CI bloquear PRs.

### 4.3 GitHub Actions — Pipeline de CI

Criar `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  pull_request:
    branches: [main, develop]
  push:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_USER: concierge
          POSTGRES_PASSWORD: concierge_pass
          POSTGRES_DB: concierge_test
        ports: ["5432:5432"]
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

      redis:
        image: redis:7-alpine
        ports: ["6379:6379"]
        options: --health-cmd "redis-cli ping" --health-interval 5s --health-retries 5

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: "pip"

      - name: Instalar dependências
        run: pip install -r requirements-f1.txt && pip install -e ".[dev]"

      - name: Lint (ruff)
        run: ruff check .

      - name: Formatação (black)
        run: black --check .

      - name: Tipos (mypy)
        run: mypy feature_1_ia_personalizada shared

      - name: Testes
        env:
          DATABASE_URL: postgresql+asyncpg://concierge:concierge_pass@localhost:5432/concierge_test
          REDIS_URL: redis://localhost:6379/0
          CELERY_BROKER_URL: redis://localhost:6379/1
          CELERY_RESULT_BACKEND: redis://localhost:6379/2
          ANTHROPIC_API_KEY: sk-ant-test-key
          OPENAI_API_KEY: sk-test-key
          EVOLUTION_API_URL: http://localhost:8080
          EVOLUTION_API_KEY: test-evolution-key
          JWT_SECRET_KEY: test-jwt-secret-key-minimum-32-chars-ok
          ENCRYPTION_KEY: ${{ secrets.TEST_ENCRYPTION_KEY }}
          JUSBRASIL_API_KEY: test-jusbrasil-key
        run: pytest --tb=short

      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          token: ${{ secrets.CODECOV_TOKEN }}

  docker-build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build imagem Docker
        run: docker build -t concierge-f1:test -f infrastructure/docker/Dockerfile.f1 .
```

### 4.4 GitHub Actions — Deploy (CD)

Criar `.github/workflows/deploy.yml` para push em `main`:

```yaml
name: Deploy

on:
  push:
    branches: [main]
    tags: ["v*"]

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Login no registry
        uses: docker/login-action@v3
        with:
          registry: ghcr.io  # ou ECR, Docker Hub
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Build e push
        uses: docker/build-push-action@v5
        with:
          context: .
          file: infrastructure/docker/Dockerfile.f1
          push: true
          tags: |
            ghcr.io/${{ github.repository }}/concierge-f1:latest
            ghcr.io/${{ github.repository }}/concierge-f1:${{ github.sha }}
```

### Critério de aceite da Sprint 3–4

- [ ] `pytest` retorna 0 com cobertura ≥ 70%
- [ ] PR em `main` bloqueia merge se testes falham
- [ ] Build Docker passa no CI para cada PR
- [ ] `black --check` e `ruff check` passam no CI

---

## 5. Sprint 5–6 — Observabilidade e Alertas

> **Meta:** Time sabe quando algo quebra antes do cliente reclamar.

### 5.1 Configurar Prometheus + Grafana via Docker Compose

**Arquivo:** `infrastructure/docker/docker-compose.yml`

Adicionar serviços de monitoramento:

```yaml
  prometheus:
    image: prom/prometheus:v2.50.0
    volumes:
      - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    ports:
      - "9090:9090"
    command:
      - "--config.file=/etc/prometheus/prometheus.yml"
      - "--storage.tsdb.retention.time=15d"

  grafana:
    image: grafana/grafana:10.3.0
    environment:
      GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_PASSWORD:-admin}
    volumes:
      - grafana_data:/var/lib/grafana
      - ./grafana/dashboards:/etc/grafana/provisioning/dashboards
    ports:
      - "3000:3000"
    depends_on: [prometheus]
```

**Criar** `infrastructure/docker/prometheus/prometheus.yml`:

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

rule_files:
  - "alerts.yml"

alerting:
  alertmanagers:
    - static_configs:
        - targets: ["alertmanager:9093"]

scrape_configs:
  - job_name: "concierge-api"
    static_configs:
      - targets: ["app-f1:8000"]
    metrics_path: "/metrics"
    scrape_interval: 15s
```

### 5.2 Regras de alerta Prometheus

**Criar** `infrastructure/docker/prometheus/alerts.yml`:

```yaml
groups:
  - name: concierge_criticos
    rules:
      - alert: APIDown
        expr: up{job="concierge-api"} == 0
        for: 1m
        annotations:
          summary: "API Concierge fora do ar"
          description: "O endpoint /metrics não está respondendo há 1 minuto"

      - alert: TaxaErroIAAlta
        expr: |
          rate(ia_orchestrator_errors_total[5m]) /
          rate(ia_orchestrator_flow_total[5m]) > 0.05
        for: 2m
        annotations:
          summary: "Taxa de erro da IA acima de 5%"
          description: "{{ $value | humanizePercentage }} das interações estão falhando"

      - alert: LatenciaWebhookAlta
        expr: histogram_quantile(0.95, rate(webhook_processing_time_seconds_bucket[5m])) > 10
        for: 5m
        annotations:
          summary: "Webhook processando lentamente (p95 > 10s)"

      - alert: WorkerCeleryForaDar
        expr: celery_workers_active == 0
        for: 3m
        annotations:
          summary: "Nenhum worker Celery respondendo"

      - alert: RedisIndisponivel
        expr: redis_connected_clients == 0
        for: 1m
        annotations:
          summary: "Redis sem clientes conectados — possível queda"
```

### 5.3 Dashboard Grafana

Criar `infrastructure/docker/grafana/dashboards/concierge.json` com painéis:

| Painel | Query |
|---|---|
| Requests/min | `rate(ia_requests_total[1m]) * 60` |
| Taxa de erro | `rate(ia_orchestrator_errors_total[5m]) / rate(ia_orchestrator_flow_total[5m])` |
| Latência p95 webhook | `histogram_quantile(0.95, rate(webhook_processing_time_seconds_bucket[5m]))` |
| Mensagens WhatsApp recebidas | `rate(whatsapp_messages_received_total[5m]) * 60` |
| Processos monitorados ativos | `processos_monitorados_total` |
| Fallback IA ativo | `rate(ia_fallback_used_total[5m]) * 60` |

### 5.4 Configurar Sentry em produção

**Arquivo:** `feature_1_ia_personalizada/api/app.py`

```python
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from sentry_sdk.integrations.celery import CeleryIntegration

if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.ENVIRONMENT,
        integrations=[
            FastApiIntegration(transaction_style="endpoint"),
            SqlalchemyIntegration(),
            CeleryIntegration(),
        ],
        traces_sample_rate=0.1,   # 10% das requisições para performance
        profiles_sample_rate=0.1,
        send_default_pii=False,   # LGPD — não enviar dados de usuário
    )
```

### 5.5 Centralizar logs em produção (Loki)

Adicionar ao `docker-compose.yml` para produção:

```yaml
  loki:
    image: grafana/loki:2.9.0
    ports: ["3100:3100"]
    command: -config.file=/etc/loki/local-config.yaml

  promtail:
    image: grafana/promtail:2.9.0
    volumes:
      - /var/log:/var/log
      - ./promtail/config.yml:/etc/promtail/config.yml
    command: -config.file=/etc/promtail/config.yml
```

Configurar Grafana para usar Loki como datasource — logs e métricas no mesmo dashboard.

### Critério de aceite da Sprint 5–6

- [ ] `http://localhost:9090` mostra métricas sendo coletadas
- [ ] `http://localhost:3000` mostra dashboard com dados reais
- [ ] Alerta `APIDown` dispara quando o serviço é derrubado manualmente
- [ ] Sentry captura exceções não tratadas com environment correto

---

## 6. Sprint 7–8 — Infraestrutura de Produção

> **Meta:** Deploy em nuvem com TLS, secrets gerenciados, backups automáticos.

### 6.1 Secrets Management

**Opção recomendada para o MVP em nuvem:** Variáveis de ambiente injetadas pelo servidor (Railway, Render, ECS, etc.) — sem `.env` em nenhum servidor.

**Para time maior / escala:** HashiCorp Vault ou AWS Secrets Manager:

```bash
# AWS — armazenar secret
aws secretsmanager create-secret \
  --name "concierge/production" \
  --secret-string '{
    "ANTHROPIC_API_KEY": "sk-ant-...",
    "JWT_SECRET_KEY": "...",
    "ENCRYPTION_KEY": "..."
  }'

# Recuperar no startup da aplicação
aws secretsmanager get-secret-value \
  --secret-id "concierge/production" \
  --query SecretString \
  --output text | jq -r 'to_entries[] | "\(.key)=\(.value)"' >> /tmp/runtime.env
```

### 6.2 Resource limits no Docker Compose

**Arquivo:** `infrastructure/docker/docker-compose.yml`

Sem limits, containers podem derrubar o servidor inteiro:

```yaml
  app-f1:
    deploy:
      resources:
        limits:
          cpus: "1.5"
          memory: 1G
        reservations:
          cpus: "0.5"
          memory: 512M

  celery-worker:
    deploy:
      resources:
        limits:
          cpus: "2.0"
          memory: 2G
```

### 6.3 Reverse proxy com TLS (Nginx)

Criar `infrastructure/nginx/nginx.conf`:

```nginx
server {
    listen 80;
    server_name seu-dominio.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name seu-dominio.com;

    ssl_certificate /etc/letsencrypt/live/seu-dominio.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/seu-dominio.com/privkey.pem;

    location / {
        proxy_pass http://app-f1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }
}
```

### 6.4 Backup automático do PostgreSQL

Criar `infrastructure/scripts/backup.sh`:

```bash
#!/bin/bash
set -euo pipefail

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="concierge_backup_${TIMESTAMP}.sql.gz"
S3_BUCKET="s3://seu-bucket/backups/postgres/"

# Dump + compressão
docker exec concierge-postgres pg_dump \
  -U concierge concierge_prod | gzip > "/tmp/${BACKUP_FILE}"

# Upload para S3
aws s3 cp "/tmp/${BACKUP_FILE}" "${S3_BUCKET}${BACKUP_FILE}"

# Limpar local
rm "/tmp/${BACKUP_FILE}"

# Retenção: manter apenas últimos 30 dias no S3
aws s3 ls "${S3_BUCKET}" | \
  awk '{print $4}' | \
  sort | head -n -30 | \
  xargs -I {} aws s3 rm "${S3_BUCKET}{}"

echo "Backup ${BACKUP_FILE} realizado com sucesso"
```

Agendar via cron no servidor:

```bash
# Backup diário às 3h
0 3 * * * /opt/concierge/infrastructure/scripts/backup.sh >> /var/log/backup.log 2>&1
```

### 6.5 Health check no CI pré-deploy

Adicionar ao `deploy.yml` step de smoke test pós-deploy:

```yaml
      - name: Smoke test pós-deploy
        run: |
          sleep 15  # aguardar container subir
          curl -f https://seu-dominio.com/health || exit 1
          curl -f https://seu-dominio.com/health/ready || exit 1
          python scripts/monitoring/health_check.py --json
```

### Critério de aceite da Sprint 7–8

- [ ] `https://seu-dominio.com` redireciona HTTP → HTTPS
- [ ] `curl https://seu-dominio.com/health` retorna 200
- [ ] Secrets não existem em nenhum arquivo versionado
- [ ] Backup diário rodando e verificável no S3
- [ ] Deploy em produção sem downtime (rolling update)

---

## 7. Sprint 9–10 — Resiliência e Escalabilidade

> **Meta:** Sistema se recupera automaticamente de falhas. Suporta carga de pico.

### 7.1 Dead Letter Queue para Celery

Tarefas que falham após todos os retries devem ir para uma fila de DLQ para análise, não desaparecer silenciosamente.

**Arquivo:** `feature_1_ia_personalizada/workers/celery_app.py`

```python
# Configurar DLQ via policy do broker
celery_app.conf.update(
    task_reject_on_worker_lost=True,
    task_acks_late=True,

    # Após N retries, mover para dead_letter queue
    task_queues=(
        Queue("monitoramento", routing_key="monitoramento"),
        Queue("notificacoes", routing_key="notificacoes"),
        Queue("ia", routing_key="ia"),
        Queue("relacionamento", routing_key="relacionamento"),
        Queue("dead_letter", routing_key="dead_letter"),  # Nova
    ),
)

# Em cada task: configurar max_retries e on_failure
@celery_app.task(
    name="workers.enviar_notificacao_andamento",
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
)
def enviar_notificacao_andamento(id_processo: int, texto: str):
    try:
        ...
    except Exception as exc:
        if self.request.retries >= self.max_retries:
            celery_app.send_task(
                "workers.processar_dlq",
                args=[self.name, id_processo, str(exc)],
                queue="dead_letter",
            )
        raise
```

### 7.2 Circuit Breaker para APIs externas

Proteger contra cascata de falhas quando Jusbrasil ou DataJud ficam instáveis:

```python
# pip install pybreaker
from pybreaker import CircuitBreaker, CircuitBreakerError

# Configurar circuit breaker por serviço
_jusbrasil_breaker = CircuitBreaker(
    fail_max=5,          # Abre após 5 falhas consecutivas
    reset_timeout=60,    # Tenta novamente após 60s
)
_datajud_breaker = CircuitBreaker(fail_max=5, reset_timeout=60)

@_jusbrasil_breaker
def buscar_andamentos_jusbrasil(numero_processo: str, data_ref: str):
    return cliente_jusbrasil.buscar_novos_andamentos(numero_processo, data_ref)

# No monitor de processos, tratar CircuitBreakerError:
try:
    lista_andamentos = buscar_andamentos_jusbrasil(numero, data_ref)
except CircuitBreakerError:
    logger.warning("jusbrasil_circuit_open_usando_datajud", numero=numero)
    lista_andamentos = buscar_andamentos_datajud(numero, data_ref)
```

### 7.3 Cache de dados jurídicos

Dados do DataJud e Jusbrasil mudam raramente — cachear no Redis para reduzir chamadas externas:

```python
import json
import redis

_redis = redis.from_url(settings.REDIS_URL)
_CACHE_TTL_ANDAMENTOS = 3600  # 1 hora

def buscar_andamentos_com_cache(numero_processo: str) -> list:
    cache_key = f"andamentos:{numero_processo}"

    cached = _redis.get(cache_key)
    if cached:
        return json.loads(cached)

    andamentos = buscar_andamentos_jusbrasil(numero_processo, None)
    _redis.setex(cache_key, _CACHE_TTL_ANDAMENTOS, json.dumps(andamentos))
    return andamentos
```

### 7.4 Load testing

Antes de ir a produção, validar carga:

```bash
# pip install locust
locust -f tests/load/locustfile.py \
  --host=https://seu-dominio.com \
  --users=50 \
  --spawn-rate=5 \
  --run-time=5m
```

**Criar** `tests/load/locustfile.py`:

```python
from locust import HttpUser, task, between

class ConciergeUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        resp = self.client.post("/auth/login", json={
            "email": "test@test.com",
            "password": "test123"
        })
        self.token = resp.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    @task(5)
    def health_check(self):
        self.client.get("/health")

    @task(3)
    def historico_chat(self):
        self.client.get("/chat/history/1", headers=self.headers)

    @task(1)
    def health_detailed(self):
        self.client.get("/health/detailed")
```

**Metas de performance:**
- p95 < 500ms para `/chat/history`
- p95 < 2s para processamento de webhook
- 0% de erro com 50 usuários simultâneos

### Critério de aceite da Sprint 9–10

- [ ] Tarefa que falha 3x vai para fila `dead_letter` (visível no Flower)
- [ ] Circuit breaker abre quando Jusbrasil fica indisponível (mock)
- [ ] Load test de 50 usuários passa sem erros e p95 < 500ms
- [ ] Cache Redis reduz chamadas ao DataJud/Jusbrasil em ≥ 60%

---

## 8. Checklist Final de Deploy

Verificar cada item antes de declarar produção:

### Código

- [x] Zero `NotImplementedError` nos workers e serviço de mensagens ✅ (restam imports Fase 3 comentados em `monitor_processos.py`)
- [ ] Zero imports comentados com "implementar depois" → `monitor_processos.py` linhas 14–18 (aguarda Fase 3)
- [ ] `pytest` passa com cobertura ≥ 70%
- [ ] `ruff check .` e `black --check .` passam sem erros
- [ ] `mypy feature_1_ia_personalizada shared` sem erros críticos

### Segurança

- [ ] `.env` não existe em nenhum commit do repositório
- [ ] CORS restrito ao domínio de produção
- [ ] Webhook WhatsApp valida assinatura da Evolution API
- [ ] Error handler global retorna mensagem genérica (sem stack trace para cliente)
- [ ] Dados sensíveis (CPF, tokens) não aparecem nos logs
- [ ] `JWT_SECRET_KEY` tem ≥ 32 caracteres aleatórios
- [ ] `ENCRYPTION_KEY` é uma chave Fernet válida

### Infraestrutura

- [ ] HTTPS ativo com certificado válido
- [ ] HTTP redireciona para HTTPS
- [ ] Resource limits definidos em todos os containers
- [ ] Backup automático configurado e testado (fazer restore de teste)
- [ ] Deploy sem downtime validado (rolling update)

### Observabilidade

- [ ] Prometheus coletando métricas a cada 15s
- [ ] Grafana com dashboard ativo
- [ ] Ao menos 3 alertas configurados (APIDown, TaxaErroAlta, WorkerFora)
- [ ] Sentry com DSN real capturando erros
- [ ] Logs centralizados com Loki (ou equivalente)
- [ ] Script `python scripts/monitoring/health_check.py` retorna exit 0

### Funcional

- [ ] Smoke test pós-deploy passa (login → enviar mensagem → receber resposta)
- [ ] Monitor de processos busca dados reais do banco e processa
- [ ] Celery Beat executa ao menos uma tarefa por ciclo sem erro
- [ ] Webhook WhatsApp processa mensagem de texto de ponta a ponta
- [ ] Health check `/health/detailed` retorna `status: ok` (todos os 6 serviços)

### Processo

- [ ] Runbook de incidentes documentado (o que fazer quando a IA cai, quando o Redis cai, etc.)
- [ ] Processo de rotação de chaves documentado
- [ ] Contato de oncall definido
- [ ] Procedimento de rollback documentado e testado

---

## Dependências entre sprints

```
Sprint 1 (Lógica)
    │
    ▼
Sprint 2 (Segurança)
    │
    ▼
Sprint 3–4 (Testes + CI/CD) ◄── Depende de S1 (workers funcionais para testar)
    │
    ▼
Sprint 5–6 (Observabilidade) ◄── Paralelo com S3–4 se tiver 2 devs
    │
    ▼
Sprint 7–8 (Infra Prod)
    │
    ▼
Sprint 9–10 (Resiliência)
    │
    ▼
  PRODUÇÃO ✅
```

> **Dica:** Sprints 3–4 e 5–6 podem correr em paralelo com 2 engenheiros.
> Sprint 7–8 depende de S3–4 (precisa de CI/CD para fazer deploy automático).

---

> Última atualização: Março 2026
> Sprint 1: 2.1 ✅ · 2.2 ⏳ · 2.3 ✅ · 2.4 ✅ · 2.5 ✅ — próximo: Sprint 2 (Segurança)
