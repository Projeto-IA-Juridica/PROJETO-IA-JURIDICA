# Roadmap de Implementação — Novas Features

> **Princípio:** aproveitar ao máximo o que já existe. Cada feature usa infra, modelos e rotas já prontas, adicionando apenas o incremento necessário.

---

## Visão Geral da Base Existente

O MVP já entrega:

| Componente | Arquivo/Módulo | Aproveitamento |
|---|---|---|
| Multi-tenancy por escritório | `shared/models/base.py` → `TenantMixin` | Todas as features |
| Banco PostgreSQL async | `shared/database/connection.py` | Features 1, 2, 3, 5 |
| Histórico de interações | `shared/models/interacao.py` | Features 3, 5, 6 |
| Dados judiciais (Jusbrasil + DataJud) | `feature_1_ia_personalizada/services/legal_data/` | Features 2, 3 |
| Orquestrador LangGraph (6 nós) | `feature_1_ia_personalizada/services/ai/orchestrator.py` | Features 3, 6 |
| Claude Client com retry | `feature_1_ia_personalizada/services/ai/claude_client.py` | Features 1, 3, 6 |
| Importação em massa | `feature_1_ia_personalizada/api/routes/admin_import.py` | Feature 4 |
| Celery + filas | `feature_1_ia_personalizada/workers/celery_app.py` | Features 1, 2, 3, 6 |
| WhatsApp (Evolution API) | `feature_1_ia_personalizada/services/messaging/` | Features 4, 6 |
| Métricas Prometheus | `feature_1_ia_personalizada/api/routes/metrics.py` | Feature 5 |
| Modelos `Processo` e `Interacao` | `shared/models/processo.py`, `shared/models/interacao.py` | Features 2, 3, 5 |
| Modelo `Escritorio` | `shared/models/escritorio.py` | Features 4, 5 |

---

## Feature 1 — RAG Jurisprudencial por Escritório

### O que entrega
Cada escritório alimenta sua própria base vetorial com petições, teses e jurisprudência favorável. A IA passa a responder com contexto real do escritório, não genérico. Quanto mais usa, mais diferenciado fica.

### O que já existe e será reaproveitado

- **PostgreSQL já em uso** → adiciona extensão `pgvector` (sem trocar banco)
- **`TenantMixin`** → garante isolamento por `escritorio_id` automaticamente
- **`ClaudeClient`** → gera embeddings (ou usa Voyage AI) sem nova infraestrutura
- **Celery worker `send_notifications.py`** → pipeline de ingestão de PDFs roda como task assíncrona
- **Redis cache (`cache_manager.py`)** → cacheia resultados de busca vetorial frequentes
- **`admin_import.py`** → endpoint de upload de documentos já tem lógica de importação em massa
- **`FactChecker` (`fact_checker.py`)** → valida se o contexto RAG é relevante antes de usar

### Modelo de Dados — Novo

```sql
-- Migração: alembic/versions/003_add_rag_tables.py

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE documentos_rag (
    id          SERIAL PRIMARY KEY,
    escritorio_id INTEGER NOT NULL REFERENCES escritorios(id) ON DELETE CASCADE,
    titulo      VARCHAR(500) NOT NULL,
    tipo        VARCHAR(50)  NOT NULL,  -- 'peticao' | 'sentenca' | 'jurisprudencia' | 'tese'
    conteudo    TEXT         NOT NULL,
    embedding   vector(1536) NOT NULL,  -- Claude/Voyage embeddings
    metadata_json JSONB DEFAULT '{}',   -- tribunal, vara, tipo_acao, data_doc, resultado
    ativo       BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ON documentos_rag USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

CREATE INDEX ON documentos_rag (escritorio_id, tipo, ativo);
```

### Novos Arquivos a Criar

```
feature_1_ia_personalizada/
├── services/
│   └── rag/
│       ├── embeddings.py        # Gera embeddings via Claude/Voyage
│       ├── vector_store.py      # Busca semântica no pgvector
│       ├── ingestion.py         # Pipeline PDF → chunks → embeddings
│       └── retriever.py        # Interface de recuperação para o orchestrator
├── workers/
│   └── ingest_documentos.py     # Task Celery para ingestão assíncrona
└── api/
    └── routes/
        └── rag.py               # POST /rag/upload, GET /rag/documentos, DELETE /rag/{id}
```

### Integração com Orquestrador Existente

No [orchestrator.py](../feature_1_ia_personalizada/services/ai/orchestrator.py), adicionar um nó entre `buscar_dados` e `gerar_resposta`:

```python
# Nó novo: buscar_contexto_rag
async def buscar_contexto_rag(state: ConversationState) -> ConversationState:
    """Busca documentos relevantes do escritório antes de gerar resposta."""
    retriever = RAGRetriever(escritorio_id=state["escritorio_id"])
    docs = await retriever.buscar(query=state["mensagem"], top_k=3)
    state["contexto_rag"] = docs  # Injetado no prompt de geração
    return state
```

