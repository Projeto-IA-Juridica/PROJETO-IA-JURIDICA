# PROJETO-IA-JURIDICA

## VISAO GERAL 

### Sumário Executivo

**Visão Geral do Projeto**

O Concierge Jurídico Digital é uma solução de IA conversacional focada em escritórios de advocacia (B2B) que transforma a comunicação entre advogados e clientes sobre processos judiciais, com intuito de melhorar a experiência do cliente. 

A proposta central é criar um assistente inteligente ativo que monitora processos via WhatsApp,traduz linguagem jurídica complexa para termos compreensíveis,notifica o cliente sobre o processo e prevê prazos usando machine learning.

**Diferencial Competitivo Principal**

Enquanto soluções existentes enviam notificações automatizadas com textos técnicos ou usam menus simples ("pressione 1 para X"), nosso agente autônomo compreende perguntas em linguagem natural (texto ou áudio), consulta processos em tempo real, verifica jurisprudência e responde em segundos com uma persona humanizada. Além disso, o agente atua como uma camada ativa de relacionamento com o cliente. 

Mesmo em períodos de ausência de movimentação processual, a IA mantém comunicação proativa e transparente, informando que o processo permanece sob análise pelo juízo competente, explicando o estágio atual e contextualizando os trâmites que justificam eventuais períodos de inatividade.

### Questões Regulatórias (OAB e LGPD)

**Posicionamento perante a OAB**

O documento original identificou corretamente a Red Flag #1. A estratégia de compliance deve ser:

**1. Disclaimers Obrigatórios em Toda Comunicação**

A IA deve incluir, na primeira interação com cada cliente, uma mensagem clara:

"Olá! Sou a assistente digital do escritório [Nome]. Posso ajudar você a acompanhar seu processo e traduzir termos jurídicos, mas não substituo a orientação do seu advogado. Para decisões legais, sempre consulte o Dr./Dra. [Nome]."

**2. Limitação de Escopo Funcional**

A IA NUNCA deve:
- Dar pareceres jurídicos ("você deve fazer X")
- Prever resultados de processos com certeza
- Oferecer estratégias processuais

A IA PODE e DEVE:
- Informar o status atual do processo
- Divulgar o que a lei fala
- Traduzir termos jurídicos ("sentença de primeira instância significa...")
- Explicar próximos passos procedimentais previstos em lei
- Agendar consultas com o advogado responsável

**3. Modelo Jurídico de Responsabilidade**

O contrato B2B com escritórios deve deixar claro que:
- A IA é ferramenta do escritório, não substituto do advogado
- Responsabilidade por orientações inadequadas é do escritório contratante
- Recomendamos cláusula expressa no contrato de honorários do escritório com o cliente final mencionando o uso de tecnologia assistiva

**Conformidade LGPD**

Processos judiciais contêm dados sensíveis (CPF, saúde, filiação). A arquitetura deve garantir:

**Medidas Técnicas Obrigatórias**
- Criptografia AES-256 em repouso (RDS) e TLS 1.3 em trânsito
- Logs de acesso com rastreabilidade completa (quem acessou qual CPF, quando)
- Retenção de dados limitada: dados de processos arquivados deletados após 5 anos
- Segregação por tenant: dados do Escritório A fisicamente isolados do Escritório B

**Medidas Organizacionais**
- DPO (Data Protection Officer) externo nos primeiros 12 meses
- RIPD (Relatório de Impacto à Proteção de Dados) elaborado e atualizado anualmente
- Contratos de processamento de dados com cada escritório cliente
- Treinamento obrigatório da equipe técnica em privacidade (40h/ano)

**Direitos dos Titulares**

O sistema deve permitir, via portal administrativo do escritório:
- Exportação de dados de um cliente em formato estruturado (portabilidade)
- Exclusão de dados de cliente mediante solicitação (direito ao esquecimento)
- Relatório de acessos aos dados do cliente (transparência)

## ESTRUTURA DAS PASTAS

> Legenda: ✅ Implementado | ❌ Não iniciado

