# Concierge Jurídico Digital

> Plataforma B2B SaaS de IA conversacional para escritórios de advocacia — monitoramento de processos via WhatsApp, tradução de linguagem jurídica e comunicação proativa com clientes.

---

## Visão Geral

O **Concierge Jurídico Digital** é um assistente inteligente que atua como camada ativa de relacionamento entre escritórios de advocacia e seus clientes. Ao contrário de soluções que apenas enviam notificações automáticas com textos técnicos, o sistema:

- Compreende perguntas em linguagem natural (texto e áudio via Whisper)
- Consulta processos em tempo real via Jusbrasil + DataJud CNJ
- Responde em segundos com uma persona humanizada (nome e tom definidos pelo escritório)
- Mantém comunicação proativa mesmo sem movimentação processual
- Nunca dá pareceres jurídicos — escala para o advogado quando necessário

**Público-alvo:** Escritórios de advocacia brasileiros (B2B SaaS).

---

## Status Geral do Projeto — Março/2026

```
MVP (Feature 1 + Infra + Sub-features):  ████████████████████  100%  ← pronto para beta
Features 2–6 (backlog):                  ░░░░░░░░░░░░░░░░░░░░    0%  ← não iniciadas

TOTAL DO PROJETO:  ~30% do roadmap completo
```

### Tabela de Features

| # | Feature | Status | Observações |
|---|---------|--------|-------------|
| **F1** | IA Personalizada (MVP) | **✅ 100%** | Em produção (Railway) |
| F1.1 | RAG — documentos do escritório | **✅ 100%** | pgvector + HNSW, dim 1024 |
| F1.2 | Score de Risco Processual | **✅ 100%** | 5 componentes, só para advogados |
| F1.3 | Resumo Inteligente com contexto | **✅ 100%** | Tracking de fase processual |
| F1.4 | Onboarding Wizard | **✅ 100%** | 6 etapas guiadas |
| F1.5 | Analytics & Dashboard | **✅ 100%** | NPS, custo/interação, exportação |
| F1.6 | Escalação para Advogado | **✅ ~95%** | Funcional; ver nota 1 |
| F1.7 | CRM Inteligente | **✅ 100%** | Score IA via Claude |
| **F2** | Controladoria (Projuris) | **❌ 0%** | Não iniciada |
| **F3** | Conexões (Chat interno) | **❌ 0%** | Não iniciada |
| **F4** | ML de Prazos | **❌ 0%** | Não iniciada |
| **F5** | App Mobile (B2C) | **❌ 0%** | Não iniciada |
| **F6** | Integração nativa com CRMs | **❌ 0%** | Não iniciada |
| **Infra** | Docker, CI/CD, Monitoring | **✅ 100%** | GitHub Actions + Railway |

---

## O Que Está Feito (Feature 1 — MVP)

### IA Conversacional
- **Orquestrador LangGraph** com 6 nós: classificação de intenção → busca de dados → geração de resposta → fact-check → envio
- **Intenções detectadas:** status do processo, saudação, reclamação, dúvidas, perspectivas, outros
- **Anti-alucinação:** fact-checker valida respostas do Claude contra dados reais do banco antes de enviar
- **Memória de conversa** por cliente armazenada no Redis
- **Personas configuráveis:** cada escritório define nome, tom e especialidades da IA

### WhatsApp
- Integração com **Evolution API** (self-hosted)
- Recebe texto, áudio (transcrição via Whisper), imagem e documentos
- Validação de assinatura HMAC no webhook
- Templates prontos: boas-vindas, NPS, datas comemorativas

### Monitoramento de Processos
- Consulta **Jusbrasil** (primário) + **DataJud CNJ** (backup gratuito)
- Worker Celery a cada 6 horas por processo ativo
- Cache Redis (1h TTL) para evitar requisições duplicadas
- Tracking de fase processual: conhecimento → instrução → saneamento → julgamento → recurso → execução → encerrado

### RAG (Retrieval-Augmented Generation)
- Upload de PDFs (petições, jurisprudências, teses)
- Pipeline: extração PyMuPDF → chunks 512 tokens (50 overlap) → embeddings 1024-dim → pgvector
- Busca semântica com MMR re-ranking (sem custo extra de embeddings)
- Injetado no system prompt de cada resposta

### Score de Risco Processual
- Pontuação 0–100 baseada em: idade do processo, perfil do juiz, tipo de ação, prazos pendentes, histórico do escritório
- **Nunca exibido para clientes** (compliance OAB Provimento 205/2021)
- Atualizado pelo worker de monitoramento a cada 6 horas