O `SYSTEM_PROMPT_STATUS_PROCESSO` em [prompts.py](../feature_1_ia_personalizada/services/ai/prompts.py) recebe um campo `{contexto_escritorio}` com os documentos recuperados.

### Nova Rota de Upload

```python
# Aproveitando lógica de admin_import.py
# POST /rag/upload
# Aceita: PDF, DOCX, TXT
# Processa: extração de texto → chunking → embedding → pgvector
```

### Fluxo de Ingestão (Worker Celery — fila existente `ia`)

```
Upload do arquivo
    └─► Celery task: ingest_documento(arquivo_id, escritorio_id)
            ├─ Extrai texto (PyMuPDF)
            ├─ Chunking: 512 tokens com 50 de overlap
            ├─ Gera embeddings (ClaudeClient ou Voyage)
            └─ Salva em documentos_rag
```

### Dependências Adicionais

```
# requirements-f1.txt
pgvector==0.3.2
PyMuPDF==1.24.0        # Extração de PDF
langchain-text-splitters==0.2.4  # Já no stack LangChain
```

---

## Feature 2 — Score de Risco Processual em Tempo Real

### O que entrega
Substitui o `vitoria_preditor.py` por um score de complexidade/risco que o advogado vê no painel. Cruza dados do DataJud (tempo médio da vara, perfil do juiz, tipo de ação) com histórico do escritório.

### O que já existe e será reaproveitado

- **`vitoria_preditor.py`** → já consulta DataJud e classifica casos similares; apenas refatora a saída
- **`datajud_client.py`** → cliente DataJud já pronto com tratamento de erros e retry
- **`jusbrasil_client.py`** → dados complementares do processo já disponíveis
- **`cache_manager.py`** → score cacheado por 6h no Redis (mesmo padrão já usado)
- **`Processo` model** → adiciona coluna `score_risco` e `score_atualizado_em`
- **`monitor_processos.py`** → worker Celery já roda de 6 em 6h; recalcula score junto
- **`/processos` route** → expõe o score no GET existente sem nova rota

### Migração de Dados — Incremental

```sql
-- alembic/versions/003_add_score_risco.py
ALTER TABLE processos
    ADD COLUMN score_risco       SMALLINT DEFAULT NULL,   -- 0-100
    ADD COLUMN score_componentes JSONB    DEFAULT NULL,   -- detalhamento
    ADD COLUMN score_atualizado_em TIMESTAMPTZ DEFAULT NULL;

CREATE INDEX ON processos (escritorio_id, score_risco)
    WHERE score_risco IS NOT NULL;
```

### Refatoração do `vitoria_preditor.py`

O módulo existente em [vitoria_preditor.py](../feature_1_ia_personalizada/services/legal_data/vitoria_preditor.py) passa a retornar um objeto estruturado em vez de percentuais:

```python
# ANTES (output atual)
{
  "percentual_favoravel_autor": 45.6,
  "casos_analisados": 87,
  "disclaimer": "..."
}

# DEPOIS (novo ScoreRisco)
{
  "score": 67,              # 0-100 (baixo risco = 0, alto risco = 100)
  "nivel": "moderado",      # baixo | moderado | alto | critico
  "componentes": {
    "complexidade_juridica": 70,     # baseado no tipo de ação
    "duracao_estimada_dias": 420,    # média DataJud para essa vara/classe
    "historico_vara": 65,            # % casos similares com desfecho neutro/neg
    "valor_causa_normalizado": 45,   # impacto relativo do valor
    "fase_processual": 30            # risco decresce conforme avança
  },
  "interpretacao": "Processo de duração média estimada em 14 meses. A vara tem histórico de alta carga processual.",
  "disclaimer": "Score de complexidade baseado em dados históricos. Não constitui previsão de resultado."
}
```

### Integração com Worker Existente

Em [monitor_processos.py](../feature_1_ia_personalizada/workers/monitor_processos.py), após cada atualização de andamento:

```python
# Recalcula score junto com a verificação de andamentos (mesma task)
score = await calcular_score_risco(processo, datajud_client)
processo.score_risco = score["score"]
processo.score_componentes = score["componentes"]
processo.score_atualizado_em = datetime.utcnow()
```

### Exposição na API

O GET `/processos/{id}` já existente em [processos.py](../feature_1_ia_personalizada/api/routes/processos.py) passa a incluir:

```json
{
  "id": 1,
  "numero_cnj": "...",
  "status": "ativo",
  "score_risco": 67,
  "score_nivel": "moderado",
  "score_interpretacao": "...",
  "score_atualizado_em": "2026-03-16T10:00:00Z"
}
```

---

## Feature 3 — Resumo Inteligente de Movimentação