```
concierge-juridico/
│
├── shared/ ──────────────────────────────────────────────────────────────
│   │   (Core compartilhado entre TODAS as features)
│   │
│   ├── models/ ─────────────────── SQLAlchemy models do banco de dados
│   │   ├── base.py ────────────── ✅ Base class para todos os models
│   │   ├── escritorio.py ──────── ✅ Model: Escritório (cliente B2B)
│   │   ├── cliente.py ─────────── ✅ Model: Cliente final (pessoa física)
│   │   ├── processo.py ────────── ✅ Model: Processos judiciais
│   │   ├── usuario.py ─────────── ✅ Model: Usuários (advogados, assistentes)
│   │   └── interacao.py ───────── ✅ Model: Logs de interações IA-Cliente
│   │
│   ├── schemas/ ────────────────── Pydantic schemas (validação de dados)
│   │   ├── escritorio.py ──────── ✅ Schemas de request/response Escritório
│   │   ├── cliente.py ─────────── ✅ Schemas Cliente
│   │   ├── processo.py ────────── ✅ Schemas Processo
│   │   ├── usuario.py ─────────── ✅ Schemas Usuario
│   │   └── response.py ────────── ✅ Schemas genéricos de resposta
│   │
│   ├── database/ ───────────────── Configuração de conexão com banco
│   │   ├── connection.py ──────── ✅ Engine SQLAlchemy, sessão factory
│   │   ├── session.py ─────────── ✅ Dependency Injection de sessão DB
│   │   └── worker_queries.py ──── ✅ Queries utilitárias para workers
│   │
│   ├── utils/ ──────────────────── Utilitários comuns a todas features
│   │   ├── validators.py ──────── ✅ Validadores (CPF, CNPJ, nº processo)
│   │   ├── formatters.py ──────── ✅ Formatação de dados (datas, moeda)
│   │   ├── lgpd.py ────────────── ✅ Utilitários de compliance LGPD
│   │   └── audio_handler.py ───── ✅ Conversão e processamento de áudios
│   │
│   ├── security/ ───────────────── Segurança e autenticação
│   │   ├── jwt.py ─────────────── ✅ Criação e validação de tokens JWT
│   │   ├── encryption.py ──────── ✅ Criptografia de dados sensíveis
│   │   └── permissions.py ─────── ✅ Sistema de permissões (RBAC)
│   │
│   ├── config/ ─────────────────── Configurações globais
│   │   ├── settings.py ────────── ✅ Pydantic Settings (env vars)
│   │   ├── constants.py ───────── ✅ Constantes globais do sistema
│   │   ├── logging.py ─────────── ✅ Structlog configurado
│   │   └── secrets.py ─────────── ✅ AWS Secrets Manager + Vault
│   │
│   └── tests/ ──────────────────── Testes do core
│       ├── test_encryption.py ──── ✅
│       ├── test_schemas.py ─────── ✅
│       ├── test_utils.py ───────── ✅
│       └── test_validators.py ──── ✅
│
│
├── feature-1-ia-personalizada/ ──────────────────────────────────────────
│   │   (MVP - IA conversacional + WhatsApp + Monitoramento)
│   │
│   ├── api/ ────────────────────── FastAPI application
│   │   ├── app.py ──────────────── ✅ FastAPI app (243 linhas)
│   │   ├── routes/ ─────────────── Endpoints REST
│   │   │   ├── auth.py ──────────── ✅ POST /auth/login, /refresh, GET /me
│   │   │   ├── webhook_whatsapp.py ─ ✅ POST /webhook/whatsapp
│   │   │   ├── processos.py ─────── ✅ CRUD de processos + sync
│   │   │   ├── chat.py ──────────── ✅ GET /chat/history, POST /chat/send
│   │   │   ├── health.py ────────── ✅ GET /health, /health/ready
│   │   │   ├── metrics.py ───────── ✅ Prometheus metrics
│   │   │   └── admin_import.py ──── ✅ Importação de dados (admin)
│   │   │
│   │   └── middleware/ ──────────── Middlewares FastAPI
│   │       ├── auth.py ──────────── ✅ Middleware de autenticação JWT
│   │       ├── rate_limit.py ────── ✅ Rate limiting por IP/user (Redis)
│   │       └── request_logging.py ─ ✅ Log de requisições
│   │
│   ├── services/ ───────────────── Lógica de negócio
│   │   │
│   │   ├── ai/ ─────────────────── Orquestração de IA
│   │   │   ├── orchestrator.py ──── ✅ ⭐ LangGraph workflow (6 nós)
│   │   │   ├── claude_client.py ─── ✅ Cliente Anthropic Claude API
│   │   │   ├── prompts.py ───────── ✅ Templates de system prompts
│   │   │   ├── memory.py ────────── ✅ Memória de conversação (Redis)
│   │   │   ├── fact_checker.py ──── ✅ Anti-alucinação (verifica com DB)
│   │   │   ├── translator.py ────── ✅ Tradução termos jurídicos→leigo
│   │   │   └── juridical_translator.py ─ ✅ Tradutor jurídico avançado
│   │   │
│   │   ├── messaging/ ──────────── Comunicação WhatsApp
│   │   │   ├── whatsapp.py ──────── ✅ Envio de mensagens (wrapper)
│   │   │   ├── evolution_client.py ─ ✅ Cliente Evolution API
│   │   │   ├── templates.py ─────── ✅ Templates prontos (NPS, boas-vindas, etc.)
│   │   │   └── scheduler.py ─────── ✅ Agendamento (respeita horário comercial)
│   │   │
│   │   ├── legal_data/ ─────────── Busca de dados processuais
│   │   │   ├── jusbrasil_client.py ─ ✅ Cliente Jusbrasil API (primário)
│   │   │   ├── datajud_client.py ─── ✅ Cliente DataJud CNJ (backup gratuito)
│   │   │   ├── data_cleaner.py ──── ✅ Pipeline de limpeza de dados
│   │   │   ├── cache_manager.py ─── ✅ Cache inteligente Redis (1h TTL)
│   │   │   └── vitoria_preditor.py ─ ✅ Preditor de resultado (legado)
│   │   │
│   │   └── integrations/ ────────── Integrações externas
│   │       ├── google_sheets.py ─── ✅ Cliente Google Sheets API
│   │       └── import_clientes.py ── ✅ Importação de clientes via CSV/Sheets
│   │
│   ├── workers/ ────────────────── Celery workers (tarefas assíncronas)
│   │   ├── celery_app.py ──────── ✅ Config Celery (4 filas)
│   │   ├── monitor_processos.py ─ ✅ Worker: monitoramento 24/7
│   │   ├── send_notifications.py ─ ✅ Worker: notificações em lote
│   │   ├── mensagens_relacionamento.py ─ ✅ Worker: msgs comemorativas
│   │   ├── webhook_whatsapp.py ─── ✅ Worker: processamento webhook
│   │   └── dead_letter.py ──────── ✅ Handler de fila morta (DLQ)
│   │
│   ├── tests/ ──────────────────── Testes automatizados
│   │   ├── unit/ (22 arquivos) ─── ✅ Cobertura total dos serviços
│   │   └── integration/ (6 arquivos) ✅ Fluxos end-to-end
│   │
│   └── data/ ───────────────────── Dados estáticos
│       ├── knowledge_base/
│       │   ├── disclaimers.json ─── ✅ Disclaimers OAB obrigatórios
│       │   └── datas_comemorativas.json ─ ✅ Datas profissionais
│       │
│       └── termos_juridicos/
│           └── traducoes.json ───── ✅ ~50 termos jurídicos (MVP)
│
│
├── feature-2-controladoria/ ─────────────────────────────────────────────
│   │   (Avisos de deveres diários + Integração Projuris)
│   │
│   ├── api/routes/
│   │   ├── deveres.py ───────────── ❌ GET /deveres/hoje
│   │   ├── tarefas.py ───────────── ❌ CRUD de tarefas
│   │   └── dashboard.py ─────────── ❌ GET /dashboard/analytics
│   │
│   ├── services/
│   │   ├── integrations/
│   │   │   ├── projuris_client.py ─ ❌ ⭐ Cliente OAuth2 Projuris API
│   │   │   └── base_crm.py ──────── ❌ Interface base para outros CRMs
│   │   │
│   │   └── business/
│   │       ├── dever_manager.py ─── ❌ Parser de deveres do Projuris
│   │       ├── notificador.py ───── ❌ Envia avisos via WhatsApp (usa F1)
│   │       └── analytics.py ─────── ❌ Métricas de produtividade
│   │
│   ├── workers/
│   │   ├── check_deveres_diarios.py ❌ Cron 6h, 12h, 18h
│   │   └── send_alerts.py ─────── ❌ Alertas de prazos
│   │
│   └── tests/ ───────────────────── ❌ Não iniciados
│
│
├── feature-3-conexoes/ ──────────────────────────────────────────────────
│   │   (Chat interno + Distribuição de tarefas entre funcionários)
│   │
│   ├── api/routes/
│   │   ├── funcionarios.py ────── ❌ CRUD de funcionários
│   │   ├── empresas.py ────────── ❌ CRUD de empresas clientes
│   │   ├── conexoes.py ────────── ❌ Conexões funcionário↔empresa
│   │   └── chat.py ────────────── ❌ Mensagens
│   │
│   ├── services/
│   │   ├── chat/
│   │   │   ├── chat_manager.py ──── ❌ ⭐ Gerencia conexões WebSocket
│   │   │   └── message_handler.py ─ ❌ Processa/roteia mensagens
│   │   │
│   │   └── permissions/
│   │       ├── acl.py ───────────── ❌ Access Control List (Casbin)
│   │       └── role_manager.py ──── ❌ Gerencia roles
│   │
│   ├── websockets/
│   │   ├── chat_server.py ─────── ❌ ⭐ Servidor WebSocket
│   │   └── events.py ──────────── ❌ Handlers de eventos WS
│   │
│   ├── workers/
│   │   └── distribute_tasks.py ─── ❌ Distribuição automática
│   │
│   └── tests/ ───────────────────── ❌ Não iniciados
│
│
├── feature-4-ml-prazos/ ─────────────────────────────────────────────────
│   │   (Predição de prazos processuais com Machine Learning)
│   │
│   ├── api/routes/
│   │   ├── predicoes.py ─────────── ❌ POST /predict/prazo
│   │   └── metrics.py ───────────── ❌ GET /model/metrics (MAE, RMSE, R²)
│   │
│   ├── services/ml/
│   │   ├── prazo_predictor.py ───── ❌ ⭐ Classe principal de predição
│   │   ├── model_trainer.py ─────── ❌ Treino (Random Forest, XGBoost)
│   │   └── evaluator.py ─────────── ❌ Avaliação de performance
│   │
│   ├── services/feature_engineering/
│   │   ├── extractor.py ─────────── ❌ Extrai features dos processos
│   │   └── transformer.py ───────── ❌ Transforma/normaliza features
│   │
│   ├── models/
│   │   ├── trained/ ────────────── ❌ .pkl dos modelos em produção
│   │   └── registry/ ───────────── ❌ Metadata MLflow
│   │
│   ├── workers/
│   │   ├── train_models.py ────── ❌ Re-treino semanal
│   │   └── update_predictions.py ─ ❌ Atualiza predições
│   │
│   ├── notebooks/
│   │   ├── exploratory_analysis.ipynb ❌ EDA
│   │   └── model_comparison.ipynb ──── ❌ Comparação de modelos
│   │
│   └── tests/ ───────────────────── ❌ Não iniciados
│
│
├── feature-5-app-mobile/ ────────────────────────────────────────────────
│   │   (App mobile - Competidor JusBrasil)
│   │
│   ├── src/screens/
│   │   ├── LoginScreen.tsx ──────── ❌
│   │   ├── ProcessosScreen.tsx ──── ❌
│   │   ├── ProcessoDetailScreen.tsx ❌
│   │   ├── ChatIAScreen.tsx ─────── ❌
│   │   ├── PaymentScreen.tsx ─────── ❌ (Stripe)
│   │   └── ProfileScreen.tsx ─────── ❌
│   │
│   ├── src/components/ ──────────── ❌ Não iniciados
│   ├── src/services/ ────────────── ❌ Não iniciados
│   ├── src/navigation/ ──────────── ❌ Não iniciados
│   ├── src/store/ ───────────────── ❌ Não iniciados
│   │
│   ├── api-backend/routes/
│   │   ├── auth.py ──────────────── ❌
│   │   ├── processos.py ─────────── ❌
│   │   ├── pagamentos.py ────────── ❌ (Stripe webhooks)
│   │   └── planos.py ────────────── ❌ (R$ 29,90 / R$ 79,90)
│   │
│   └── api-backend/services/
│       ├── stripe_client.py ─────── ❌ ⭐ Assinaturas Stripe
│       └── document_service.py ───── ❌ URLs pré-assinadas S3
│
│
├── feature-6-integracao-crms/ ───────────────────────────────────────────
│   │   (Ecossistema fechado - Integrações nativas com 3 CRMs)
│   │
│   ├── api/routes/ ──────────────── ❌ Não iniciados
│   ├── services/sync/ ───────────── ❌ Não iniciados
│   ├── services/webhooks/ ───────── ❌ Não iniciados
│   │
│   ├── adapters/
│   │   ├── base_adapter.py ─────── ❌ Interface AbstractAdapter
│   │   ├── projuris/ ───────────── ❌ Adapter Projuris (client, adapter, mapper)
│   │   ├── astrea/ ─────────────── ❌ Adapter Astrea
│   │   └── saj_adv/ ────────────── ❌ Adapter SAJ ADV (SOAP)
│   │
│   ├── workers/ ────────────────── ❌ Não iniciados
│   └── tests/ ──────────────────── ❌ Não iniciados
│
│
├── infrastructure/ ──────────────────────────────────────────────────────
│   │
│   ├── terraform/ ──────────────── ❌ IaC AWS (não iniciado)
│   │
│   ├── docker/
│   │   ├── Dockerfile.f1 ───────── ✅ Imagem Feature 1
│   │   ├── docker-compose.yml ──── ✅ Compose desenvolvimento
│   │   └── docker-compose.prod.yml ✅ Compose produção
│   │
│   ├── kubernetes/ ─────────────── ❌ Manifests K8s (não iniciados)
│   │
│   └── scripts/
│       └── backup.sh ───────────── ✅ Backup PostgreSQL
│
│
├── monitoring/ ──────────────────────────────────────────────────────────
│   ├── alerts.yml ──────────────── ✅ Regras Prometheus
│   ├── grafana-agent.yaml ──────── ✅ Grafana Agent (produção)
│   ├── grafana-agent-local.yaml ─── ✅ Grafana Agent (local)
│   ├── loki-config.yaml ────────── ✅ Loki (logs)
│   └── promtail-config.yaml ────── ✅ Promtail (log shipping)
│
│
├── docs/
│   ├── guides/
│   │   ├── development.md ──────── ✅ Guia de desenvolvimento
│   │   ├── production-readiness.md ✅ Checklist produção
│   │   └── secrets.md ──────────── ✅ Gestão de secrets
│   │
│   ├── api/ ────────────────────── ❌ OpenAPI spec / Postman collection
│   ├── architecture/ ───────────── ❌ Diagramas de arquitetura
│   └── deployment/ ─────────────── ❌ Guias AWS / K8s
│
│
└── scripts/
    ├── setup/
    │   ├── init_db.py ──────────── ✅ Cria tabelas + migrations
    │   ├── seed_data.py ────────── ✅ Popula dados iniciais
    │   └── create_admin.py ─────── ✅ Cria usuário admin
    │
    ├── chat_ao_vivo.py ─────────── ✅ Interface de chat ao vivo
    ├── hub_advogado_teste.py ────── ✅ Testes hub do advogado
    ├── streamlit_chat.py ────────── ✅ Chat via Streamlit
    ├── monitoring/health_check.py ─ ✅ Health check das APIs
    │
    └── migration/ ──────────────── ❌ Scripts de migração de versões

```