### CRM Inteligente
- Score de relacionamento por cliente (frequência de interação, NPS, escalações, dias sem contato)
- Análise narrativa gerada pelo Claude com insights de satisfação
- Debounce: máximo 1 análise por hora por cliente

### Analytics
- NPS com trends de 30/90 dias
- Taxa de resposta autônoma (sem escalação)
- Custo por interação (baseado em tokens)
- Exportação CSV/Excel

### Escalação
- Detecta automaticamente pedidos fora de escopo (parecer, estratégia)
- Notifica o advogado responsável via WhatsApp
- Registra tempo de resposta e rastreia resolução

### Onboarding
6 etapas guiadas para novos escritórios: dados da firma → conexão WhatsApp → importação de clientes → configuração de persona → disclaimers OAB → ativação.

### Importação de Clientes
- Upload CSV ou sincronização com **Google Sheets**
- Validação de CPF, CNPJ, formato de telefone

### Segurança & Compliance
- **AES-256** (Fernet) para CPF, dados sensíveis em repouso
- **TLS 1.3** em trânsito
- **JWT** com 60 min de expiração
- **LGPD:** logs de acesso rastreáveis, mascaramento de dados, isolamento por `escritorio_id`
- **OAB:** disclaimers obrigatórios na primeira interação, sem previsão de resultado, sem pareceres

---

## O Que Ainda Falta

### Pendências Dentro do MVP (Feature 1)

| Item | Descrição | Impacto |
|------|-----------|---------|
| **Agendamento real** | `whatsapp.py:429` tem `# TODO`: integração com Celery Beat ou tabela de agendamentos para marcar consultas | Médio — cliente não consegue auto-agendar |
| **Direitos LGPD** | Endpoints de exportação e exclusão de dados do cliente (portabilidade + esquecimento) | Alto — exigência legal |
| **Load testing** | Scripts existem em `tests/load/` mas não integrados ao CI | Baixo — qualidade |
| **Terraform / K8s** | `infrastructure/terraform/` e `infrastructure/kubernetes/` declarados mas não criados | Baixo — só Railway por ora |
| **Documentação de API** | Pasta `docs/api/` vazia — sem Postman collection nem OpenAPI exportado | Baixo — qualidade |
| **Diagramas de arquitetura** | `docs/architecture/` vazia | Baixo — documentação |

### Features do Roadmap (não iniciadas)

#### Feature 2 — Controladoria (Projuris)
IA avisa advogados sobre deveres e prazos do dia via WhatsApp, integrado ao Projuris.
- `projuris_client.py` — cliente OAuth2 Projuris
- `dever_manager.py` — parser de deveres
- Workers: cron às 6h, 12h, 18h
- **Bloqueio:** acesso à API Projuris (contrato necessário)

#### Feature 3 — Conexões (Chat Interno)
Chat interno entre funcionários de escritórios e empresas clientes (estilo LinkedIn jurídico).
- Servidor WebSocket
- ACL com Casbin
- Distribuição automática de tarefas entre advogados

#### Feature 4 — ML de Prazos
Predição de prazos processuais com Random Forest / XGBoost.
- Feature engineering a partir dos dados de processo
- MLflow para registro de modelos
- Re-treino semanal automático
- **Pré-requisito:** volume mínimo de dados históricos (~1.000 processos concluídos)

#### Feature 5 — App Mobile B2C
App React Native para o cliente final monitorar seus próprios processos (concorrente do JusBrasil).
- Planos pagos: R$ 29,90 (básico) / R$ 79,90 (premium)
- Integração Stripe para assinaturas
- Acesso a documentos via URLs pré-assinadas S3

#### Feature 6 — Integração Nativa com CRMs
Adapters para Projuris, Astrea e SAJ ADV.
- Sincronização bidirecional de processos
- Webhooks por evento processual

---

## Problemas Conhecidos

| # | Problema | Status |
|---|----------|--------|
| 1 | Migration `004` com `down_revision` errado | ✅ **Corrigido** — atualizado para `e4bcb5d405fa` |
| 2 | Dois arquivos `008_*` com mesma dependência | ⚠️ **Aceitável** — Alembic trata como branches paralelas; não interferem |
| 3 | `ScoreRiscoCalculator` em `vitoria_preditor.py` (arquivo legado) | ℹ️ **Dívida técnica** — funcional, refatoração opcional |
| 4 | RAG usa `vector(1024)` e HNSW (spec pedia 1536 + IVFFlat) | ℹ️ **Intencional** — HNSW tem recall melhor com inserts incrementais |