### O que entrega
Em vez de "Juntada de petição intercorrente", a IA gera: "O escritório da outra parte enviou um documento ao juiz. Isso é normal nesta fase e seu advogado já foi notificado. Prazo estimado para próximo passo: 15-20 dias." Mantém estado do processo para contexto histórico.

### O que já existe e será reaproveitado

- **`translator.py` + `juridical_translator.py`** → tradução de termos já funciona; agora recebe contexto histórico
- **`memory.py`** → histórico de conversas já no Redis; mesma estrutura guarda estado do processo
- **`monitor_processos.py`** → detecta novos andamentos; é o ponto de entrada natural
- **`interacoes` table** → `metadata_json` já armazena dados flexíveis; guarda o estado do processo
- **`ClaudeClient`** → gera o resumo contextualizado com o mesmo wrapper existente
- **`SYSTEM_PROMPT_STATUS_PROCESSO`** em [prompts.py](../feature_1_ia_personalizada/services/ai/prompts.py) → recebe campo novo `{historico_andamentos}` e `{fase_atual}`
- **`whatsapp.py`** → envia a mensagem contextualizada (sem mudança)

### Modelo de Estado do Processo — Sem Nova Tabela

Aproveitando `metadata_json` do modelo `Interacao` e um novo campo em `Processo`:

```sql
-- alembic/versions/003_add_processo_state.py
ALTER TABLE processos
    ADD COLUMN estado_atual     JSONB DEFAULT NULL,
    ADD COLUMN fase_processual  VARCHAR(100) DEFAULT NULL;
-- Ex: fase_processual = 'instrucao' | 'saneamento' | 'julgamento' | 'recurso' | 'execucao'
```

### Novo Serviço: `ProcessoStateManager`

```
feature_1_ia_personalizada/services/ai/processo_state.py
```

```python
class ProcessoStateManager:
    """
    Mantém e atualiza o estado processual para contexto de resumos.
    Usa o campo processo.estado_atual (JSONB) + histórico de interacoes.
    """

    async def get_state(self, processo_id: int) -> dict:
        """Retorna estado atual: fase, últimos andamentos, próximas expectativas."""
        ...

    async def update_state(self, processo_id: int, novo_andamento: str) -> dict:
        """Atualiza fase com base no novo andamento. Retorna estado atualizado."""
        ...

    async def gerar_contexto_historico(self, processo_id: int, n_ultimos: int = 5) -> str:
        """Formata histórico para injetar no prompt Claude."""
        ...
```

### Integração com `monitor_processos.py` (Worker Existente)

```python
# Em monitor_processos.py — após detectar novo andamento:
state_manager = ProcessoStateManager(db)
estado = await state_manager.update_state(processo.id, novo_andamento)

# Passa estado completo para o tradutor
resumo = await juridical_translator.traduzir_com_contexto(
    andamento=novo_andamento,
    fase_atual=estado["fase"],
    historico=estado["ultimos_andamentos"],
    tipo_acao=processo.tipo_acao,
    polo_cliente=processo.polo_cliente
)

# O resumo vai para o WhatsApp pelo canal já existente
```

### Novo Prompt em `prompts.py`

```python
SYSTEM_PROMPT_ANDAMENTO_CONTEXTUALIZADO = """
Você é o assistente jurídico do escritório {nome_escritorio}.

CONTEXTO DO PROCESSO:
- Tipo de ação: {tipo_acao}
- Fase atual: {fase_processual}
- Cliente é: {polo_cliente} (autor/réu)
- Últimos andamentos: {historico_andamentos}

NOVO ANDAMENTO:
{novo_andamento}

TAREFA:
Explique este andamento em linguagem simples, considerando:
1. O que aconteceu
2. Por que é normal (ou não) nesta fase
3. O que o cliente deve esperar a seguir (prazo estimado)
4. Se o cliente precisa fazer algo

REGRAS OAB: Não emita parecer jurídico. Não preveja resultado.
Sempre mencione que o advogado responsável já foi notificado.
"""
```

---

## Feature 4 — Módulo de Onboarding Automatizado do Escritório

### O que entrega
Escritório se cadastra, importa processos via CSV/integração, configura persona da IA, e em 30 minutos está operando. Transforma o produto de "serviço consultivo" para "produto escalável".

### O que já existe e será reaproveitado

- **`admin_import.py`** → importação em massa de clientes/processos já implementada; estende com fluxo guiado
- **`escritorio.py` model** → já tem `webhook_whatsapp_instance`, `plano`, `max_processos`; adiciona campos de persona
- **`usuario.py` model** → criação de usuário admin do escritório já existe
- **`evolution_client.py`** → configuração da instância WhatsApp já no código
- **`auth.py` routes** → login/registro já funciona; adiciona endpoint de registro self-service
- **`templates.py`** (messaging) → templates de mensagem já existem; adiciona mecanismo de customização
- **`validators.py`** → validação de CNPJ já implementada
- **`disclaimers.json`** → textos OAB já prontos para incluir nos templates