---

## PROGRESSO DO PROJETO

### Por Feature

| Feature | Descrição | Status | Progresso |
|---|---|---|---|
| **Feature 1** | IA Personalizada (MVP) | ✅ Concluída | `████████████████████` 100% |
| **Feature 2** | Controladoria (Projuris) | ❌ Não iniciada | `░░░░░░░░░░░░░░░░░░░░` 0% |
| **Feature 3** | Conexões (Chat interno) | ❌ Não iniciada | `░░░░░░░░░░░░░░░░░░░░` 0% |
| **Feature 4** | ML Prazos | ❌ Não iniciada | `░░░░░░░░░░░░░░░░░░░░` 0% |
| **Feature 5** | App Mobile | ❌ Não iniciada | `░░░░░░░░░░░░░░░░░░░░` 0% |
| **Feature 6** | Integração CRMs | ❌ Não iniciada | `░░░░░░░░░░░░░░░░░░░░` 0% |
| **Infra/DevOps** | Docker, CI/CD, Monitoring | ✅ Concluída | `████████████████████` 100% |

### Por Camada (Feature 1 detalhado)

| Camada | Arquivos | Feito |
|---|---|---|
| Setup & Config | 16 | ✅ 16/16 |
| Shared Core (models, schemas, security, utils) | 28 | ✅ 28/28 |
| API (rotas + middleware) | 12 | ✅ 12/12 |
| Serviços AI (orchestrator, claude, memory, etc.) | 7 | ✅ 7/7 |
| Serviços Legal Data | 5 | ✅ 5/5 |
| Serviços Messaging | 4 | ✅ 4/4 |
| Workers Celery | 6 | ✅ 6/6 |
| Testes (unit + integration) | 28 | ✅ 28/28 |
| Infra / DevOps / Monitoring | 14 | ✅ 14/14 |

