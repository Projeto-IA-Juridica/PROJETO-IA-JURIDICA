# Concierge Jurídico Digital

> Plataforma B2B SaaS de IA conversacional para escritórios de advocacia — monitoramento de processos, comunicação proativa com clientes, prospecção inteligente de leads e hub de análise jurídica para advogados.

![CI](https://github.com/gabrielferreiraabel/concierge-juridico/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.12+-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.109-green)
![Deploy](https://img.shields.io/badge/deploy-Railway-purple)
![Cobertura](https://img.shields.io/badge/cobertura-70%25%20mínimo-brightgreen)

---

## O Problema

Escritórios de advocacia perdem clientes por falta de comunicação — não por falta de competência. O cliente não sabe o que está acontecendo com seu processo, precisa ligar para obter uma atualização básica, e o advogado gasta horas por semana respondendo perguntas repetitivas no WhatsApp como _"tem novidade?"_ e _"o que significa esse termo?"_.

Ao mesmo tempo, captar novos clientes é artesanal: esperar indicação, pagar por anúncios genéricos ou garimpar manualmente no Jusbrasil sem critério.

---

## A Solução

O **Concierge Jurídico Digital** é um assistente de IA que o escritório implanta em seu WhatsApp em minutos. A partir daí:

- **Clientes recebem atualizações proativas** assim que há movimentação processual, em linguagem simples — sem precisar perguntar
- **Perguntas frequentes são respondidas em segundos** pela IA, com a persona e o tom do escritório
- **O advogado é acionado apenas quando necessário** — pareceres, estratégias, situações fora de escopo
- **Novos clientes são descobertos automaticamente** com base nas especialidades reais do escritório, cruzadas com o DataJud CNJ

O resultado: mais clientes atendidos, menos tempo operacional, relacionamento mais próximo e captação sistematizada.

---

## Pitch

> *"Imagine um assistente que conhece todos os seus processos, fala com seus clientes no WhatsApp 24h por dia no seu tom, nunca erra um prazo e ainda te indica quem está litigando na sua área de atuação e ainda não tem advogado. É isso que entregamos."*

**Para o advogado:** menos tempo respondendo WhatsApp, mais tempo faturando.
**Para o cliente:** transparência e proximidade que fideliza.
**Para o escritório:** crescimento sem contratar mais assistentes.

---

## Público-Alvo

| Segmento | Perfil | Dor Principal |
|----------|--------|---------------|
| **Escritórios boutique** (2–15 advogados) | Cível, trabalhista, família, previdenciário | Sem estrutura para atendimento proativo; todo cliente precisa ligar para saber novidades |
| **Escritórios em crescimento** (15–50 advogados) | Mais de uma área de atuação | Escalar atendimento sem contratar proporcionalmente |
| **Advogados autônomos** com carteira estabelecida | Qualquer área | Parecer de disponibilidade 24h sem custo fixo de funcionário |

**Fora do escopo atual:** escritórios enterprise com sistemas legados complexos (Projuris, SAJ) — endereçados nas Features 2 e 6 do roadmap.

---

## Como Geramos Valor

### Para o escritório

| Métrica | Impacto |
|---------|---------|
| **Redução de chamadas/WhatsApp manual** | IA responde ~70–80% das perguntas rotineiras sem escalação |
| **Tempo do advogado** | Estimativa de 3–5h/semana economizadas por advogado em atendimento repetitivo |
| **Fidelização de clientes** | CRM automático identifica clientes em risco de churn antes de perderem o contato |
| **Captação de leads qualificados** | Prospecção baseada em demanda jurídica comprovada (DataJud), não em cold lead |
| **Análise de petições** | Hub do Advogado analisa documentos jurídicos com Claude Opus em segundos |

### Para o cliente final

- Sabe o que está acontecendo com seu processo sem precisar ligar
- Recebe explicações em linguagem simples, não jurídica
- Tem um canal de atendimento disponível a qualquer hora

### Modelo de negócio (SaaS B2B)

- Cobrança mensal por escritório (por número de processos ativos ou por volume de interações)
- Planos diferenciados por funcionalidade (MVP, Prospecção, Hub)
- Receita recorrente e baixo churn estrutural (dados e personas ficam no sistema)

---

## Status do Projeto — Abril/2026

```
MVP (Feature 1 + Infra + Sub-features):  ████████████████████  100%  ← em produção
Hub do Advogado (Harvey AI):              ███████████████████░   95%  ← funcional
Feature 3 — Prospecção Inteligente:       ██████████████████░░   90%  ← LinkedIn pendente
Features 2, 4–6 (backlog):               ░░░░░░░░░░░░░░░░░░░░    0%  ← não iniciadas

TOTAL DO PROJETO:  ~50% do roadmap completo
```

### Tabela de Features

| # | Feature | Status | Observações |
|---|---------|--------|-------------|
| **F1** | IA Personalizada (MVP) | **✅ 100%** | Em produção (Railway) |
| F1.1 | RAG — documentos do escritório | **✅ 100%** | pgvector + HNSW, dim 1024 |
| F1.2 | Score de Risco Processual | **✅ 100%** | 5 componentes, exclusivo para advogados |
| F1.3 | Resumo Inteligente com contexto | **✅ 100%** | Tracking de fase processual |
| F1.4 | Onboarding Wizard | **✅ 100%** | 6 etapas guiadas |
| F1.5 | Analytics & Dashboard | **✅ 100%** | NPS, custo/interação, exportação |
| F1.6 | Escalação para Advogado | **✅ ~95%** | Funcional; ver Problemas Conhecidos |
| F1.7 | CRM Inteligente | **✅ 100%** | Score + análise narrativa via Claude |
| F1.8 | Agendamento de mensagens | **✅ 100%** | Dispatcher Celery Beat a cada 5 min |
| **Hub** | Hub do Advogado (Harvey AI) | **✅ ~95%** | Análise de petições + consultas com Claude Opus |
| **F2** | Controladoria (Projuris) | **❌ 0%** | Aguarda contrato Projuris |
| **F3** | Prospecção Inteligente | **✅ ~90%** | Motor completo; LinkedIn real pendente |
| F3.1 | DNA do Advogado | **✅ 100%** | Claude Haiku + cache Redis 6h |
| F3.2 | DataJud — busca de litigantes | **✅ 100%** | Deduplicação automática por tipo de ação |
| F3.3 | Receita Federal / CNPJ | **✅ 100%** | Enriquecimento B2B (porte, sócios, situação) |
| F3.4 | LinkedIn enrichment (B2B) | **⚠️ ~70%** | Estrutura pronta; Partner Program pendente |
| F3.5 | Matching & Score IA (B2B/B2C) | **✅ 100%** | Heurística + refinamento Claude; limiar 30 |
| F3.6 | Pipeline de leads | **✅ 100%** | CRUD + deduplicação por CNPJ/CNJ |
| F3.7 | Compliance LGPD/OAB (B2C) | **✅ 100%** | Sem CPF/telefone/email; aviso automático |
| **F4** | ML de Prazos | **❌ 0%** | Aguarda volume de dados históricos |
| **F5** | App Mobile (B2C) | **❌ 0%** | Não iniciada |
| **F6** | Integração nativa com CRMs | **❌ 0%** | Não iniciada |
| **Infra** | Docker, CI/CD, Monitoring | **✅ 100%** | GitHub Actions + Railway |

---

## Funcionalidades Implementadas

### IA Conversacional via WhatsApp

O coração do produto. Um orquestrador LangGraph executa um pipeline de 6 nós para cada mensagem recebida:

```
classificar intenção → buscar dados → gerar resposta → fact-check → enviar
```

- **6 intenções detectadas:** status do processo, saudação, reclamação, dúvida jurídica, perspectiva do caso, outros
- **Anti-alucinação:** o fact-checker valida cada resposta do Claude contra os dados reais do banco antes de enviar ao cliente — se houver divergência, a resposta é corrigida ou descartada
- **Memória de conversa** por cliente armazenada no Redis — a IA lembra o contexto da sessão
- **Personas configuráveis** — cada escritório define nome, tom e especialidades da IA
- **Tradutor jurídico** — termos técnicos são automaticamente convertidos para linguagem acessível

**Canais suportados:**
- Texto (WhatsApp via Evolution API)
- Áudio — transcrição via OpenAI Whisper antes do processamento
- Imagens e documentos — recebidos e catalogados

**Controle de envio:**
- Respeita janela comercial configurada por cliente (ex: só enviar entre 8h e 18h)
- Rate limit de 5 mensagens proativas por dia por cliente
- Mensagens bloqueadas são salvas na tabela `mensagens_agendadas` e despachadas automaticamente pelo `dispatcher_agendadas` a cada 5 minutos via Celery Beat

---

### Monitoramento de Processos

- Consulta Jusbrasil (primário) + DataJud CNJ (backup gratuito) a cada 6 horas por processo ativo
- Cache Redis 1h para evitar requisições duplicadas
- Tracking completo de fase processual: `conhecimento → instrução → saneamento → julgamento → recurso → execução → encerrado`
- Ao detectar movimentação, dispara notificação proativa para o cliente em linguagem simples

---

### RAG — Base de Conhecimento do Escritório

- Upload de PDFs (petições, jurisprudências, teses, modelos)
- Pipeline: extração PyMuPDF → chunks de 512 tokens (50 overlap) → embeddings 1024-dim → armazenamento pgvector
- Busca semântica com MMR re-ranking para diversidade de resultados
- O conteúdo relevante é injetado automaticamente no system prompt de cada resposta
- Isolado por `escritorio_id` — um escritório nunca acessa os documentos de outro

---

### Score de Risco Processual

Pontuação 0–100 por processo, calculada com 5 componentes:

| Componente | Peso |
|-----------|------|
| Idade do processo | 20% |
| Perfil histórico do juiz | 25% |
| Tipo de ação | 20% |
| Prazos pendentes | 20% |
| Histórico do escritório no tribunal | 15% |

- **Nunca exibido para clientes** — compliance OAB Provimento 205/2021
- Atualizado automaticamente a cada 6 horas pelo worker de monitoramento

---

### CRM Inteligente

- Score de relacionamento por cliente (0–100) calculado com: frequência de interação, NPS, número de escalações, dias desde último contato
- Classificação automática: `excelente / satisfeito / neutro / em_risco / critico`
- Análise narrativa gerada pelo Claude com diagnóstico de satisfação e ação sugerida
- Debounce: máximo 1 análise por hora por cliente para não gerar custo desnecessário
- Alerta quando cliente está em risco de churn

---

### Analytics & Dashboard

- NPS com tendências de 30 e 90 dias
- Taxa de resposta autônoma (percentual de conversas sem escalação)
- Custo por interação (calculado por tokens consumidos)
- Exportação CSV/Excel para relatórios internos

---

### Escalação para Advogado

- Detecta automaticamente requisições fora de escopo: pedidos de parecer, análise de estratégia, situações emocionalmente sensíveis
- Notifica o advogado responsável pelo processo via WhatsApp
- Registra timestamp de abertura, resposta e resolução
- Configurável por escritório: canal dedicado ou número compartilhado

---

### Onboarding Wizard

6 etapas guiadas para novos escritórios ficarem operacionais em menos de 30 minutos:

1. Dados do escritório (nome, OAB, especialidades)
2. Conexão WhatsApp via Evolution API
3. Importação de clientes (CSV ou Google Sheets)
4. Configuração de persona (nome da IA, tom, especialidades declaradas)
5. Aceite dos disclaimers OAB
6. Ativação e teste de envio

---

### Hub do Advogado — Harvey AI

Interface exclusiva para advogados, sem as restrições do canal de cliente. Powered by Claude Opus.

**Funcionalidades:**
- `POST /hub/analisar-peticao` — upload de PDF de petição (até 10 MB) + análise estruturada: pontos fortes, fracos, riscos processuais, sugestões de melhoria
- `POST /hub/consulta` — consulta jurídica livre em linguagem natural

**Classificação de intenção automática:**

| Intenção | O que faz |
|----------|-----------|
| `análise_petição` | Analisa documento jurídico linha a linha |
| `pesquisa_jurisprudência` | Busca jurisprudência relevante para o caso |
| `resumo_processo` | Gera resumo executivo do processo referenciado |
| `insight_cliente` | Análise do histórico de relacionamento com o cliente |
| `pergunta_jurídica` | Responde perguntas doutrinárias e procedimentais |

**Rastreabilidade:** cada sessão é salva em `sessoes_advogado` com modelo utilizado, tokens consumidos e custo estimado.

---

### Prospecção Inteligente (Feature 3)

Motor de captação de leads com demanda jurídica comprovada.

**DNA do Advogado**
Analisa o histórico de processos do escritório e extrai: especialidades predominantes, setores-alvo, tipo de lead ideal (B2B ou B2C). Persistido em `escritorio.dna_prospeccao` (JSONB) + cache Redis 6h. Se o escritório tiver menos de 5 processos, retorna `dados_insuficientes=True` sem forçar classificação.

**Descoberta via DataJud**
Em vez de buscar um CNPJ específico, o sistema busca no DataJud CNJ por `tipo_acao` — retornando quem já está litigando nessa área. Prioriza partes sem advogado (`sem_advogado=True`). Resolve índice automaticamente por área: trabalhista → TRT, cível → TJ, federal → TRF.

**Enriquecimento B2B**
- Receita Federal via ReceitaWS: razão social, situação cadastral, porte, sócios (sem CPF — LGPD)
- LinkedIn: contatos com cargo e URL de perfil (estrutura pronta, Partner Program pendente)
- Cache Redis 24h por CNPJ

**Enriquecimento B2C — LGPD by Design**
Apenas dados do processo público: nome, polo, tipo de ação, fase, tribunal. CPF, telefone, email e endereço são proibidos no nível do modelo — não existem os campos. `validar_compliance()` descarta automaticamente ações com dados sensíveis (internação compulsória, curatela, retificação de registro civil).

**Matching & Score IA**

| Critério B2B | Peso | Critério B2C | Peso |
|-------------|------|-------------|------|
| Especialidade match | +30 | Especialidade match | +35 |
| Setor CNAE | +20 | Polo compatível | +25 |
| Demanda ativa 3+ processos | +15 | Fase processual inicial | +20 |
| Contatos LinkedIn | +15 | Alta recorrência no escritório | +20 |
| Porte MÉDIA/GRANDE | +10 | — | — |
| Situação ATIVA | +10 | — | — |

Score ≥ 30 → Claude refina, gera motivo e sugere abordagem. Score < 30 → retorna sem chamar o modelo.

**Pipeline de Leads**
CRUD completo com deduplicação automática (mesmo CNPJ ou mesmo CNJ → atualiza em vez de duplicar), filtros por tipo/status/score mínimo e paginação. `aviso_lgpd` injetado automaticamente quando o pipeline contém leads B2C.

---

## Arquitetura

```
┌──────────────────────────────────────────────────────────┐
│                    WhatsApp (cliente)                    │
└───────────────────────────┬──────────────────────────────┘
                            │ webhook HMAC
                     Evolution API
                            │
┌───────────────────────────▼──────────────────────────────┐
│               FastAPI (feature_1_ia_personalizada)        │
│  ┌──────────────────────────────────────────────────┐    │
│  │        LangGraph Orchestrator (6 nós)            │    │
│  │   classify → fetch → generate → check → send    │    │
│  └───────────┬────────────────┬─────────────────────┘    │
│              │                │                           │
│        Claude API        Jusbrasil / DataJud              │
│        (Anthropic)       (Redis cache 1h)                 │
│              │                │                           │
│        pgvector RAG      PostgreSQL (asyncpg)             │
│                                                           │
│  ┌──────────────────────────────────────────────────┐    │
│  │  Hub do Advogado — Harvey AI                     │    │
│  │  /hub/* → Claude Opus → SessaoAdvogado           │    │
│  └──────────────────────────────────────────────────┘    │
│                                                           │
│  ┌──────────────────────────────────────────────────┐    │
│  │  Motor de Prospecção (Feature 3)                 │    │
│  │  DNA → DataJud → Receita/LinkedIn → Match → IA   │    │
│  └──────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────┘
                            │
               Celery Workers (Redis broker)
               ├── monitor_processos       (cron: cada 6h)
               ├── dispatcher_agendadas    (cron: cada 5min)
               ├── mensagens_relacionamento (cron: diário/semanal)
               ├── send_notifications      (on-demand)
               ├── crm_worker              (on-demand, debounce 1h)
               ├── hub_advogado            (on-demand)
               ├── ingest_documentos       (on-demand)
               └── dead_letter             (DLQ)
```

**Multi-tenancy:** isolamento por `escritorio_id` em todas as tabelas (row-level, sem schema separado).

---

## Stack Tecnológica

| Camada | Tecnologia |
|--------|-----------|
| API | FastAPI 0.109 + Uvicorn |
| IA / LLM | Claude Opus (Hub) + Claude 3.5 Sonnet (orquestrador) + Claude Haiku (DNA/matching) |
| Orquestração de IA | LangGraph + LangChain |
| Transcrição de áudio | OpenAI Whisper |
| Banco de dados | PostgreSQL 13 + asyncpg |
| Vetores (RAG) | pgvector 0.3 — dim 1024, índice HNSW |
| Cache | Redis 5 (TTL 1h–24h por contexto) |
| Filas | Celery 5.3 + Redis broker + RedBeat scheduler |
| Monitoramento de processos | Jusbrasil API + DataJud CNJ |
| WhatsApp | Evolution API (self-hosted) |
| Enriquecimento B2B | ReceitaWS (CNPJ) + LinkedIn API (Partner Program pendente) |
| Google Sheets | google-api-python-client |
| Segurança | JWT (python-jose) + bcrypt + Fernet AES-256 |
| Métricas | Prometheus + Grafana Cloud |
| Logs | structlog (JSON) + Sentry |
| CI/CD | GitHub Actions |
| Deploy | Railway |
| Testes | pytest + pytest-asyncio + factory-boy |
| Qualidade | Ruff + Black + mypy |

---

## Estrutura de Pastas

```
PROJETO-IA-JURIDICA-5/
│
├── shared/                          # Core compartilhado
│   ├── models/                      # SQLAlchemy ORM (10 models)
│   │   ├── base.py                  ✅ TenantMixin, TimestampMixin
│   │   ├── escritorio.py            ✅ Tenant raiz
│   │   ├── cliente.py               ✅ Cliente final
│   │   ├── processo.py              ✅ Processo judicial (score, fase)
│   │   ├── usuario.py               ✅ Advogados/assistentes
│   │   ├── interacao.py             ✅ Log de conversas IA-cliente
│   │   ├── documento_rag.py         ✅ Documentos vetorizados
│   │   ├── lead_prospeccao.py       ✅ Pipeline de prospecção (F3)
│   │   ├── sessao_advogado.py       ✅ Sessões do Hub do Advogado
│   │   └── mensagem_agendada.py     ✅ Fila de mensagens fora da janela comercial
│   ├── schemas/                     ✅ Pydantic v2 (request/response)
│   ├── database/                    ✅ AsyncEngine + sessionmaker
│   ├── security/                    ✅ JWT + AES-256
│   ├── utils/                       ✅ LGPD, formatadores, validadores
│   └── config/                      ✅ Pydantic Settings + constantes
│
├── feature_1_ia_personalizada/
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
│   │   │   ├── metrics.py           ✅ /metrics (Prometheus)
│   │   │   ├── prospeccao.py        ✅ /prospeccao/* (DNA, pipeline, leads)
│   │   │   └── hub_advogado.py      ✅ /hub/* (Harvey AI)
│   │   └── middleware/              ✅ Auth JWT, rate limit, logging
│   │
│   ├── services/
│   │   ├── ai/
│   │   │   ├── orchestrator.py      ✅ LangGraph (6 nós)
│   │   │   ├── claude_client.py     ✅ Wrapper Claude com retries
│   │   │   ├── escalation_client.py ✅ Claude Opus (Hub + escalação premium)
│   │   │   ├── fact_checker.py      ✅ Anti-alucinação
│   │   │   ├── memory.py            ✅ Memória Redis por cliente
│   │   │   ├── juridical_translator.py ✅ Tradução jurídico→leigo
│   │   │   ├── processo_state.py    ✅ Tracking de fase processual
│   │   │   └── prompts.py           ✅ System prompts tipados
│   │   ├── messaging/               ✅ Evolution API + templates + agendamento
│   │   ├── legal_data/              ✅ Jusbrasil + DataJud + cache
│   │   ├── rag/                     ✅ Ingestão + embeddings + retriever
│   │   ├── analytics/               ✅ NPS + métricas + exportação
│   │   ├── crm/                     ✅ Score + análise Claude
│   │   ├── escalacao/               ✅ Escalação para advogados
│   │   ├── integrations/            ✅ Google Sheets
│   │   └── prospeccao/
│   │       ├── dna_advogado.py      ✅ DNA do escritório
│   │       ├── datajud_prospeccao.py ✅ Busca litigantes por tipo de ação
│   │       ├── empresa_intelligence.py ✅ Enriquecimento B2B
│   │       ├── pessoa_intelligence.py  ✅ Enriquecimento B2C (LGPD)
│   │       ├── matching.py          ✅ Heurística + refinamento Claude
│   │       ├── receita_federal_client.py ✅ CNPJ e sócios
│   │       └── linkedin_client.py   ⚠️ Estrutura pronta; Partner Program pendente
│   │
│   ├── workers/
│   │   ├── celery_app.py            ✅ 6 filas + RedBeat scheduler
│   │   ├── monitor_processos.py     ✅ Polling Jusbrasil (cada 6h)
│   │   ├── send_notifications.py    ✅ Notificações on-demand
│   │   ├── dispatcher_agendadas.py  ✅ Despacha mensagens agendadas (cada 5min)
│   │   ├── crm_worker.py            ✅ Análise CRM (debounce 1h)
│   │   ├── hub_advogado.py          ✅ Processamento assíncrono do Hub
│   │   ├── ingest_documentos.py     ✅ Pipeline RAG
│   │   ├── mensagens_relacionamento.py ✅ Aniversários, datas comemorativas
│   │   └── dead_letter.py           ✅ Dead Letter Queue
│   │
│   └── tests/
│       ├── unit/                    ✅ 43 arquivos
│       └── integration/             ✅ 16 arquivos
│
├── alembic/versions/                ✅ 21 migrations
├── frontend/                        ✅ Landing page (HTML/CSS/JS)
├── infrastructure/docker/           ✅ Dockerfile + docker-compose (dev + prod)
├── .github/workflows/               ✅ CI + deploy + backup
├── docs/guides/                     ✅ development.md, production-readiness.md
├── scripts/setup/                   ✅ init_db.py, seed_data.py, create_admin.py
├── Makefile                         ✅ 40+ targets
└── pyproject.toml                   ✅ Ruff + Black + mypy + pytest
```

---

## Setup Local

**Pré-requisitos:** Python 3.12+, Docker + Docker Compose, ffmpeg

```bash
# 1. Clonar e configurar ambiente
git clone <repo>
cd PROJETO-IA-JURIDICA-5
make setup              # cria .venv, instala deps, copia .env.example → .env

# 2. Editar .env com as chaves necessárias (ver seção abaixo)

# 3. Subir infraestrutura
docker compose -f infrastructure/docker/docker-compose.yml up -d

# 4. Banco de dados
make migrate            # alembic upgrade head
make seed               # dados de desenvolvimento
make create-admin       # criar primeiro usuário admin

# 5. Rodar
make dev                # FastAPI em :8000
make worker             # Celery worker (outro terminal)
make beat               # Celery Beat — dispatcher + todos os crons
make flower             # Monitor Celery em :5555 (opcional)

# 6. Qualidade
make test               # pytest (cobertura mínima 70%)
make lint               # Ruff + Black check
make type-check         # mypy
```

---

## Endpoints

| Método | Rota | Descrição | Auth |
|--------|------|-----------|------|
| `POST` | `/webhook/whatsapp` | Receiver Evolution API | API Key |
| `POST` | `/auth/login` | Gera token JWT | Email/senha |
| `POST` | `/auth/register` | Cadastro de escritório | — |
| `GET` | `/processos` | Lista processos do escritório | JWT |
| `GET` | `/processos/{id}` | Detalhes + score de risco | JWT |
| `POST` | `/rag/upload` | Upload de documento PDF | JWT |
| `DELETE` | `/rag/{id}` | Remove documento do RAG | JWT |
| `POST` | `/crm/analise` | Dispara análise CRM de cliente | JWT |
| `GET` | `/crm/cliente/{id}` | Score + diagnóstico CRM | JWT |
| `POST` | `/onboarding/etapa` | Avança etapa do wizard | JWT |
| `GET` | `/chat/historico` | Histórico de conversas | JWT |
| `GET` | `/health` | Health check (DB, Redis, Claude) | — |
| `GET` | `/metrics` | Métricas Prometheus | — |
| `POST` | `/hub/analisar-peticao` | Analisa petição PDF com Claude Opus | JWT (advogado) |
| `POST` | `/hub/consulta` | Consulta jurídica livre no Hub | JWT (advogado) |
| `GET` | `/prospeccao/dna` | DNA atual do escritório | JWT (advogado) |
| `POST` | `/prospeccao/dna/atualizar` | Regenera DNA via Claude | JWT (advogado) |
| `POST` | `/prospeccao/descobrir` | Executa motor de prospecção | JWT (advogado) |
| `GET` | `/prospeccao/pipeline` | Lista leads com filtros e paginação | JWT (advogado) |
| `PATCH` | `/prospeccao/{id}/status` | Atualiza status e notas de um lead | JWT (advogado) |
| `DELETE` | `/prospeccao/{id}` | Remove um lead do pipeline | JWT (advogado) |
| `GET` | `/clientes/{id}/exportar` | Exporta dados pessoais do cliente (LGPD Art. 18, V) | JWT (advogado) |
| `DELETE` | `/clientes/{id}` | Anonimiza dados pessoais do cliente (LGPD Art. 18, IV) | JWT (advogado) |

---

## Compliance

### OAB (Provimento 205/2021)
- IA nunca emite pareceres jurídicos nem prevê resultado de processos
- Disclaimer obrigatório na primeira interação de cada cliente
- Score de risco visível apenas para advogados
- Escalação automática para humano em situações fora de escopo
- Prospecção B2C restrita a canais processuais — sem cold call com dados de litígio

### LGPD (Lei 13.709/2018)
- Criptografia AES-256 em repouso para CPF e dados sensíveis
- TLS 1.3 em trânsito
- Logs de acesso rastreáveis por usuário e timestamp
- Mascaramento: CPF → `***.***.***-XX`, telefone → `(**)****-XXXX`
- Isolamento de dados por `escritorio_id` (row-level multi-tenancy)
- Retenção: dados de processos arquivados removidos após 5 anos
- Endpoints de portabilidade e anonimização implementados: `GET /clientes/{id}/exportar` (Art. 18, V) e `DELETE /clientes/{id}` (Art. 18, IV)

---

## Moats Estratégicos — Vantagens Competitivas Defensáveis

A defensibilidade do Concierge não está no código — está nos dados, na rede e no switching cost acumulado. Cada escritório que entra alimenta múltiplos moats simultaneamente.

### Moats ativos (já operando)

| Moat | Tipo | Como funciona | Replicabilidade |
|------|------|---------------|-----------------|
| **Base RAG proprietária** | Dados | Petições, teses e jurisprudências do escritório alimentam a IA. Quanto mais documentos, melhor a resposta. Efeito composto irreplicável de fora. | ⬛⬛⬛⬛⬛ Quase impossível |
| **Dados de prospecção acumulados** | Dados | DNA do advogado + histórico de leads + taxa de conversão por perfil. O matching score se calibra com feedback real — concorrente começa com heurística genérica. | ⬛⬛⬛⬛⬜ Muito difícil |

### Moats em construção (próximos 6 meses)

| Moat | Tipo | Como funciona | Replicabilidade |
|------|------|---------------|-----------------|
| **Persona treinada por uso** | Switching cost | Cada correção do advogado refina a IA via few-shot acumulado. Após meses de uso, a persona é insubstituível — trocar de produto significa recomeçar do zero. | ⬛⬛⬛⬛⬛ Quase impossível |
| **Dados de experiência jurídica** | Dados | NPS, tempo de resposta, satisfação por fase processual — dados cross-escritório anonimizados que ninguém mais coleta. Nem o CNJ, nem a Jusbrasil. | ⬛⬛⬛⬛⬜ Muito difícil |
| **Rede processual própria** | Escala | Cada escritório traz processos monitorados. Com 50 escritórios = milhares de processos com contexto que a Jusbrasil não tem (fase real, satisfação, histórico do escritório). Reduz e eventualmente elimina dependência de API terceira. | ⬛⬛⬛⬛⬜ Muito difícil |
| **Inteligência preditiva por vara/juiz** | Tecnologia | ML de prazos que melhora com cada processo concluído na plataforma. Novos entrantes precisam de 1–2 anos de dados para chegar onde já estamos. | ⬛⬛⬛⬛⬜ Muito difícil |
| **API aberta para escritórios** | Switching cost | Escritórios integram dados do Concierge nos próprios sites e sistemas internos. Cada integração é uma raiz no stack do cliente — arrancar significa refazer sistemas. | ⬛⬛⬛⬜⬜ Difícil |

### Moats de longo prazo (12–18 meses)

| Moat | Tipo | Como funciona | Replicabilidade |
|------|------|---------------|-----------------|
| **Efeito de rede cross-escritório** | Rede | Marketplace de indicações: leads fora da especialidade são encaminhados para outros escritórios da rede com comissão rastreada. Cada novo escritório torna a plataforma mais valiosa para todos os outros. | ⬛⬛⬛⬛⬛ Quase impossível |
| **Selo "Escritório Digital"** | Marca | Certificação pública de qualidade de atendimento (NPS, tempo de resposta, taxa de autonomia). Inverte a dinâmica comercial: escritórios precisam estar na plataforma para competir, não o contrário. | ⬛⬛⬛⬜⬜ Difícil |
| **Índice de Experiência Jurídica** | Marca | Relatório público periódico com benchmarks anonimizados do mercado. Posiciona a empresa como autoridade — jornalistas citam, escritórios querem ranking favorável. Glassdoor fez com salários; nós fazemos com atendimento jurídico. | ⬛⬛⬛⬜⬜ Difícil |
| **Dados para litechs e seguradoras** | Dados | Dados anonimizados e agregados vendidos como análises e APIs de consulta: seguradoras querem prever custo de litígio, litechs querem avaliar risco de financiamento, departamentos jurídicos querem benchmarks. Linha de receita que não depende de SaaS. | ⬛⬛⬛⬛⬜ Muito difícil |

### Tese de defensibilidade

```
Fase 1 (agora):      Dados proprietários por escritório (RAG + prospecção)
                      → Lock-in individual: cada escritório acumula inteligência própria

Fase 2 (6 meses):    Dados cross-escritório + persona treinável + rede processual
                      → Lock-in de plataforma: valor cresce com a base instalada

Fase 3 (12+ meses):  Efeito de rede + marca + dados vendáveis
                      → Lock-in de ecossistema: trocar não é perder uma ferramenta,
                        é perder acesso a uma rede e a uma posição de mercado
```

> **Insight central:** o ativo mais valioso não é o software — são os dados de experiência jurídica. Nenhum concorrente tem dados estruturados de interação entre escritórios e clientes, cruzados com dados processuais em tempo real e feedback de satisfação. Isso não existe em nenhum lugar do Brasil. O SaaS é o mecanismo de coleta; o valor real está na rede e nos dados.

---

## Variáveis de Ambiente

```bash
# IA
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...           # Whisper

# Banco
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/juridico
REDIS_URL=redis://localhost:6379

# WhatsApp
EVOLUTION_API_URL=http://localhost:8080
EVOLUTION_API_KEY=...
EVOLUTION_WEBHOOK_SECRET=...    # HMAC validation

# Judicial
JUSBRASIL_API_KEY=...
DATAJUD_API_KEY=...             # Gratuito — CNJ

# Google Sheets (opcional)
GOOGLE_SHEETS_CREDENTIALS=...

# Segurança
SECRET_KEY=...                  # JWT signing
ENCRYPTION_KEY=...              # Fernet AES-256

# Observabilidade (opcional em dev)
SENTRY_DSN=...
GRAFANA_CLOUD_API_KEY=...
```

---

## Testes

```bash
make test               # todos os testes
make test-unit          # apenas unitários
make test-integration   # apenas integração
make coverage           # relatório HTML de cobertura
```

- **1.158 testes coletados** — 43 arquivos unitários + 16 arquivos de integração
- Cobertura mínima: **70%** (enforçado no CI com falha de build)
- Banco de testes: SQLite in-memory via `aiosqlite` — sem PostgreSQL necessário em dev
- Feature 3: 89 testes dedicados (heurística de matching componente a componente, LGPD, rotas)

---

## O Que Falta para Production Ready

### Bloqueadores (obrigatório antes de lançar para clientes reais)

| Item | Por que é bloqueador | Estimativa |
|------|---------------------|------------|
| **Validação de produção do banco** | `alembic upgrade head` precisa ser testado em ambiente de staging com dados reais antes do primeiro deploy | Processo, não código |

### Importante (não bloqueia o lançamento, mas afeta qualidade)

| Item | Impacto |
|------|---------|
| **LinkedIn API real** (Partner Program) | Enriquecimento B2B retorna dados mock de contato; funcionalidade existe, dado é vazio |
| **Load testing no CI** | Scripts existem em `tests/load/` mas não rodam no pipeline — sem garantia de performance sob carga |
| **Documentação de API** | `docs/api/` vazia — sem Postman collection nem snapshot OpenAPI para integrações externas |

### Roadmap (não bloqueia, mas são features de valor)

| Feature | Desbloqueio |
|---------|-------------|
| **Feature 2 — Controladoria (Projuris)** | Contrato de API com a Projuris |
| **Feature 4 — ML de Prazos** | ~1.000 processos concluídos para treinar o modelo |
| **Feature 5 — App Mobile B2C** | Decisão de produto e time de frontend |
| **Feature 6 — Integração nativa com CRMs** | Parcerias com Projuris / Astrea / SAJ ADV |

---

## Problemas Conhecidos

| # | Problema | Status |
|---|----------|--------|
| 1 | Migration `004` com `down_revision` errado | ✅ **Corrigido** — aponta corretamente para `e4bcb5d405fa` |
| 2 | Dois arquivos com prefixo `008_` | ✅ **Sem conflito** — cadeia sequencial (`008_add_analytics_indexes` → `008_add_onboarding_fields`); sem branches paralelas |
| 3 | `ScoreRiscoCalculator` acoplada ao módulo `vitoria_preditor.py` | ✅ **Corrigido** — movida para `score_risco.py`; imports atualizados em `monitor_processos`, `hub_juridico_v2`, `hub_advogado_teste`, `test_score_risco` |
| 4 | RAG usa `vector(1024)` e HNSW (spec pedia 1536 + IVFFlat) | ℹ️ **Intencional** — HNSW funciona em tabela vazia e mantém recall estável com inserts incrementais, sem necessidade de recriar índice |

---

## Links

- **Tasks e sub-features:** [TASKS.md](TASKS.md)
- **Guia de desenvolvimento:** [docs/guides/development.md](docs/guides/development.md)
- **Checklist de produção:** [docs/guides/production-readiness.md](docs/guides/production-readiness.md)
- **Gestão de secrets:** [docs/guides/secrets.md](docs/guides/secrets.md)
- **Documentação do banco:** [bancodedados_api.md](bancodedados_api.md)