### Novos Campos no Modelo `Escritorio`

```sql
-- alembic/versions/004_add_onboarding_fields.py
ALTER TABLE escritorios
    ADD COLUMN persona_nome          VARCHAR(100) DEFAULT 'Assistente Jurídico',
    ADD COLUMN persona_tom           VARCHAR(50)  DEFAULT 'formal',  -- formal | amigavel | neutro
    ADD COLUMN horario_inicio        TIME         DEFAULT '08:00',
    ADD COLUMN horario_fim           TIME         DEFAULT '18:00',
    ADD COLUMN onboarding_etapa      SMALLINT     DEFAULT 0,  -- 0-5 (funil)
    ADD COLUMN onboarding_completo   BOOLEAN      DEFAULT FALSE,
    ADD COLUMN onboarding_at         TIMESTAMPTZ  DEFAULT NULL,
    ADD COLUMN template_boas_vindas  TEXT         DEFAULT NULL,
    ADD COLUMN template_atualizacao  TEXT         DEFAULT NULL;
```

### Novas Rotas de Onboarding

```
feature_1_ia_personalizada/api/routes/onboarding.py
```

```
POST /onboarding/register         → Cria escritório + usuário admin
POST /onboarding/configure-ia     → Salva persona (nome, tom, horários)
POST /onboarding/import-processos → Importa CSV (reusa admin_import.py)
POST /onboarding/connect-whatsapp → Cria instância Evolution API
GET  /onboarding/status           → Etapa atual + checklist
POST /onboarding/complete         → Marca onboarding como concluído
```

### Fluxo de Onboarding (5 Etapas)

```
Etapa 0: Registro
    ├─ POST /onboarding/register
    ├─ Cria escritório (CNPJ validado por validators.py)
    └─ Cria usuário admin + envia email de boas-vindas

Etapa 1: Configuração da IA
    ├─ POST /onboarding/configure-ia
    ├─ Nome da IA, tom, horários de atendimento
    └─ Preview de como a IA vai se apresentar

Etapa 2: Importação de Processos
    ├─ POST /onboarding/import-processos (reusa admin_import.py)
    ├─ CSV com colunas: cpf_cliente, numero_cnj, tipo_acao, advogado_email
    └─ Valida CNJs (validators.py), cria clientes e processos

Etapa 3: Conexão WhatsApp
    ├─ POST /onboarding/connect-whatsapp
    ├─ Chama evolution_client.py para criar instância
    └─ Retorna QR Code para escanear

Etapa 4: Templates de Mensagem
    ├─ Seleção de templates pré-aprovados OAB (disclaimers.json)
    └─ Customização de tom (usa persona configurada)

Etapa 5: Go Live
    ├─ Ativa monitoramento dos processos (monitoramento_ativo = True)
    ├─ Envia mensagem de boas-vindas para todos os clientes
    └─ Marca onboarding_completo = True
```

### Templates Pré-Aprovados (OAB)

Adicionar em [disclaimers.json](../feature_1_ia_personalizada/data/knowledge_base/disclaimers.json):

```json
{
  "templates_onboarding": {
    "boas_vindas": "Olá {nome_cliente}! Sou {persona_nome}, assistente digital do {nome_escritorio}. Estou aqui para mantê-lo informado sobre seu processo de forma clara e objetiva. Para dúvidas jurídicas específicas, seu advogado {nome_advogado} está sempre disponível.",
    "primeira_atualizacao": "Olá {nome_cliente}! Há novidades no seu processo. {resumo_andamento} Precisa de mais informações? Pode me perguntar aqui.",
    "sem_novidades": "Olá {nome_cliente}! Verifiquei seu processo hoje e não há novidades desde nossa última conversa. Avisarei assim que houver alguma movimentação."
  }
}
```

---

## Feature 5 — Analytics de Satisfação e Retenção

### O que entrega
Dashboard para o escritório mostrando: NPS por cliente, tempo de resposta antes/depois da IA, interações evitadas (ligações/emails), horas economizadas. Torna o churn improvável.

### O que já existe e será reaproveitado

- **`interacoes` table** → já armazena `tokens_input/output`, `custo_estimado`, `tempo_resposta_ms`, `satisfacao` (NPS 1-5), `created_at` — é a fonte de verdade
- **`/chat/stats/dashboard`** route → já existe com totais básicos; expande sem nova rota
- **Prometheus metrics** → `ia_response_time_seconds`, `ia_tokens_consumed_total` já coletados
- **`metadata_json` em Interacao** → guarda dados flexíveis (tipo de mensagem, canal)
- **`TenantMixin`** → todos os dados já isolados por `escritorio_id`
- **`interacao.py` model** → apenas adiciona índices para queries de analytics