---

## Arquitetura

```
┌─────────────────────────────────────────────────────┐
│                   WhatsApp (cliente)                │
└──────────────────────────┬──────────────────────────┘
                           │ webhook
                    Evolution API
                           │
┌──────────────────────────▼──────────────────────────┐
│              FastAPI (feature_1_ia_personalizada)    │
│  ┌─────────────────────────────────────────────────┐ │
│  │         LangGraph Orchestrator (6 nós)          │ │
│  │  classify → fetch_data → generate → check → send│ │
│  └───────┬──────────────┬──────────────────────────┘ │
│          │              │                             │
│    Claude API      Jusbrasil/DataJud                  │
│    (Anthropic)     (Redis cache 1h)                   │
│          │              │                             │
│    pgvector RAG    PostgreSQL (asyncpg)                │
└─────────────────────────────────────────────────────┘
                           │
              Celery Workers (Redis broker)
              ├── monitor_processos (cada 6h)
              ├── send_notifications
              ├── crm_worker
              └── ingest_documentos
```

**Multi-tenancy:** isolamento por `escritorio_id` em todas as tabelas (row-level, sem schema separado).

---

## Stack Tecnológica

| Camada | Tecnologia |
|--------|-----------|
| API | FastAPI 0.109 + Uvicorn |
| IA / LLM | Claude (Anthropic) + LangGraph + LangChain |
| Transcrição de áudio | OpenAI Whisper |
| Banco de dados | PostgreSQL 13 + asyncpg |
| Vetores (RAG) | pgvector 0.3 (dim 1024, HNSW) |
| Cache | Redis 5 |
| Filas | Celery 5.3 + Redis broker |
| Monitoramento de processos | Jusbrasil API + DataJud CNJ |
| WhatsApp | Evolution API (self-hosted) |
| Google Sheets | google-api-python-client |
| Segurança | JWT (python-jose) + bcrypt + Fernet AES-256 |
| Métricas | Prometheus + Grafana Cloud |
| Logs | structlog (JSON) + Sentry |
| CI/CD | GitHub Actions |
| Deploy | Railway |
| Testes | pytest + pytest-asyncio + factory-boy |
| Lint/Format | Ruff + Black + mypy |

---

## Estrutura de Pastas