### Porcentagem Geral

```
MVP (Feature 1 + Infra):   ████████████████████  100%  ← pronto para produção
Features 2-6:              ░░░░░░░░░░░░░░░░░░░░    0%  ← backlog

TOTAL DO PROJETO:  ~30% concluído
```

> **Nota:** A Feature 1 corresponde a ~60% do valor de negócio do produto final.
> O MVP está completo com 155 arquivos implementados, testes automatizados,
> compliance OAB/LGPD, monitoramento e pipeline CI/CD configurados.
    │
    ├── backup/ ─────────────────── Scripts de backup
    │   ├── backup_to_s3.py ─────── Backup diário para S3
    │   └── restore_from_backup.py ─ Restore de backup
    │
    └── monitoring/ ─────────────── Scripts de monitoramento
        ├── health_check.py ─────── Health check das APIs
        └── performance_test.py ─── Testes de performance/carga

```

## FUNCIONALIDADES ADICIONAIS 

- IA personalizada ( pesquisa de satisfação, responde duvidas, notifica os clientes sobre os processos , da boas-vindas para novos clientes) FEITO
- Controladoria - IA avisa sobre os deveres e funções do dia: Projuris - FALTA INTEGRAÇÃO COM O PROJURIS 
- Realizar conexões entre  funcionários de empresas e escritórios - LINKEDIN
- Estimativa de prazo : depende da participação do autor/ réu e da quantidade de problemas. FEITO
- Concorrente JusBrasil - oferecer ao advogado um aplicativo para vender acesso sobre os processos para o cliente: 
- Ao realizar o pagamento, o cliente terá acesso completo ao documento sobre o processo e a um IA que tira todas as dúvidas sobre o processo.
- Plano IA cliente VS Plano IA empresa
- Ecossistema de dados fechados: ProJuris

## FERRAMENTAS NECESSARIAS - Stack Tecnológica e APIs

Este documento consolida toda a stack tecnológica e APIs necessárias para cada feature do Concierge Jurídico Digital.

### SHARED (Core Compartilhado)

**Dependências Base**

```python
# requirements-base.txt
fastapi==0.109.0
uvicorn[standard]==0.27.0
sqlalchemy==0.0.25
alembic==1.13.1
psycopg2-binary==2.9.9
redis==5.0.1
cryptography==42.0.0
python-jose[cryptography]==3.3.0
httpx==0.26.0
pydantic==2.5.0
prometheus-client==0.19.0
sentry-sdk[fastapi]==1.40.0
```

**Modelos Compartilhados**
- Escritorio - Dados do escritório cliente
- Cliente - Clientes finais (pessoas físicas)
- Processo - Processos judiciais
- Usuario - Usuários do sistema (advogados, assistentes)
- Interacao - Logs de interações IA-Cliente

### FEATURE 1 - IA Personalizada (MVP)

**Stack Completa**

```python
# Core
fastapi==0.109.0
uvicorn[standard]==0.27.0