### Novos Índices (Sem Mudança de Schema)

```sql
-- alembic/versions/005_add_analytics_indexes.py
CREATE INDEX ON interacoes (escritorio_id, created_at DESC);
CREATE INDEX ON interacoes (escritorio_id, satisfacao) WHERE satisfacao IS NOT NULL;
CREATE INDEX ON interacoes (escritorio_id, direcao, created_at);
CREATE INDEX ON interacoes (cliente_id, created_at DESC);
```

### Expansão do Dashboard Existente

Rota já existente em [chat.py](../feature_1_ia_personalizada/api/routes/chat.py) — `GET /chat/stats/dashboard` — passa a retornar:

```json
{
  "periodo": "2026-02-16 a 2026-03-16",
  "resumo": {
    "total_interacoes": 1234,
    "clientes_ativos": 89,
    "nps_medio": 8.1,
    "nps_anterior": 6.2,
    "variacao_nps": "+1.9"
  },
  "eficiencia": {
    "tempo_resposta_medio_ms": 1840,
    "interacoes_sem_humano": 1105,
    "percentual_autonomia": 89.5,
    "horas_economizadas_estimadas": 47.2,
    "custo_total_usd": 12.34
  },
  "por_cliente": [
    {
      "cliente_id": 1,
      "nome": "João Silva",
      "nps": 9,
      "interacoes": 23,
      "ultimo_contato": "2026-03-15"
    }
  ],
  "tendencia_semanal": [
    { "semana": "2026-W10", "interacoes": 287, "nps_medio": 7.8 },
    { "semana": "2026-W11", "interacoes": 312, "nps_medio": 8.3 }
  ]
}
```

### Cálculo de Horas Economizadas

```python
# Lógica simples baseada nos dados já existentes
MINUTOS_POR_INTERACAO = 8  # benchmark: responder WhatsApp/email manualmente

horas = (interacoes_sem_humano * MINUTOS_POR_INTERACAO) / 60
```

### Coleta de NPS — Via WhatsApp Existente

No [mensagens_relacionamento.py](../feature_1_ia_personalizada/workers/mensagens_relacionamento.py) (worker já existente), adicionar envio periódico de pesquisa NPS:

```python
# Task nova: solicitar_nps_cliente
# Disparada 7 dias após cada movimentação significativa
# Mensagem: "De 1 a 5, como avalia o atendimento do {nome_escritorio}?"
# Resposta capturada no webhook → salva em interacao.satisfacao
```

### Novo Serviço de Analytics

```
feature_1_ia_personalizada/services/analytics/
├── calculadora.py    # Queries SQL para métricas (usa session já configurada)
└── exportador.py     # Gera PDF/CSV do relatório mensal
```

---

## Feature 6 — Modo "Advogado no Loop" com Escalação Inteligente

### O que entrega
IA detecta perguntas fora do escopo permitido e escala para o advogado com: resumo da conversa + pergunta do cliente + sugestão de resposta para aprovação em 2 cliques pelo WhatsApp.

### O que já existe e será reaproveitado

- **Orquestrador LangGraph** → adiciona nó `avaliar_escalacao` antes de `gerar_resposta`
- **`ClaudeClient`** → gera o resumo da conversa + sugestão de resposta para o advogado
- **`memory.py`** → histórico da conversa já está no Redis; usado para montar o contexto de escalação
- **`evolution_client.py`** → envia a notificação para o WhatsApp do advogado (mesmo cliente já usa)
- **`usuarios` table** → já tem `telefone` do advogado; apenas adiciona `whatsapp_numero`
- **`interacoes` table** → `metadata_json` guarda estado da escalação (pendente/aprovado/rejeitado)
- **`disclaimers.json`** → lista de triggers OAB já documentados; vira `ESCALATION_TRIGGERS`

### Novo Campo em `Usuario`

```sql
-- alembic/versions/006_add_usuario_whatsapp.py
ALTER TABLE usuarios
    ADD COLUMN whatsapp_numero VARCHAR(20) DEFAULT NULL,
    ADD COLUMN escalacao_ativa BOOLEAN DEFAULT TRUE;
```

### Novo Nó no Orquestrador Existente

Em [orchestrator.py](../feature_1_ia_personalizada/services/ai/orchestrator.py), adicionar entre `classificar_intencao` e `gerar_resposta`:

```python
async def avaliar_escalacao(state: ConversationState) -> ConversationState:
    """
    Avalia se a mensagem requer escalação para o advogado.
    Usa a classificação de intenção já feita no nó anterior.
    """
    intencao = state["intencao"]

    ESCALACAO_OBRIGATORIA = [
        "parecer_juridico",
        "estrategia_processual",
        "negociacao",
        "decisao_judicial_impacto_alto"
    ]

    if intencao in ESCALACAO_OBRIGATORIA:
        state["requer_escalacao"] = True
        state["motivo_escalacao"] = intencao

    return state
```

