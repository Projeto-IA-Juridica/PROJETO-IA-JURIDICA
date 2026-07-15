# 03 — Arquitetura e Stack

## Fluxo de uma mensagem (produto)

```
Cliente no WhatsApp
   │ (webhook HMAC)
Evolution API (self-hosted)
   │
FastAPI  →  /webhook/whatsapp  →  fila Celery
   │
Orquestrador LangGraph (nós desacoplados):
   classificar_intencao → buscar_dados → gerar_resposta
       → confidence_router → verificar_resposta (fact-check) → enviar_resposta
   │
   ├── Claude Sonnet (resposta padrão)
   ├── Claude Opus (escalação premium / Hub)
   ├── Claude Haiku (DNA, títulos, tarefas baratas)
   ├── Jusbrasil / DataJud (dados do processo, cache Redis 1h)
   ├── pgvector (RAG — base do escritório)
   └── PostgreSQL (asyncpg)
```

## Multi-tenancy

Isolamento por `escritorio_id` em todas as tabelas (row-level, sem schema
separado). Um `TenantMixin` injeta o campo. Nenhuma query cruza escritórios;
o RAG é filtrado por `escritorio_id`; um escritório nunca vê dado de outro.

## Stack tecnológica

| Camada | Tecnologia |
|---|---|
| API | FastAPI 0.109 + Uvicorn |
| LLM | Claude Opus `claude-opus-4-6` (Hub/escalação) · Sonnet `claude-sonnet-5` (orquestrador) · Haiku 4.5 (DNA/títulos) |
| Orquestração de IA | LangGraph 0.2 + LangChain 0.2 |
| Embeddings (RAG) | Voyage AI `voyage-law-2` (1024D, jurídico) — fallback OpenAI `text-embedding-3-small` (dimensions=1024) |
| Transcrição de áudio | OpenAI Whisper |
| Banco | PostgreSQL 13 + asyncpg 0.29 (prepared statements desativados — compatível com PgBouncer/Railway) |
| Vetores | pgvector — dim 1024, índice HNSW |
| Cache/filas | Redis 5 · Celery 5.3 + RedBeat scheduler |
| Billing | Stripe (Checkout + Portal + webhooks HMAC) |
| Agenda | Google Calendar API (OAuth2 por escritório, REST via httpx) + SSE (Redis pub/sub) |
| WhatsApp | Evolution API (self-hosted, não-oficial) |
| Dados judiciais | Jusbrasil (primário) + DataJud CNJ (backup gratuito) |
| Enriquecimento B2B | ReceitaWS (CNPJ) + Explorium MCP + LinkedIn (Partner Program pendente) |
| Segurança | JWT (python-jose) + bcrypt + Fernet AES-256 |
| Observabilidade | Prometheus + Grafana + structlog (JSON) + Sentry (`send_default_pii=False`) |
| CI/CD | GitHub Actions |
| Deploy | Railway |
| Frontend | React 19 + TypeScript + TailwindCSS v4 + TanStack Query v5 + Vite |
| Qualidade | Ruff + Black + mypy + pytest + mutmut |

> **Nota sobre modelos:** o código referencia majoritariamente
> `claude-sonnet-5`, `claude-opus-4-6` e `claude-haiku-4-5-20251001`. Há
> referências residuais a `claude-sonnet-4-*` em pontos antigos/testes — a
> direção é padronizar nos três primeiros.

## Estrutura de pastas (topo)

```
shared/                       # Core compartilhado (models, schemas, security, config, utils)
feature_1_ia_personalizada/   # O PRODUTO
  ├── api/routes/             # 19 routers
  ├── api/middleware/         # auth JWT, CSRF, rate limit, logging
  ├── services/               # ai, agendamento, billing, crm, rag, legal_data, ...
  └── workers/                # 11 tasks Celery
feature_vendas/               # A MÁQUINA DE VENDAS (isolada por flag)
admin/                        # Admin Panel (React) — 9 páginas
frontend/hub-react/           # Hub do Advogado (React) — 16 páginas
frontend/{login,cadastro-onboarding,ajuda-contato}/  # frontends vanilla
alembic/versions/             # 31 migrations
infrastructure/docker/        # Dockerfile + docker-compose
monitoring/                   # Prometheus + Grafana + Loki
docs/base_conhecimento/       # ESTA base de conhecimento
```

## Deploy

Railway hospeda: a API FastAPI, o worker Celery, o beat (scheduler), o Postgres
e o Redis. A Evolution API é self-hosted (pode ser o mesmo ou outro serviço). O
fix de PgBouncer (desativar prepared statements no asyncpg) é o que permite rodar
com pooler no Railway.

**A máquina de vendas não exige serviços novos no Railway:** ela pega carona na
mesma API, worker, beat, Postgres e Redis. Só precisa de env vars `VENDAS_*` e
instâncias novas na Evolution (chips diferentes). Ver
[09_maquina_de_vendas.md](09_maquina_de_vendas.md).

## Como rodar local (resumo)

```
make setup          # venv + deps + .env
docker compose -f infrastructure/docker/docker-compose.yml up -d
make migrate        # alembic upgrade head
make seed && make create-admin
make dev            # API :8000
make worker         # Celery worker
make beat           # Celery Beat (crons)
```
Frontends: `cd admin && npm run dev` (:5173) · `cd frontend/hub-react && npm run dev` (:5174).