```
PROJETO-IA-JURIDICA-13/
│
├── shared/                          # Core compartilhado
│   ├── models/                      # SQLAlchemy ORM
│   │   ├── base.py                  ✅ TenantMixin, TimestampMixin
│   │   ├── escritorio.py            ✅ Tenant raiz (escritório)
│   │   ├── cliente.py               ✅ Cliente final
│   │   ├── processo.py              ✅ Processo judicial (com score, fase)
│   │   ├── usuario.py               ✅ Advogados/assistentes
│   │   ├── interacao.py             ✅ Log de conversas IA-cliente
│   │   └── documento_rag.py         ✅ Documentos vetorizados
│   ├── schemas/                     ✅ Pydantic v2 (request/response)
│   ├── database/                    ✅ AsyncEngine + sessionmaker
│   ├── security/                    ✅ JWT + AES-256
│   ├── utils/                       ✅ LGPD, formatadores, validadores
│   └── config/                      ✅ Pydantic Settings + constantes
│
├── feature_1_ia_personalizada/      # MVP (100% completo)
│   ├── api/
│   │   ├── app.py                   ✅ FastAPI app + lifespan
│   │   ├── routes/
│   │   │   ├── auth.py              ✅ Login + registro JWT
│   │   │   ├── webhook_whatsapp.py  ✅ Receiver Evolution API
│   │   │   ├── processos.py         ✅ CRUD processos
│   │   │   ├── chat.py              ✅ Histórico + NPS + analytics
│   │   │   ├── rag.py               ✅ Upload/busca de documentos
│   │   │   ├── crm.py               ✅ Score CRM por cliente
│   │   │   ├── onboarding.py        ✅ Wizard 6 etapas
│   │   │   ├── admin_import.py      ✅ CSV/Google Sheets
│   │   │   ├── health.py            ✅ /health, /health/ready
│   │   │   └── metrics.py           ✅ /metrics (Prometheus)
│   │   └── middleware/              ✅ Auth JWT, rate limit, logging
│   │
│   ├── services/
│   │   ├── ai/
│   │   │   ├── orchestrator.py      ✅ LangGraph (1419 linhas)
│   │   │   ├── claude_client.py     ✅ Wrapper Claude com retries
│   │   │   ├── prompts.py           ✅ System prompts tipados
│   │   │   ├── memory.py            ✅ Memória Redis por cliente
│   │   │   ├── fact_checker.py      ✅ Anti-alucinação
│   │   │   ├── juridical_translator.py ✅ Tradução jurídico→leigo
│   │   │   └── processo_state.py    ✅ Tracking de fase processual
│   │   ├── messaging/               ✅ Evolution API + templates
│   │   ├── legal_data/              ✅ Jusbrasil + DataJud + cache
│   │   ├── rag/                     ✅ Ingestão + embeddings + retriever
│   │   ├── analytics/               ✅ NPS + métricas + exportação
│   │   ├── crm/                     ✅ Score + análise Claude
│   │   ├── escalacao/               ✅ Escalação para advogados
│   │   └── integrations/            ✅ Google Sheets
│   │
│   ├── workers/
│   │   ├── celery_app.py            ✅ 3 filas: monitoramento, notificacoes, ia
│   │   ├── monitor_processos.py     ✅ Polling Jusbrasil (cada 6h)
│   │   ├── send_notifications.py    ✅ Processamento de mensagens
│   │   ├── crm_worker.py            ✅ Análise CRM (debounce 1h)
│   │   ├── ingest_documentos.py     ✅ Pipeline RAG
│   │   ├── mensagens_relacionamento.py ✅ Msgs comemorativas
│   │   └── dead_letter.py           ✅ Fila morta (DLQ)
│   │
│   ├── data/
│   │   ├── knowledge_base/          ✅ disclaimers.json, datas_comemorativas.json
│   │   └── termos_juridicos/        ✅ traducoes.json (~50 termos)
│   │
│   └── tests/
│       ├── unit/                    ✅ 25+ arquivos
│       └── integration/             ✅ 6 fluxos end-to-end
│
├── alembic/versions/                ✅ 11 migrations (incluindo pgvector + índices)
│
├── frontend/                        # Landing page de marketing
│   ├── index.html                   ✅ Página principal (semântica)
│   ├── style.css                    ✅ Dark navy/gold, responsivo
│   └── script.js                    ✅ Scroll reveal + navegação
│
├── infrastructure/docker/           ✅ Dockerfile + docker-compose (dev + prod)
│
├── .github/workflows/
│   ├── ci.yml                       ✅ Lint + tipos + testes + Docker build
│   ├── deploy.yml                   ✅ Deploy Railway na main
│   └── backup.yml                   ✅ Backup agendado PostgreSQL
│
├── docs/
│   ├── guides/                      ✅ development.md, production-readiness.md, secrets.md
│   ├── api/                         ❌ Vazia (sem Postman/OpenAPI exportado)
│   └── architecture/                ❌ Vazia (sem diagramas)
│
├── scripts/setup/                   ✅ init_db.py, seed_data.py, create_admin.py
├── Makefile                         ✅ 40+ targets (dev, test, lint, deploy)
├── pyproject.toml                   ✅ Ruff + Black + mypy + pytest config
├── requirements-base.txt            ✅
├── requirements-f1.txt              ✅
├── requirements-dev.txt             ✅
├── railway.json                     ✅ Deploy Railway (API)
└── railway.worker.json              ✅ Deploy Railway (Celery worker)
```

---

## Setup Local

### Pré-requisitos
- Python 3.12+
- Docker + Docker Compose
- ffmpeg (para processamento de áudio)

### Passo a passo

```bash
# 1. Clonar e configurar ambiente
git clone <repo>
cd PROJETO-IA-JURIDICA-13
make setup              # cria .venv, instala deps, copia .env.example → .env

# 2. Configurar variáveis de ambiente
# Editar .env com:
# ANTHROPIC_API_KEY, OPENAI_API_KEY, JUSBRASIL_API_KEY
# EVOLUTION_API_URL, EVOLUTION_API_KEY
# DATABASE_URL, REDIS_URL
# GOOGLE_SHEETS_CREDENTIALS (opcional)

# 3. Subir infraestrutura
docker compose -f infrastructure/docker/docker-compose.yml up -d

# 4. Banco de dados
make migrate            # alembic upgrade head
make seed               # dados de desenvolvimento
make create-admin       # criar primeiro usuário admin

# 5. Rodar
make dev                # FastAPI em :8000
make worker             # Celery worker (outro terminal)
make beat               # Celery beat — agendamentos (opcional)
make flower             # Monitor Celery em :5555 (opcional)

# 6. Qualidade
make test               # pytest (cobertura mínima 70%)
make lint               # Ruff + Black check
make type-check         # mypy
```