### Serviço de Escalação

```
feature_1_ia_personalizada/services/escalacao/
├── detector.py      # Detecta necessidade de escalação
├── contexto.py      # Monta resumo da conversa + sugestão de resposta
└── notificador.py   # Envia para WhatsApp do advogado via evolution_client.py
```

### Fluxo de Escalação

```
Cliente pergunta algo além do escopo
    │
    ▼
[nó: avaliar_escalacao]
    │ requer_escalacao = True
    ▼
[nó: preparar_escalacao]  ← NOVO
    ├─ Gera resumo da conversa (ClaudeClient — já existente)
    ├─ Monta mensagem para advogado:
    │      "📋 ESCALAÇÃO NECESSÁRIA
    │       Cliente: João Silva
    │       Processo: 0001234-12.2024.8.26.0001
    │       Pergunta: [pergunta do cliente]
    │
    │       Contexto: [resumo últimas 5 mensagens]
    │
    │       Sugestão de resposta:
    │       [texto gerado pelo Claude]
    │
    │       ✅ Aprovar e enviar  |  ✏️ Editar  |  ❌ Rejeitar"
    │
    ├─ Envia para WhatsApp do advogado (evolution_client.py)
    ├─ Salva escalacao em interacao.metadata_json:
    │      {"escalacao": {"status": "pendente", "advogado_id": 5, "ts": "..."}}
    └─ Responde ao cliente: "Sua pergunta foi encaminhada ao seu advogado. Retorno em breve."
```

### Captura da Resposta do Advogado

No [webhook_whatsapp.py](../feature_1_ia_personalizada/api/routes/webhook_whatsapp.py), detectar respostas do advogado com botões de aprovação:

```python
# Detecta se remetente é advogado (por telefone)
# Se sim, verifica metadata_json da interação pendente
# Ações: aprovar (envia resposta ao cliente), editar, rejeitar
```

### SLA de Escalação

No [mensagens_relacionamento.py](../feature_1_ia_personalizada/workers/mensagens_relacionamento.py) (worker existente), adicionar:

```python
# Task: verificar_escalacoes_pendentes (a cada 30 min)
# Se escalação > 2h sem resposta → lembrete para advogado
# Se escalação > 24h → alerta para admin do escritório
```

---

## Feature 3 — Prospecção Inteligente (Redesenhada)

### O que entrega
Motor de captação de clientes para advogados. O sistema analisa o histórico de processos do escritório para identificar em quais áreas e tipos de empresa ele se destaca, depois cruza com dados de empresas-alvo (processos públicos + dados da Receita Federal + funcionários via LinkedIn API) e gera uma fila de leads qualificados e pontuados. O advogado vê: "Empresa X tem 3 processos trabalhistas em aberto, a funcionária Y (cargo: Diretora de RH) trabalha lá — seu escritório vence 78% dos casos trabalhistas neste setor."

### Problema que resolve
Advogados prospectam de forma aleatória. Não sabem onde têm vantagem competitiva, não conectam o histórico de vitórias com oportunidades de mercado. Esta feature transforma os dados que já estão no banco em inteligência comercial.

### O que já existe e será reaproveitado

- **`processos` + `interacoes` tables** → fonte de verdade do histórico do escritório — taxa de sucesso, tipos de causa, setores de clientes
- **`datajud_client.py`** → busca processos públicos das empresas-alvo por CNPJ (já integrado)
- **`jusbrasil_client.py`** → complementa com dados processuais das empresas (já integrado)
- **`cache_manager.py`** → cacheia perfis de empresa (Receita Federal) e resultados LinkedIn por CNPJ
- **`claude_client.py`** → gera análise narrativa do DNA do advogado e justificativa de cada lead
- **`TenantMixin`** → isolamento por `escritorio_id` automático
- **`crm/aggregator.py`** → lógica de agregação de dados por cliente reaproveitável para empresa-alvo

### Modelo de Dados — Novos