# IA & LLM
langchain==0.1.0
langgraph==0.0.20
anthropic==0.18.0      # Claude Sonnet 4
openai==1.12.0         # Whisper (transcrição)

# Database
sqlalchemy==2.0.25
psycopg2-binary==2.9.9
redis==5.0.1

# Async Tasks
celery==5.3.6
flower==2.0.1

# HTTP
httpx==0.26.0
aiohttp==3.9.3

# Google Sheets Integration
google-api-python-client==2.116.0
google-auth==2.27.0
```

**APIs Externas**

#### 1️⃣ Anthropic Claude API

```yaml
URL: https://api.anthropic.com/v1/messages
Modelo: claude-sonnet-4-20250514
Custo:
  - Input: $0.003 por 1K tokens (~R$ 0.015)
  - Output: $0.015 por 1K tokens (~R$ 0.075)
  - Média/interação: R$ 0.10
Uso: IA conversacional principal
Auth: API Key (Bearer token)
```

**Exemplo de uso:**

```python
from anthropic import Anthropic

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

message = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1024,
    temperature=0.3,
    system="Você é um assistente jurídico...",
    messages=[
        {"role": "user", "content": "Qual o status do meu processo?"}
    ]
)
```

#### 2️⃣ Evolution API (WhatsApp)

```yaml
URL: http://seu-servidor:8080 (self-hosted)
Custo: 
  - Self-hosted: R$ 0 (VPS R$ 50/mês)
  - Cloud managed: R$ 50-100/mês
Uso: Envio/recebimento mensagens WhatsApp
Auth: API Key
Docs: https://doc.evolution-api.com
```

**Endpoints principais:**

```python
# Enviar mensagem
POST /message/sendText/{instance}
{
  "number": "5511999999999",
  "textMessage": {
    "text": "Olá! Seu processo foi atualizado..."
  }
}

# Webhook (receber mensagens)
POST /webhook/set/{instance}
{
  "url": "https://sua-api.com/webhook/whatsapp",
  "events": ["messages.upsert"]
}
```

#### 3️⃣ Jusbrasil API Giga

```yaml
URL: https://api.jusbrasil.com.br/v2
Custo: R$ 1,50 por processo/mês (monitoramento)
Uso: Busca e monitoramento de processos
Auth: API Key
```

**Endpoints:**

```python
# Buscar processo
GET /processos?numero=0001234-56.2024.8.26.0100
Headers: {"Authorization": "Bearer {API_KEY}"}

# Andamentos
GET /processos/{id}/andamentos