---

## Endpoints Principais

| Método | Rota | Descrição | Auth |
|--------|------|-----------|------|
| `POST` | `/webhook/whatsapp` | Receiver Evolution API | API Key |
| `POST` | `/auth/login` | Gera token JWT | Email/senha |
| `POST` | `/auth/register` | Cadastro de escritório | — |
| `GET` | `/processos` | Lista processos do escritório | JWT |
| `GET` | `/processos/{id}` | Detalhes de um processo | JWT |
| `POST` | `/rag/upload` | Upload de documento (PDF) | JWT |
| `POST` | `/crm/analise` | Dispara análise CRM de cliente | JWT |
| `GET` | `/crm/cliente/{id}` | Score CRM de um cliente | JWT |
| `POST` | `/onboarding/etapa` | Avança etapa do wizard | JWT |
| `GET` | `/chat/historico` | Histórico de conversas | JWT |
| `GET` | `/health` | Health check (DB, Redis, Claude) | — |
| `GET` | `/metrics` | Métricas Prometheus | — |

---

## Compliance

### OAB (Provimento 205/2021)
- IA nunca dá pareceres jurídicos ("você deve fazer X")
- IA nunca prevê resultado de processos
- Disclaimer obrigatório na primeira interação de cada cliente
- Score de risco visível apenas para advogados, nunca para clientes
- Escalação automática para humano quando necessário

### LGPD
- Criptografia AES-256 em repouso (CPF, dados sensíveis)
- TLS 1.3 em trânsito
- Logs de acesso rastreáveis (quem acessou qual dado, quando)
- Mascaramento: CPF → `***.***.***-XX`, telefone → `(**)****-XXXX`
- Isolamento por `escritorio_id` (segregação de dados entre clientes)
- Retenção: dados de processos arquivados removidos após 5 anos (política definida)
- **Faltam:** endpoints de exportação e exclusão por solicitação do titular

---

## Variáveis de Ambiente

```bash
# .env.example (ver arquivo completo)

# IA
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...          # Whisper

# Banco
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/juridico
REDIS_URL=redis://localhost:6379

# WhatsApp
EVOLUTION_API_URL=http://localhost:8080
EVOLUTION_API_KEY=...
EVOLUTION_WEBHOOK_SECRET=...   # HMAC validation

# Judicial
JUSBRASIL_API_KEY=...
DATAJUD_API_KEY=...            # Gratuito — CNJ

# Google Sheets (opcional)
GOOGLE_SHEETS_CREDENTIALS=...

# Segurança
SECRET_KEY=...                 # JWT signing
ENCRYPTION_KEY=...             # Fernet AES-256

# Observabilidade (opcional em dev)
SENTRY_DSN=...
GRAFANA_CLOUD_API_KEY=...
```

---

## Próximos Passos Sugeridos

1. **Agendamento de consultas** — implementar o TODO em `whatsapp.py:429` com Celery Beat
2. **Endpoints LGPD** — exportação e exclusão de dados do titular (exigência legal)
3. **Documentação de API** — gerar Postman collection a partir do OpenAPI automático do FastAPI (`/docs`)
4. **Load testing** — integrar `tests/load/` ao pipeline CI
5. **Feature 2 (Controladoria)** — próxima de maior valor para escritórios com Projuris
6. **Feature 4 (ML de Prazos)** — requer dados históricos; iniciar coleta estruturada agora

---

## Testes

```bash
make test                      # todos os testes
make test-unit                 # apenas unitários
make test-integration          # apenas integração
make coverage                  # relatório HTML de cobertura
```

- Cobertura mínima: **70%** (enforçado no CI)
- 54 arquivos de teste (25 unitários + 6 integração + fixtures compartilhadas)
- Banco de testes: SQLite in-memory via `aiosqlite` (sem PostgreSQL necessário)

---

## Links

- **Roadmap detalhado:** [docs/ROADMAP_FEATURES.md](docs/ROADMAP_FEATURES.md)
- **Tasks e sub-features:** [TASKS.md](TASKS.md)
- **Guia de desenvolvimento:** [docs/guides/development.md](docs/guides/development.md)
- **Checklist de produção:** [docs/guides/production-readiness.md](docs/guides/production-readiness.md)
- **Gestão de secrets:** [docs/guides/secrets.md](docs/guides/secrets.md)
- **Documentação do banco:** [bancodedados_api.md](bancodedados_api.md)