```sql
-- alembic/versions/011_add_prospeccao.py

-- Perfil de especialidade do escritório (calculado periodicamente)
CREATE TABLE dna_escritorio (
    id              SERIAL PRIMARY KEY,
    escritorio_id   INTEGER NOT NULL REFERENCES escritorios(id) ON DELETE CASCADE,
    area_juridica   VARCHAR(100) NOT NULL,   -- 'trabalhista' | 'civil' | 'consumidor' | etc.
    setor_empresa   VARCHAR(100),            -- 'varejo' | 'saude' | 'tech' | etc.
    total_processos INTEGER DEFAULT 0,
    taxa_sucesso    NUMERIC(5,2),            -- 0-100
    ticket_medio    NUMERIC(10,2),
    atualizado_em   TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (escritorio_id, area_juridica, setor_empresa)
);

-- Empresas monitoradas para prospecção
CREATE TABLE empresas_prospeccao (
    id              SERIAL PRIMARY KEY,
    escritorio_id   INTEGER NOT NULL REFERENCES escritorios(id) ON DELETE CASCADE,
    cnpj            VARCHAR(18) NOT NULL,
    razao_social    VARCHAR(500),
    setor           VARCHAR(100),
    porte           VARCHAR(50),             -- 'MEI' | 'ME' | 'EPP' | 'MEDIO' | 'GRANDE'
    dados_receita   JSONB DEFAULT '{}',      -- dados brutos da Receita Federal
    processos_ativos INTEGER DEFAULT 0,
    score_match     SMALLINT DEFAULT 0,      -- 0-100: afinidade com o escritório
    score_motivo    TEXT,                    -- explicação gerada pelo Claude
    status          VARCHAR(50) DEFAULT 'identificada',  -- identificada | qualificada | abordada | convertida
    criado_em       TIMESTAMPTZ DEFAULT NOW(),
    atualizado_em   TIMESTAMPTZ DEFAULT NOW()
);

-- Leads individuais (funcionário de empresa-alvo)
CREATE TABLE leads_prospeccao (
    id              SERIAL PRIMARY KEY,
    escritorio_id   INTEGER NOT NULL REFERENCES escritorios(id) ON DELETE CASCADE,
    empresa_id      INTEGER NOT NULL REFERENCES empresas_prospeccao(id) ON DELETE CASCADE,
    nome            VARCHAR(255),
    cargo           VARCHAR(255),
    linkedin_url    VARCHAR(500),
    linkedin_id     VARCHAR(100),            -- ID LinkedIn para deduplicação
    area_atuacao    VARCHAR(100),            -- ex: 'RH', 'Jurídico', 'Financeiro'
    relevancia      VARCHAR(50),             -- 'alta' | 'media' | 'baixa'
    motivo          TEXT,                    -- ex: "Diretora de RH em empresa com 5 processos trabalhistas"
    status          VARCHAR(50) DEFAULT 'novo',  -- novo | visualizado | contatado | descartado
    criado_em       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ON dna_escritorio (escritorio_id, taxa_sucesso DESC);
CREATE INDEX ON empresas_prospeccao (escritorio_id, score_match DESC, status);
CREATE INDEX ON leads_prospeccao (escritorio_id, empresa_id, relevancia);
```

### Arquitetura de Serviços — Novos

```
feature_1_ia_personalizada/services/prospeccao/
│
├── dna_analyzer.py          # Calcula especialidades do escritório a partir dos processos
├── empresa_intel.py         # Busca dados de empresa: Receita Federal + DataJud
├── linkedin_client.py       # Wrapper LinkedIn API (People Search / Company Employees)
├── lead_scorer.py           # Score de afinidade escritório × empresa × funcionário
└── prospeccao_pipeline.py   # Orquestra o fluxo completo
```

### Fluxo Completo

```
1. ANÁLISE DE DNA (roda 1x/semana via Celery Beat)
   ────────────────────────────────────────────────
   Worker: calcular_dna_escritorio(escritorio_id)
       ├─ Query: processos por área jurídica + setor do cliente
       ├─ Calcula taxa_sucesso por combinação (área × setor)
       ├─ Gera análise narrativa via Claude: "Seu escritório vence 78% dos casos
       │   trabalhistas no setor de varejo com 3+ funcionários..."
       └─ Salva em dna_escritorio

2. ANÁLISE DE EMPRESA-ALVO (sob demanda ou em lote)
   ────────────────────────────────────────────────
   POST /prospeccao/empresa  { cnpj: "..." }
       ├─ Receita Federal API → razão social, porte, CNAE (setor), sócios
       ├─ DataJud → processos ativos da empresa por área jurídica
       ├─ Calcula score_match: sobreposição entre áreas dos processos e DNA do escritório
       ├─ Claude gera score_motivo: "Alta afinidade: empresa tem 4 processos trabalhistas
       │   ativos e seu escritório tem taxa de 78% em casos similares no varejo."
       └─ Salva em empresas_prospeccao

3. ENRIQUECIMENTO COM LINKEDIN (por empresa qualificada)
   ────────────────────────────────────────────────────
   Worker: enriquecer_empresa_linkedin(empresa_id)
       ├─ LinkedIn API: busca funcionários da empresa por CNPJ/nome
       ├─ Filtra por cargos relevantes (RH, Jurídico, Financeiro, Diretoria)
       ├─ Para cada pessoa: avalia relevância com base nos processos da empresa
       │      ex: processos trabalhistas → Diretora de RH = alta relevância
       └─ Salva em leads_prospeccao com motivo gerado

4. PIPELINE DE PROSPECÇÃO (interface do advogado)
   ────────────────────────────────────────────────
   GET /prospeccao/leads?status=novo&relevancia=alta
       └─ Retorna leads ranqueados com: nome, cargo, empresa, motivo, score
```