# Webhook (notificações)
POST /webhooks
{
  "url": "https://sua-api.com/webhook/jusbrasil",
  "eventos": ["andamento_processual"]
}
```

#### 4️⃣ DataJud (CNJ) - Backup

```yaml
URL: https://datajud-api.cnj.jus.br
Custo: Gratuito
Uso: API pública dos tribunais (fallback)
Auth: Sem autenticação
Docs: https://www.cnj.jus.br/sistemas/datajud/
```

#### 5️⃣ OpenAI Whisper API

```yaml
URL: https://api.openai.com/v1/audio/transcriptions
Custo: $0.006 por minuto (~R$ 0.03/min)
Uso: Transcrição de áudios WhatsApp
Auth: Bearer token
```

**Exemplo:**

```python
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

audio_file = open("audio.ogg", "rb")
transcript = client.audio.transcriptions.create(
  model="whisper-1",
  file=audio_file,
  language="pt"
)
```

#### 6️⃣ Google Sheets API

```yaml
URL: https://sheets.googleapis.com/v4/spreadsheets
Custo: Gratuito (até 100k reads/dia)
Uso: Gerenciamento de dados de clientes (MVP)
Auth: Service Account (OAuth2)
Docs: https://developers.google.com/sheets/api
```

**Setup:**
1. Criar projeto no Google Cloud Console
2. Ativar Google Sheets API
3. Criar Service Account
4. Baixar JSON de credenciais
5. Compartilhar planilha com email da service account

**Exemplo de uso:**

```python
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

creds = Credentials.from_service_account_file(
    'credentials.json',
    scopes=['https://www.googleapis.com/auth/spreadsheets.readonly']
)

service = build('sheets', 'v4', credentials=creds)
result = service.spreadsheets().values().get(
    spreadsheetId='SPREADSHEET_ID',
    range='Clientes!A2:I'
).execute()
```

**Estrutura das Planilhas:**

**Planilha 1: Clientes**
- ID, Nome, Telefone, CPF, Data Nascimento, Profissão, Empresa, Status, Último Contato

**Planilha 2: Datas Comemorativas**
- Profissão, Data, Nome da Comemoração, Template Mensagem

**Planilha 3: Log de Mensagens**
- Cliente ID, Tipo, Data Envio, Sucesso, Erro

### FEATURE 2 - Controladoria

**Stack Adicional**

```python
# Base + 
pandas==2.2.0           # Análise de dados
numpy==1.26.3
oauthlib==3.2.2         # OAuth2
requests-oauthlib==1.3.1
schedule==1.2.0         # Cron jobs
```

**APIs Externas**

#### 1️⃣ Projuris API

```yaml
URL: https://api.projuris.com.br/v2
Custo: Incluído no CRM do cliente (R$ 0 adicional)
Uso: Sincronização tarefas, prazos, audiências
Auth: OAuth2
Docs: https://docs.projuris.com.br
```

**OAuth2 Flow:**

```python
# 1. Authorization URL
GET https://auth.projuris.com.br/oauth/authorize
  ?client_id={CLIENT_ID}
  &redirect_uri={REDIRECT_URI}
  &response_type=code
  &scope=read:processos write:tarefas

# 2. Exchange code for token
POST https://auth.projuris.com.br/oauth/token
{
  "grant_type": "authorization_code",
  "code": "{CODE}",
  "client_id": "{CLIENT_ID}",
  "client_secret": "{CLIENT_SECRET}",
  "redirect_uri": "{REDIRECT_URI}"
}

# 3. Use access token
GET https://api.projuris.com.br/v2/tarefas?data_vencimento=2026-02-16
Headers: {"Authorization": "Bearer {ACCESS_TOKEN}"}
```

**Endpoints principais:**

```python
GET /api/v2/tarefas?status=pendente
GET /api/v2/audiencias?data={hoje}
GET /api/v2/prazos?vencimento=proximos-7-dias
POST /api/v2/webhooks  # Registro de webhooks
```

### FEATURE 3 - Conexões

**Stack Adicional**

```python
# Base +
websockets==12.0        # WebSocket server
python-socketio==5.11.0 # Socket.IO
aioredis==2.0.1         # Redis async
casbin==1.31.0          # ACL (permissões)
```

**Tecnologias**

**WebSocket (FastAPI)**

```python
from fastapi import WebSocket