### Novas Rotas

```
POST   /prospeccao/empresa                → Analisa empresa por CNPJ
GET    /prospeccao/empresas               → Lista empresas monitoradas (com score)
GET    /prospeccao/leads                  → Lista leads (filtros: status, relevância, área)
PATCH  /prospeccao/leads/{id}/status      → Atualiza status do lead (visualizado/contatado/descartado)
GET    /prospeccao/dna                    → Perfil de especialidade do escritório
POST   /prospeccao/dna/recalcular         → Força recálculo do DNA
```

### Dependências Adicionais

```
# requests para Receita Federal (síncrono, simples)
# LinkedIn API SDK — ou httpx (já no projeto)
# Nenhuma nova dependência crítica
```

### Integração com LinkedIn API

```python
# linkedin_client.py
# Endpoint: GET /v2/search/blended?q=companiesV2&...
# Requer: LinkedIn Partner Program (aprovação necessária)
# Escopo: r_liteprofile, r_emailaddress, w_member_social

# Alternativa sem aprovação imediata:
# - Usar apenas dados da Receita Federal (sócios/representantes)
# - DataJud traz CPF/nome das partes → algumas são pessoas físicas = funcionários
# - Enriquecer com LinkedIn manualmente via URL fornecida pelo advogado
```

### Workaround para LinkedIn API Restrita

Enquanto a aprovação do LinkedIn Partner Program não chega, o fluxo funciona sem LinkedIn:
- **Receita Federal** traz sócios e representantes legais da empresa
- **DataJud** traz partes dos processos (pessoas físicas que processaram ou foram processadas pela empresa)
- O advogado pode adicionar manualmente o perfil LinkedIn de um lead (campo `linkedin_url`)
- Quando a aprovação chegar, o enriquecimento automático é ligado via feature flag

### Worker de Manutenção

```
workers/prospeccao_worker.py

Tasks:
  calcular_dna_escritorio     → 1x/semana por escritório ativo
  enriquecer_empresa_linkedin → sob demanda após empresa ser qualificada
  atualizar_processos_empresa → 1x/semana, atualiza contagem via DataJud
```

---

## Ordem de Implementação Recomendada

```
Sprint 1 (1-2 semanas)
├── Feature 3: Resumo Inteligente (menor risco, maior impacto imediato)
│   ├── processo_state.py
│   ├── Novo prompt em prompts.py
│   └── Integração com monitor_processos.py
│
└── Feature 2: Score de Risco (refatora vitoria_preditor.py — já existe)
    ├── Migração SQL (nova coluna em processos)
    └── Cálculo no worker existente

Sprint 2 (2-3 semanas)
├── Feature 5: Analytics (quase tudo já existe nos dados)
│   ├── Índices SQL
│   ├── Expansão do /chat/stats/dashboard
│   └── NPS via WhatsApp
│
└── Feature 6: Advogado no Loop
    ├── Novo nó no orquestrador
    ├── Serviço de escalação
    └── Webhook de resposta do advogado

Sprint 3 (3-4 semanas)
├── Feature 1: RAG Jurisprudencial
│   ├── Migração pgvector
│   ├── Pipeline de ingestão
│   └── Integração no orquestrador
│
└── Feature 4: Onboarding Automatizado
    ├── Novos campos em escritorios
    ├── Rotas de onboarding
    └── Fluxo de configuração WhatsApp
```

---

## Dependências Adicionais por Feature

| Feature | Novas Dependências | Justificativa |
|---|---|---|
| 1 (RAG) | `pgvector==0.3.2`, `PyMuPDF==1.24.0` | Extensão PostgreSQL + extração PDF |
| 2 (Score) | Nenhuma | Reusa `datajud_client.py` |
| 3 (Resumo) | Nenhuma | Reusa Claude + tradutor existentes |
| 4 (Onboarding) | Nenhuma | Reusa toda a stack |
| 5 (Analytics) | `reportlab==4.1.0` (opcional) | Geração de PDF de relatório |
| 6 (Loop) | Nenhuma | Reusa orchestrator + WhatsApp |

---

## Checklist de Qualidade (Para Cada Feature)

Seguindo os padrões já estabelecidos no projeto:

- [ ] Migração Alembic criada em `alembic/versions/`
- [ ] Testes unitários em `feature_1_ia_personalizada/tests/unit/`
- [ ] Testes de integração em `feature_1_ia_personalizada/tests/integration/`
- [ ] Métricas Prometheus adicionadas (padrão `ia_*` ou `whatsapp_*`)
- [ ] Logs estruturados com `structlog` (padrão existente)
- [ ] Isolamento por `escritorio_id` verificado
- [ ] Dados sensíveis não expostos nos logs (padrão LGPD existente)
- [ ] Disclaimer OAB incluído onde aplicável