@app.websocket("/ws/chat/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int):
    await websocket.accept()
    # Gerenciar conexões persistentes
```

**Redis Pub/Sub**

```python
import redis

# Publisher
redis_client.publish("chat:escritorio:1", json.dumps(message))

# Subscriber
pubsub = redis_client.pubsub()
pubsub.subscribe("chat:escritorio:1")
for message in pubsub.listen():
    # Processar mensagens
```

### FEATURE 4 - ML Prazos

**Stack ML**

```python
# Base +
scikit-learn==1.4.0     # ML tradicional
xgboost==2.0.3          # Gradient boosting
lightgbm==4.2.0         # Alternative GB
pandas==2.2.0
numpy==1.26.3
scipy==1.11.4

# Feature Engineering
category-encoders==2.6.3
imbalanced-learn==0.11.0

# Model Management
mlflow==2.10.0          # Versionamento
joblib==1.3.2           # Serialização

# Viz (notebooks)
matplotlib==3.8.2
seaborn==0.13.1
jupyter==1.0.0
```

**Modelos ML**

**Random Forest Regressor**

```python
from sklearn.ensemble import RandomForestRegressor

model = RandomForestRegressor(
    n_estimators=100,
    max_depth=10,
    random_state=42
)

features = ['tribunal_encoded', 'dias_sem_mov', 'qtd_partes', 
            'complexidade_score', 'media_prazo_vara']

model.fit(X_train[features], y_train)
```

**XGBoost**

```python
import xgboost as xgb

dtrain = xgb.DMatrix(X_train, label=y_train)
params = {
    'objective': 'reg:squarederror',
    'max_depth': 6,
    'learning_rate': 0.1
}
model = xgb.train(params, dtrain, num_boost_round=100)
```

**MLflow (Versionamento)**

```python
import mlflow

mlflow.set_experiment("prazo_predictor")

with mlflow.start_run():
    mlflow.log_param("n_estimators", 100)
    mlflow.log_metric("mae", 15.2)
    mlflow.sklearn.log_model(model, "model")
```

### FEATURE 5 - App Mobile

**Stack Frontend (React Native)**

```json
{
  "react-native": "0.73.2",
  "expo": "~50.0.0",
  "@react-navigation/native": "^6.1.0",
  "@tanstack/react-query": "^5.17.0",
  "zustand": "^4.4.7",
  "react-native-whatsapp": "latest"
}
```

**Stack Backend**

```python
# Base +
stripe==8.0.0           # Pagamentos
boto3==1.34.34          # AWS S3
pyjwt==2.8.0            # JWT mobile
firebase-admin==6.4.0   # Push notifications
Pillow==10.2.0          # Image processing
```

**APIs Externas**

#### 1️⃣ Stripe (Pagamentos)

```yaml
URL: https://api.stripe.com/v1
Custo: 
  - Brasil: 3.99% + R$ 0.39 por transação
  - Internacional: 6.99% + R$ 0.39
Uso: Assinaturas recorrentes
Auth: API Key (Secret Key)
Docs: https://stripe.com/docs/api
```

**Criar assinatura:**

```python
import stripe

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

# Criar cliente
customer = stripe.Customer.create(
    email="cliente@example.com",
    payment_method="pm_card_visa"
)

# Criar assinatura
subscription = stripe.Subscription.create(
    customer=customer.id,
    items=[{"price": "price_ia_cliente_mensal"}],
    payment_behavior="default_incomplete",
    expand=["latest_invoice.payment_intent"]
)
```

**Webhook (eventos):**

```python
@app.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    
    event = stripe.Webhook.construct_event(
        payload, sig_header, webhook_secret
    )
    
    if event.type == "invoice.payment_succeeded":
        # Ativar acesso do cliente
        pass
```

#### 2️⃣ AWS S3 (Documentos)

```python
import boto3

s3 = boto3.client('s3',
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY"),
    aws_secret_access_key=os.getenv("AWS_SECRET_KEY")
)

# Upload
s3.upload_file('documento.pdf', 'bucket-docs', 'processo/123/doc.pdf')

# URL pré-assinada (1 hora)
url = s3.generate_presigned_url(
    'get_object',
    Params={'Bucket': 'bucket-docs', 'Key': 'processo/123/doc.pdf'},
    ExpiresIn=3600
)
```

#### 3️⃣ Firebase Cloud Messaging (Push)

```python
from firebase_admin import messaging

message = messaging.Message(
    notification=messaging.Notification(
        title="Novo andamento!",
        body="Seu processo teve atualização"
    ),
    token=device_token
)

response = messaging.send(message)
```

### FEATURE 6 - Integração CRMs

**Stack Adicional**

```python
# Base +
zeep==4.2.1             # SOAP (SAJ ADV)
oauthlib==3.2.2         # OAuth2
marshmallow==3.20.1     # Data mapping
pyhmac==1.0.0           # Webhook security
```

**APIs de CRMs**

#### 1️⃣ Projuris

```yaml
URL: https://api.projuris.com.br/v2
Auth: OAuth2
Market Share: ~40% escritórios BR
```

#### 2️⃣ Astrea

```yaml
URL: https://api.astrea.com.br/v1
Auth: API Key
Market Share: ~30%
```

**Exemplo:**

```python
import httpx

headers = {"X-API-Key": os.getenv("ASTREA_API_KEY")}

# Listar processos
response = httpx.get(
    "https://api.astrea.com.br/v1/processos",
    headers=headers
)

# Webhook
httpx.post(
    "https://api.astrea.com.br/v1/webhooks",
    headers=headers,
    json={
        "url": "https://nossa-api.com/webhook/astrea",
        "events": ["processo.atualizado"]
    }
)
```

#### 3️⃣ SAJ ADV

```yaml
URL: https://api.sajadv.com.br/v1
Auth: OAuth2 (híbrido SOAP/REST)
Market Share: ~20%
Webhook: Não disponível (polling necessário)
```

**SOAP Client (zeep):**

```python
from zeep import Client

wsdl = "https://api.sajadv.com.br/soap?wsdl"
client = Client(wsdl=wsdl)

# Buscar processos
processos = client.service.ListarProcessos(
    escritorio_id=123,
    data_inicio="2026-01-01"
)
```

### Infraestrutura AWS

**Serviços Utilizados**

```yaml
# Compute
AWS Lambda: Execução serverless de workers
EC2: APIs (se não usar Lambda)

# Database
RDS PostgreSQL: Banco principal (Multi-AZ)
ElastiCache Redis: Cache + sessions

# Storage
S3: Documentos PDF, backups
S3 Glacier: Arquivamento long-term

# Networking
CloudFront: CDN para frontend
Route53: DNS
VPC: Rede isolada

# Monitoring
CloudWatch: Logs + métricas
SNS: Alertas
SQS: Filas de mensagens

# Security
Secrets Manager: Credenciais
IAM: Permissões
KMS: Criptografia keys
```

**Estimativa de Custos AWS (100 processos)**

```
RDS db.t3.micro (Postgres):      R$ 80/mês
ElastiCache t3.micro (Redis):    R$ 60/mês
S3 (100GB):                      R$ 15/mês
Lambda (500k invocations):       R$ 5/mês
CloudFront (1TB transfer):       R$ 40/mês
────────────────────────────────────────
TOTAL:                           R$ 200/mês
```

### Resumo de Custos por Feature

**Feature 1 (100 processos)**

```
Jusbrasil API:         R$ 150/mês
Claude API:            R$ 50/mês
OpenAI Whisper:        R$ 10/mês
AWS:                   R$ 200/mês
Google Sheets API:     R$ 0 (free tier)
────────────────────────────────
SUBTOTAL:              R$ 410/mês

Mensagens Relacionamento:
- Aniversários:        R$ 0,08/mês
- Datas profissionais: R$ 0,10/mês  
- Check-ins:           R$ 0,10/mês
────────────────────────────────
TOTAL:                 R$ 410,28/mês
Receita (20 clientes): R$ 30.000/mês
Margem:                98.6%
```

**Feature 2**

```
Projuris API:          R$ 0 (incluído)
AWS adicional:         R$ 50/mês
────────────────────────────────
TOTAL INCREMENTAL:     R$ 50/mês
```

**Feature 4 (ML)**

```
EC2 t3.medium (treino): R$ 150/mês
MLflow storage:         R$ 20/mês
────────────────────────────────
TOTAL INCREMENTAL:      R$ 170/mês
```

**Feature 5 (Mobile)**

```
Stripe fees:            3.99% receita
Firebase:               R$ 0 (free tier)
S3 adicional:           R$ 30/mês
────────────────────────────────
TOTAL INCREMENTAL:      R$ 30/mês + %
```

### Segurança e Compliance

**LGPD**

```python
# Criptografia em repouso
DATABASE_URL com SSL: sslmode=require

# Criptografia em trânsito
TLS 1.3 em todas as APIs

# Logs auditáveis
{
  "user_id": 123,
  "action": "visualizar_processo",
  "processo_id": "0001234-56.2024.8.26.0100",
  "timestamp": "2026-02-16T10:30:00Z",
  "ip": "192.168.1.1"
}

# Retenção de dados
Processos arquivados: 5 anos
Logs de acesso: 6 meses
Backups: 3 anos
```

**OAB Compliance**

```python
# Disclaimer obrigatório (primeira interação)
DISCLAIMER = """
Olá! Sou a assistente digital do escritório {escritorio}.
Posso ajudar você a acompanhar seu processo, mas não
substituo a orientação do seu advogado. Para decisões
legais, sempre consulte Dr./Dra. {advogado}.
"""

# Limitações de escopo
PODE_FAZER = [
    "Informar status do processo",
    "Traduzir termos jurídicos",
    "Explicar próximos passos procedimentais",
    "Agendar consultas"
]

NAO_PODE_FAZER = [
    "Dar pareceres jurídicos",
    "Prever resultados",
    "Oferecer estratégias processuais"
]
```

### Monitoramento

**Prometheus Metrics**

```python
from prometheus_client import Counter, Histogram

# Métricas
mensagens_enviadas = Counter('whatsapp_messages_sent', 'Total mensagens')
latencia_ia = Histogram('ia_response_time_seconds', 'Latência respostas IA')
processos_monitorados = Gauge('processos_ativos', 'Processos monitorados')

# Uso
mensagens_enviadas.inc()
with latencia_ia.time():
    resposta = await claude.chat(mensagem)
```

**Grafana Dashboards**

- Uptime: Taxa de disponibilidade por feature
- Performance: P50, P95, P99 latência
- Business: MRR, churn, NPS
- Errors: Taxa de erro por endpoint
- AI: Tokens consumidos, custo por interação

### Deploy

**Docker Build**

```bash
# Feature 1
docker build -t concierge-f1:latest -f infrastructure/docker/Dockerfile.f1 .

# Feature 2
docker build -t concierge-f2:latest -f infrastructure/docker/Dockerfile.f2 .
```

**Kubernetes**

```bash
# Development
kubectl apply -k infrastructure/kubernetes/overlays/dev/

# Production
kubectl apply -k infrastructure/kubernetes/overlays/prod/
```

**Terraform (AWS)**

```bash
cd infrastructure/terraform/environments/prod
terraform init
terraform plan
terraform apply
```

### Checklist Final

**Antes de Começar Desenvolvimento**

- [ ] Criar conta Anthropic Claude (R$ 100 créditos grátis)
- [ ] Configurar Evolution API (WhatsApp)
- [ ] Criar conta Jusbrasil API
- [ ] Setup PostgreSQL local ou Docker
- [ ] Setup Redis local ou Docker
- [ ] Criar conta AWS (Free Tier)
- [ ] Criar projeto Google Cloud Console
- [ ] Ativar Google Sheets API
- [ ] Criar Service Account e baixar credentials.json
- [ ] Criar planilha Google Sheets (3 abas)
- [ ] Ler documentação OAB sobre uso de IA
- [ ] Ler LGPD (Lei 13.709/2018)

**MVP (Feature 1)**

- [ ] Setup projeto (make setup)
- [ ] Implementar orchestrator LangGraph
- [ ] Integrar Claude API
- [ ] Integrar Evolution API (WhatsApp)
- [ ] Integrar Jusbrasil API
- [ ] Integrar Google Sheets API
- [ ] Implementar workers mensagens relacionamento
- [ ] Sistema fact-checking
- [ ] Worker monitoramento Celery
- [ ] Testes unitários + integração
- [ ] Deploy staging
- [ ] Onboarding 3 escritórios beta

---

**Última atualização:** Fevereiro 2026  
**Versão:** 1.0.0
