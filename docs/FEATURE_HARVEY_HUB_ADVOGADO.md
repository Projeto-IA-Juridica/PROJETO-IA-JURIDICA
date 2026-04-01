# Feature: Hub do Advogado (Harvey AI + Canal WhatsApp Exclusivo)

> **Conceito central:** Criar um ecossistema de IA dual onde o cliente interage com Claude (fluido, conversacional) e o advogado tem um canal próprio no WhatsApp alimentado por Harvey AI (especializado em raciocínio jurídico pesado). Um roteador de confiança decide quando escalar Claude → Harvey no fluxo do cliente.

---

## 1. Contexto e Motivação

### O Problema

Claude é excelente para conversação fluida e explicações acessíveis ao cliente leigo, mas apresenta limitações em tarefas jurídicas de alta complexidade:

- Análise aprofundada de petições (estrutura, fundamentação, falhas)
- Pesquisa de jurisprudência com citação precisa
- Perguntas técnicas do advogado que exigem raciocínio jurídico denso
- Respostas com alto risco de alucinação factual (CLT, CPC, jurisprudências)

### A Solução

Duas frentes paralelas que se complementam:

| Canal | Usuário | IA Principal | Fallback | Casos de Uso |
|---|---|---|---|---|
| WhatsApp (já existente) | Cliente | Claude | Harvey (score baixo) | Status de processo, esclarecimentos, NPS |
| WhatsApp (novo) | Advogado | Harvey | Claude (fallback) | Análise jurídica, insights, dúvidas técnicas |

### Por Que Harvey

- API disponível (diferente da maioria dos modelos legais)
- Especializado em direito americano E brasileiro (via fine-tuning)
- Resultados mais confiáveis em raciocínio jurídico denso
- Fecha o ecossistema: cliente usa Claude, advogado usa Harvey, ambos alimentados pelo mesmo banco de dados do escritório

---

## 2. Arquitetura Geral da Feature

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          ECOSSISTEMA DE IA                              │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    CANAL DO CLIENTE (existente)                   │   │
│  │                                                                   │   │
│  │  Cliente → WhatsApp → Orchestrator (LangGraph)                   │   │
│  │                              │                                   │   │
│  │                    ┌─────────▼──────────┐                        │   │
│  │                    │  Roteador de        │                        │   │
│  │                    │  Confiança (NOVO)   │                        │   │
│  │                    └────┬──────────┬─────┘                        │   │
│  │                         │          │                              │   │
│  │               score≥0.7 │          │ score<0.7                   │   │
│  │                         ▼          ▼                              │   │
│  │                      Claude      Harvey                           │   │
│  │                     (fluido)   (preciso)                         │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    CANAL DO ADVOGADO (NOVO)                       │   │
│  │                                                                   │   │
│  │  Advogado → WhatsApp → Hub do Advogado (Celery task)             │   │
│  │                              │                                   │   │
│  │                    ┌─────────▼──────────┐                        │   │
│  │                    │  Classificador de   │                        │   │
│  │                    │  Intenção Jurídica  │                        │   │
│  │                    └──────────┬──────────┘                        │   │
│  │                               │                                   │   │
│  │      ┌────────────┬───────────┼──────────────┬────────────────┐  │   │
│  │      ▼            ▼           ▼               ▼                ▼  │   │
│  │  Análise      Pesquisa    Resumo de        Insight         Pergunta│  │
│  │  Petição      Jurisprud.  Processo         CRM             Jurídica│  │
│  │      │            │           │               │                │  │   │
│  │      └────────────┴─────Harvey AI─────────────┘                │  │   │
│  │                                              Claude (fallback)  │  │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │              BASE DE CONHECIMENTO COMPARTILHADA                   │   │
│  │   pgvector (RAG) | Redis (cache) | PostgreSQL (dados) | Celery   │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Componente 1 — Roteador de Confiança (Claude → Harvey)

### 3.1 O Que É

Módulo que avalia a confiança da resposta do Claude antes de enviá-la ao cliente. Se o score estiver abaixo do threshold, a mesma pergunta é enviada ao Harvey, que produz uma resposta mais confiável.

### 3.2 Quando Rotear para Harvey

O roteador ativa quando **qualquer uma** das condições abaixo é verdadeira:

| Condição | Threshold | Razão |
|---|---|---|
| Score de confiança semântica | < 0.70 | Claude incerto sobre o conteúdo |
| Intenção classificada como "jurídica_complexa" | sempre | Ex: análise de recurso, citação de lei |
| Hallucination score (fact_checker) | > 0.30 | Resposta contradiz dados reais |
| Número de tentativas de geração | > 1 | Claude não convergiu na resposta |
| Pergunta contém termos de alta especificidade | — | CPC art. X, STJ, STF, Súmula N |

### 3.3 Como Calcular o Score de Confiança

O score é composto por 4 dimensões determinísticas (sem chamar IA extra):

```
score_final = (
    0.35 × score_cobertura_rag    # Quão bem o RAG cobriu a pergunta
  + 0.25 × score_fact_checker     # Validação contra dados reais
  + 0.25 × score_intencao         # Clareza da intenção classificada
  + 0.15 × score_historico_cliente # Quantas perguntas similares foram bem respondidas
)
```

**Cálculo de cada componente:**

- **score_cobertura_rag:** max(similaridade_coseno) dos documentos recuperados. Se RAGRetriever retornou 0 documentos → score = 0.
- **score_fact_checker:** já existe em `fact_checker.py`. Reaproveitado diretamente.
- **score_intencao:** mapeado a partir do `tipo_intencao` classificado pelo LangGraph:
  - `status_processo` → 0.90 (alta confiança, dado estruturado)
  - `saudacao` → 1.0
  - `reclamacao` → 0.75
  - `pergunta_juridica` → 0.45 (baixa, propenso à alucinação)
  - `perspectiva_caso` → 0.30 (muito baixa, opinião jurídica = Harvey)
- **score_historico_cliente:** razão entre respostas bem avaliadas (NPS ≥ 4) nas últimas 20 interações.

### 3.4 Arquivo a Criar

**`feature_1_ia_personalizada/services/ai/confidence_router.py`**

```python
# Estrutura do módulo (pseudocódigo de implementação)

@dataclass
class ConfidenceScore:
    valor: float                    # 0.0 → 1.0
    componentes: dict               # Breakdown por dimensão
    deve_escalar_harvey: bool       # True se < threshold
    motivo: str                     # Log interno


class ConfidenceRouter:
    THRESHOLD = 0.70

    async def avaliar(
        self,
        mensagem: str,
        resposta_claude: str,
        tipo_intencao: str,
        rag_docs: list,
        fact_check_result: dict,
        historico_cliente: list[Interacao],
        escritorio_id: int,
    ) -> ConfidenceScore:
        ...

    async def rotear(
        self,
        state: ConversationState,
        score: ConfidenceScore,
    ) -> str:
        """Retorna 'claude' ou 'harvey' baseado no score."""
        ...
```

### 3.5 Integração no Orchestrator Existente

O `orchestrator.py` já tem os nós `gerar_resposta` e `verificar_resposta`. Adicionar um novo nó entre eles:

```
classificar_intencao
      ↓
buscar_dados
      ↓
gerar_resposta  (Claude)
      ↓
[NOVO] avaliar_confianca          ← novo nó
      ↓ score≥0.7       ↓ score<0.7
verificar_resposta    [NOVO] gerar_resposta_harvey
      ↓                       ↓
enviar_resposta ←──────────────┘
```

Isso aproveita 100% do LangGraph existente, apenas adicionando 2 nós.

---

## 4. Componente 2 — Harvey Client

### 4.1 Arquivo a Criar

**`feature_1_ia_personalizada/services/ai/harvey_client.py`**

Seguir o mesmo padrão de `claude_client.py` para consistência:

```python
# Estrutura espelhada no claude_client.py existente

class HarveyClient:
    """
    Wrapper async para a API do Harvey AI.
    Espelha a interface do ClaudeClient para facilitar o roteamento.
    """
    
    # Constantes (alinhar com constants.py)
    MODELO_HARVEY = "harvey-v3"           # confirmar com documentação Harvey
    MAX_TOKENS = 2048                     # Harvey suporta respostas mais longas
    TIMEOUT = 45                          # Harvey é mais lento (raciocínio denso)
    MAX_RETRIES = 3
    
    async def gerar_resposta(
        self,
        system_prompt: str,
        mensagem_usuario: str,
        contexto_rag: list[str] | None = None,
        escritorio_id: int | None = None,
    ) -> HarveyResponse:
        """
        Chama a API Harvey com retry + backoff.
        Retorna resposta tipada com tokens consumidos + custo.
        """
        ...
    
    async def analisar_peticao(
        self,
        conteudo_peticao: str,
        tipo_analise: TipoAnaliseHarvey,
        contexto_processo: dict | None = None,
    ) -> AnaliseHarveyResponse:
        """
        Endpoint especializado para análise de petições.
        Harvey tem endpoint dedicado para documentos jurídicos.
        """
        ...
    
    async def pesquisar_jurisprudencia(
        self,
        query: str,
        tribunal: str | None = None,
        periodo: str | None = None,
    ) -> list[Jurisprudencia]:
        """
        Pesquisa jurisprudência via Harvey.
        Harvey tem acesso a base de dados jurídica própria.
        """
        ...
```

### 4.2 Variáveis de Ambiente Necessárias

Adicionar em `shared/config/settings.py`:

```python
# Harvey AI
HARVEY_API_KEY: str = ""
HARVEY_API_URL: str = "https://api.harvey.ai/v1"  # Confirmar endpoint oficial
HARVEY_MODELO: str = "harvey-v3"
HARVEY_TIMEOUT: int = 45
HARVEY_HABILITADO: bool = False  # Feature flag — ativa por escritório
```

### 4.3 Custo e Métricas

O `Interacao` model já tem `custo_estimado` e `tokens_input/output`. Adicionar campo `modelo_ia` para rastrear qual modelo respondeu:

```sql
-- Migração: alembic/versions/XXX_add_modelo_ia_to_interacoes.py
ALTER TABLE interacoes ADD COLUMN modelo_ia VARCHAR(50) DEFAULT 'claude';
-- Valores: 'claude', 'harvey', 'claude_harvey_fallback'
```

---

## 5. Componente 3 — Hub do Advogado (Canal WhatsApp Exclusivo)

### 5.1 O Que É

Um número de WhatsApp separado (ou instância Evolution API separada) dedicado ao advogado. Diferente do canal do cliente (fluido, proativo), este canal é **reativo e especializado**:

- Advogado envia mensagem → Harvey processa → responde com análise densa
- Sem persona, sem linguagem acessível — responde como colega jurista
- Acessa toda a base de dados do escritório (processos, clientes, documentos RAG)
- **Não envia mensagens proativas** (sem marketing, sem NPS)

### 5.2 Intenções Suportadas

| Intenção | Comando Natural | Processamento | Exemplo |
|---|---|---|---|
| `resumo_processo` | "Resumo do proc. 1234567" | Jusbrasil + Harvey | "Me dá um resumo do processo do João Silva" |
| `analise_peticao` | Envia PDF | Harvey Document API | Envia petição PDF pelo WhatsApp |
| `pesquisa_jurisprudencia` | "Juris sobre..." | Harvey Search | "Busca jurisprudência STJ sobre prescrição intercorrente" |
| `insight_cliente` | "Insight do cliente X" | CRM + Harvey | "Que ação devo tomar com a Maria?" |
| `duvida_juridica` | Pergunta aberta | Harvey Chat | "No CPC art 485 inciso VI..." |
| `status_escritorio` | "Status" ou "Dashboard" | Dashboard formatado | Resumo do dia: X atendimentos, Y processos |
| `rascunho_mensagem` | "Escreve mensagem para X" | Harvey + Claude | Gera mensagem para advogado enviar ao cliente |

### 5.3 Fluxo Técnico de uma Mensagem do Advogado

```
Advogado → WhatsApp → Evolution API → Webhook (/webhook/whatsapp)
                                              │
                                    ┌─────────▼──────────┐
                                    │  Identificar se é   │
                                    │  canal advogado     │
                                    │  (numero_whatsapp   │
                                    │  está em Usuario    │
                                    │  com role=advogado) │
                                    └─────────┬──────────┘
                                              │
                              ┌───────────────▼───────────────┐
                              │   Celery Task (NOVA)           │
                              │   processar_mensagem_advogado  │
                              │   (fila: hub_advogado)         │
                              └───────────────┬───────────────┘
                                              │
                              ┌───────────────▼───────────────┐
                              │  ClassificadorIntencaoAdvogado │
                              │  (Claude Haiku — rápido)       │
                              └───────────────┬───────────────┘
                                              │
                         ┌────────────────────┼────────────────────┐
                         │                    │                     │
               ┌─────────▼───────┐  ┌─────────▼───────┐  ┌───────▼──────────┐
               │  Harvey Chat     │  │  HarveyAnalyzer  │  │  Dashboard       │
               │  (dúvida jurídica│  │  (petição/juris) │  │  (status escritório)│
               └─────────┬───────┘  └─────────┬───────┘  └───────┬──────────┘
                         │                    │                     │
                         └────────────────────┼─────────────────────┘
                                              │
                              ┌───────────────▼───────────────┐
                              │   Formatar resposta WhatsApp   │
                              │   (sem fragmentação excessiva  │
                              │    — advogado lê texto longo)  │
                              └───────────────┬───────────────┘
                                              │
                              ┌───────────────▼───────────────┐
                              │   WhatsAppService.enviar()     │
                              │   (evolution_client.py)        │
                              └────────────────────────────────┘
```

### 5.4 Identificação do Canal no Webhook Existente

O webhook existente em `webhook_whatsapp.py` recebe todas as mensagens. Adicionar lógica de roteamento por **número de telefone do remetente**:

```python
# Em webhook_whatsapp.py — dentro do handler de messages.upsert

# Verificar se remetente é advogado do escritório
usuario = await db.query(Usuario).filter(
    Usuario.whatsapp_numero == telefone_remetente,
    Usuario.escritorio_id == escritorio_id,
    Usuario.role.in_(["advogado", "admin"]),
    Usuario.ativo == True,
).first()

if usuario:
    # Rotear para fila do hub do advogado
    processar_mensagem_advogado.apply_async(
        args=[payload_dict, usuario.id],
        queue="hub_advogado"
    )
else:
    # Fluxo existente do cliente
    processar_mensagem_recebida.apply_async(...)
```

**Aproveitamento:** 100% do código de webhook existente. Apenas adiciona um `if/else` de roteamento.

### 5.5 Nova Celery Task

**`feature_1_ia_personalizada/workers/hub_advogado.py`** (arquivo novo)

```python
# Estrutura da task principal

@celery_app.task(
    name="processar_mensagem_advogado",
    queue="hub_advogado",
    max_retries=3,
    default_retry_delay=5,
    soft_time_limit=120,
    time_limit=150,
)
async def processar_mensagem_advogado(
    payload: dict,
    usuario_id: int,
) -> None:
    """
    Processa mensagem do advogado:
    1. Classifica intenção (Claude Haiku — rápido)
    2. Busca dados relevantes (processos, clientes, RAG)
    3. Chama Harvey AI com contexto completo
    4. Envia resposta formatada via WhatsApp
    """
    ...
```

### 5.6 Nova Fila Celery

Em `workers/celery_app.py`, adicionar:

```python
# Adicionar ao CELERY_TASK_ROUTES
"feature_1_ia_personalizada.workers.hub_advogado.*": {"queue": "hub_advogado"},

# Adicionar à lista de queues no worker start command
# celery -A ... worker -Q monitoramento,notificacoes,ia,relacionamento,hub_advogado
```

### 5.7 Modelo para Sessão do Advogado

Criar modelo de memória de sessão específico para advogado (diferente do histórico do cliente):

```python
# shared/models/sessao_advogado.py (arquivo novo)

class SessaoAdvogado(Base, TimestampMixin, TenantMixin):
    """
    Histórico de conversação do advogado com o Hub.
    Separado de Interacao (que é para cliente).
    """
    __tablename__ = "sessoes_advogado"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    mensagem_advogado: Mapped[str] = mapped_column(Text)
    resposta_hub: Mapped[str] = mapped_column(Text)
    intencao: Mapped[str] = mapped_column(String(50))
    modelo_ia: Mapped[str] = mapped_column(String(50))  # 'harvey', 'claude', 'harvey_claude'
    tokens_input: Mapped[int] = mapped_column(default=0)
    tokens_output: Mapped[int] = mapped_column(default=0)
    custo_estimado: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=0)
    cliente_referenciado_id: Mapped[int | None] = mapped_column(ForeignKey("clientes.id"))
    processo_referenciado_id: Mapped[int | None] = mapped_column(ForeignKey("processos.id"))
    metadata_json: Mapped[dict] = mapped_column(JSONB, default={})
```

---

## 6. Componente 4 — Análise de Petições via WhatsApp

### 6.1 Fluxo

Advogado envia documento PDF pelo WhatsApp → Evolution API captura → Hub processa com Harvey.

```
Advogado envia PDF no WhatsApp
        │
        ▼
Evolution API → Webhook (tipo: "document")
        │
        ▼
processar_mensagem_advogado (detecta type=document)
        │
        ▼
Baixar PDF via evolution_client.download_media()
        │
        ▼
Extrair texto via PyMuPDF (já em ingestion.py)
        │
        ▼
HarveyClient.analisar_peticao(conteudo, tipo_analise)
        │
        ▼
Resposta estruturada:
  • Tipo da peça
  • Pontos fortes
  • Pontos fracos / lacunas
  • Argumentos ausentes
  • Precedentes relevantes (Harvey busca jurisprudência)
  • Sugestão de melhoria
        │
        ▼
Formatar em markdown para WhatsApp
(Evolution API suporta negrito *texto*, itálico _texto_)
        │
        ▼
Enviar resposta ao advogado
```

### 6.2 Tipos de Análise

```python
# Em harvey_client.py

class TipoAnaliseHarvey(str, Enum):
    ANALISE_COMPLETA = "analise_completa"
    PONTOS_FRACOS = "pontos_fracos"
    JURISPRUDENCIA_RELACIONADA = "jurisprudencia_relacionada"
    RESUMO_EXECUTIVO = "resumo_executivo"
    CONTRA_ARGUMENTOS = "contra_argumentos"
```

### 6.3 Reaproveitamento

- `ingestion.py:DocumentoIngester._extrair_texto_pdf()` — extração de texto do PDF já existe
- `data_cleaner.py` — limpeza de artefatos OCR já existe
- `evolution_client.py:download_media()` — download de mídia já existe (usado para áudios)

---

## 7. Componente 5 — Resumo Inteligente de Processo

### 7.1 O Que O Advogado Recebe

Quando digita algo como _"Resumo do processo do João Silva"_ ou envia o número CNJ:

```
📋 *Processo 0001234-55.2023.8.26.0001*
Cliente: João Silva
Tribunal: TJSP — 3ª Vara Cível
Fase: Instrução processual

*Últimas movimentações:*
• 28/03 — Juntada de contestação pelo réu
• 15/03 — Audiência de conciliação: sem acordo

*Análise Harvey:*
O processo está em fase crítica. A contestação apresentada pelo réu traz o argumento de prescrição (Art. 206 CC), que é refutável dado que a ciência do dano ocorreu em [data]. Recomendo juntar os documentos X, Y, Z antes da próxima audiência.

*Score de Risco:* 62/100 (moderado)
*Próxima audiência:* 15/04/2026

Quer que eu analise a petição inicial ou a contestação?
```

### 7.2 Dados Coletados

Harvey recebe como contexto:

1. **Dados estruturados do banco** — processo, andamentos, partes (já em `worker_queries.py`)
2. **Documentos RAG do escritório** — petições, contestações já ingeridas
3. **Dados do cliente** — CRM score, histórico de interações
4. **Dados externos** — Jusbrasil (já em `jusbrasil_client.py` e `datajud_client.py`)

Harvey faz o **raciocínio jurídico** sobre esses dados — não coleta novos dados.

---

## 8. Prompts do Hub do Advogado

### 8.1 Onde Criar

**`feature_1_ia_personalizada/services/ai/prompts.py`** — adicionar seção ao arquivo existente (linhas 524+):

```python
# === PROMPTS DO HUB DO ADVOGADO ===

SYSTEM_PROMPT_HUB_ADVOGADO_BASE = """
Você é um assistente jurídico especializado, acessado exclusivamente por advogados.
Escritório: {nome_escritorio}
Advogado: Dr(a). {nome_usuario} — OAB {oab}

Você tem acesso completo a todos os dados do escritório.
Responda com precisão técnica — o interlocutor é um profissional jurídico.
Cite artigos de lei, súmulas e jurisprudências com precisão.
Não use linguagem simplificada. Seja objetivo e denso.
""".strip()

SYSTEM_PROMPT_ANALISE_PETICAO = """
Analise o documento jurídico fornecido como um advogado sênior revisando o trabalho de um colega.
Estruture a análise em:
1. IDENTIFICAÇÃO: Tipo de peça, vara, partes, pedidos
2. PONTOS FORTES: Argumentos bem fundamentados
3. VULNERABILIDADES: Lacunas, argumentos fracos, risco de improcedência
4. JURISPRUDÊNCIA RELEVANTE: Precedentes que apoiam ou atacam a tese
5. SUGESTÕES: O que adicionar, modificar ou retirar
6. AVALIAÇÃO GERAL: Score de 0-100 + recomendação final

Base legal: direito brasileiro vigente. Data de referência: {data_hoje}.
""".strip()

SYSTEM_PROMPT_PESQUISA_JURISPRUDENCIA = """
Pesquise jurisprudência sobre: {query}

Tribunal(is) relevantes: {tribunais}
Período: {periodo}

Forneça:
1. Ementa resumida (2-3 linhas por julgado)
2. Data + tribunal + número do processo
3. Aplicabilidade ao caso: FAVORÁVEL | DESFAVORÁVEL | NEUTRO
4. Tendência atual: se jurisprudência está se consolidando ou oscilando

Ordene do mais recente para o mais antigo.
""".strip()

SYSTEM_PROMPT_INSIGHT_CLIENTE = """
Com base nos dados do cliente {nome_cliente} (CRM score: {crm_score}):

Histórico de interações: {resumo_interacoes}
Processos ativos: {resumo_processos}
Última ação recomendada: {ultima_acao_crm}

Forneça:
1. Situação atual do relacionamento (3-4 linhas)
2. Pontos de atenção imediata
3. Recomendação de próxima ação (específica e acionável)
4. Risco de abandono: BAIXO | MÉDIO | ALTO
""".strip()
```

---

## 9. Novos Endpoints REST (para Dashboard Web)

O Hub do Advogado funciona primariamente via WhatsApp, mas os dados ficam acessíveis via API para eventual dashboard web:

### 9.1 Arquivo a Criar

**`feature_1_ia_personalizada/api/routes/hub_advogado.py`**

```
POST /api/v1/hub/consultar
  Body: { pergunta: str, cliente_id?: int, processo_id?: int }
  → Chama Harvey diretamente (sem WhatsApp) para uso em dashboard
  → Role: advogado, admin

POST /api/v1/hub/analisar-peticao
  Body: FormData (arquivo PDF)
  → Análise Harvey do documento
  → Role: advogado, admin

GET  /api/v1/hub/historico?page=1&limit=25
  → Lista sessoes_advogado do usuário autenticado
  → Role: advogado, admin

GET  /api/v1/hub/historico/{sessao_id}
  → Detalhes de uma sessão específica

GET  /api/v1/hub/metricas
  → Tokens consumidos, custo total, intenções mais usadas
  → Role: admin
```

---

## 10. Configuração por Escritório (Feature Flag)

Harvey deve ser ativável por escritório (diferente planos). Adicionar ao modelo `Escritorio`:

```python
# shared/models/escritorio.py — adicionar campos

harvey_habilitado: Mapped[bool] = mapped_column(default=False)
harvey_canal_advogado_numero: Mapped[str | None] = mapped_column(String(20))
# Número WhatsApp dedicado ao hub do advogado
# Se None: usa o mesmo número, distingue por role do remetente

harvey_quota_tokens_mes: Mapped[int] = mapped_column(default=500_000)
harvey_tokens_usados_mes: Mapped[int] = mapped_column(default=0)
harvey_confidence_threshold: Mapped[float] = mapped_column(default=0.70)
# Threshold ajustável por escritório (padrão 0.70)
```

```sql
-- Migração: alembic/versions/XXX_add_harvey_fields_escritorio.py
ALTER TABLE escritorios ADD COLUMN harvey_habilitado BOOLEAN DEFAULT FALSE;
ALTER TABLE escritorios ADD COLUMN harvey_canal_advogado_numero VARCHAR(20);
ALTER TABLE escritorios ADD COLUMN harvey_quota_tokens_mes INTEGER DEFAULT 500000;
ALTER TABLE escritorios ADD COLUMN harvey_tokens_usados_mes INTEGER DEFAULT 0;
ALTER TABLE escritorios ADD COLUMN harvey_confidence_threshold FLOAT DEFAULT 0.70;
```

### 10.1 Verificação no Orchestrator

```python
# No orchestrator.py — antes de chamar Harvey

if not escritorio.harvey_habilitado:
    # Forçar Claude sem roteamento para Harvey
    return await gerar_resposta_claude(state)

if escritorio.harvey_tokens_usados_mes >= escritorio.harvey_quota_tokens_mes:
    # Quota Harvey esgotada → fallback para Claude
    logger.warning("harvey_quota_esgotada", escritorio_id=escritorio_id)
    return await gerar_resposta_claude(state)
```

---

## 11. Plano de Implementação por Fases

### Fase 1 — Fundação Harvey (2-3 dias)

**Objetivo:** Harvey funcionando isoladamente, sem impacto no fluxo existente.

| Tarefa | Arquivo | Reutiliza |
|---|---|---|
| Criar `HarveyClient` async com retry | `services/ai/harvey_client.py` | Padrão de `claude_client.py` |
| Adicionar `HARVEY_API_KEY` nas settings | `shared/config/settings.py` | `settings.py` existente |
| Feature flag por escritório | Migração Alembic | Modelo `Escritorio` existente |
| Testes unitários do client | `tests/unit/test_harvey_client.py` | Fixtures existentes |

**Critério de aceite:** `HarveyClient.gerar_resposta()` retorna resposta válida num teste de integração.

---

### Fase 2 — Roteador de Confiança (2-3 dias)

**Objetivo:** Claude delega para Harvey automaticamente quando confiança é baixa.

| Tarefa | Arquivo | Reutiliza |
|---|---|---|
| Criar `ConfidenceRouter` | `services/ai/confidence_router.py` | `fact_checker.py`, `memory.py` |
| Adicionar campo `modelo_ia` nas interações | Migração Alembic | Modelo `Interacao` existente |
| Adicionar nós `avaliar_confianca` + `gerar_resposta_harvey` no LangGraph | `services/ai/orchestrator.py` | Grafo LangGraph existente |
| Adicionar prompts Harvey (cliente) | `services/ai/prompts.py` | Arquivo existente |
| Métricas Harvey (tokens, custo, roteamentos) | `api/routes/metrics.py` | Prometheus existente |
| Testes de integração do roteador | `tests/integration/` | Suite de testes existente |

**Critério de aceite:** Pergunta jurídica complexa → score < 0.70 → Harvey responde. Pergunta simples de status → Claude responde.

---

### Fase 3 — Hub do Advogado via WhatsApp (3-4 dias)

**Objetivo:** Advogado consegue fazer perguntas jurídicas via WhatsApp e receber respostas Harvey.

| Tarefa | Arquivo | Reutiliza |
|---|---|---|
| Roteamento por role no webhook | `api/routes/webhook_whatsapp.py` | Webhook existente (só adicionar if/else) |
| Task Celery do hub | `workers/hub_advogado.py` | Padrão de `send_notifications.py` |
| Classificador de intenção do advogado | `services/ai/hub_advogado_classifier.py` | `claude_client.py` (Haiku) |
| Modelo `SessaoAdvogado` | `shared/models/sessao_advogado.py` | `TenantMixin`, `TimestampMixin` |
| Adicionar fila `hub_advogado` no Celery | `workers/celery_app.py` | Config existente |
| Prompts do hub do advogado | `services/ai/prompts.py` | Arquivo existente |
| Testes | `tests/unit/test_hub_advogado.py` | Fixtures existentes |

**Critério de aceite:** Advogado envia "Dúvida sobre CPC art. 485" → Harvey responde via WhatsApp em < 30 segundos.

---

### Fase 4 — Análise de Petições (2-3 dias)

**Objetivo:** Advogado envia PDF → Harvey analisa e responde com insights estruturados.

| Tarefa | Arquivo | Reutiliza |
|---|---|---|
| Detecção de documento no hub | `workers/hub_advogado.py` | `evolution_client.download_media()` |
| Pipeline PDF → Harvey | `services/ai/harvey_client.py` | `ingestion.py._extrair_texto_pdf()` |
| Prompts de análise de petição | `services/ai/prompts.py` | Seção Harvey existente |
| Endpoint REST de análise | `api/routes/hub_advogado.py` | Auth middleware existente |
| Testes | `tests/integration/test_analise_peticao.py` | Suite existente |

**Critério de aceite:** Advogado envia PDF de petição → recebe análise estruturada em < 60 segundos.

---

### Fase 5 — Resumo de Processos e Insights CRM (2 dias)

**Objetivo:** Harvey consegue cruzar dados jurídicos + CRM para dar insights acionáveis ao advogado.

| Tarefa | Arquivo | Reutiliza |
|---|---|---|
| Intent handler de resumo de processo | `workers/hub_advogado.py` | `worker_queries.py` (queries existentes) |
| Intent handler de insight de cliente | `workers/hub_advogado.py` | `crm/aggregator.py` e `analyzer.py` |
| Prompts de resumo e insight | `services/ai/prompts.py` | Seção Harvey |
| Endpoint REST `/hub/historico` | `api/routes/hub_advogado.py` | JWT middleware |

**Critério de aceite:** "Me dá um resumo do João Silva" → Harvey retorna resumo com dados reais do processo + recomendação CRM.

---

## 12. Arquivos a Criar (Completo)

```
NOVOS ARQUIVOS:
feature_1_ia_personalizada/
├── services/
│   └── ai/
│       ├── harvey_client.py          # Cliente Harvey AI (espelhado no claude_client.py)
│       └── confidence_router.py     # Roteador de confiança Claude → Harvey
├── workers/
│   └── hub_advogado.py              # Task Celery do hub do advogado
└── api/
    └── routes/
        └── hub_advogado.py          # Endpoints REST do hub

shared/
└── models/
    └── sessao_advogado.py           # Histórico de sessões do advogado

alembic/versions/
├── XXX_add_modelo_ia_to_interacoes.py
├── XXX_add_harvey_fields_to_escritorios.py
└── XXX_add_sessoes_advogado.py

ARQUIVOS EXISTENTES A MODIFICAR:
shared/config/settings.py             # +4 vars Harvey
shared/models/escritorio.py          # +5 campos Harvey
feature_1_ia_personalizada/
├── services/ai/
│   ├── orchestrator.py              # +2 nós no LangGraph
│   └── prompts.py                   # +4 prompts Harvey
├── workers/celery_app.py            # +1 fila hub_advogado
└── api/routes/webhook_whatsapp.py   # +roteamento por role
```

---

## 13. Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| Harvey API indisponível | Média | Alto | Circuit breaker (já existe `pybreaker`) + fallback para Claude |
| Latência Harvey > 30s | Alta | Médio | Mensagem "Analisando..." imediata + resposta assíncrona |
| Custo Harvey por token alto | Alta | Médio | Quota por escritório + cache de respostas semelhantes (Redis) |
| Advogado usa canal cliente acidentalmente | Baixa | Baixo | Identificação por `whatsapp_numero` em `Usuario` |
| Score de confiança mal calibrado | Média | Médio | A/B test threshold por escritório + métricas de satisfação |
| PDF muito grande para Harvey | Média | Baixo | Chunking antes de enviar (reutilizar `ingestion.py`) |

---

## 14. Métricas de Sucesso

| Métrica | Meta | Como Medir |
|---|---|---|
| Taxa de roteamento Claude → Harvey | < 20% das msgs de cliente | `modelo_ia` em `Interacao` |
| NPS após resposta Harvey (cliente) | ≥ 4.2 | `satisfacao` em `Interacao` |
| Tempo de resposta Harvey (advogado) | < 30s para texto, < 90s para PDF | `SessaoAdvogado.created_at` |
| Retenção do hub (advogado usa ≥ 3x/semana) | ≥ 60% dos advogados ativos | `SessaoAdvogado` aggregation |
| Custo por análise de petição | < R$ 0,50 | `custo_estimado` em `SessaoAdvogado` |

---

## 15. Dependências Externas a Confirmar

Antes de iniciar a implementação, confirmar com a equipe Harvey:

1. **Endpoint de chat:** `POST /v1/chat/completions` ou formato próprio?
2. **Endpoint de documento:** Existe API dedicada para análise de PDFs?
3. **Modelo disponível no Brasil:** Latência aceitável para Brasil (Harvey é US-based)?
4. **Pricing:** Por token? Por request? Por documento?
5. **Rate limits:** Quantas requisições/minuto por API key?
6. **Idioma:** Suporte nativo ao português brasileiro ou necessita prompt em inglês?
7. **Acesso a jurisprudência brasileira:** Harvey tem base de dados de STJ/STF/TJs?

---

## 16. Resumo do Aproveitamento da Base Existente

| Componente Existente | Aproveitamento na Feature |
|---|---|
| `LangGraph orchestrator.py` | Adiciona 2 nós sem refatorar o grafo |
| `ClaudeClient` (padrão de implementação) | `HarveyClient` segue a mesma interface |
| `fact_checker.py` | Reusado no `ConfidenceRouter` sem alteração |
| `webhook_whatsapp.py` | Adiciona `if/else` de roteamento (5 linhas) |
| `evolution_client.download_media()` | Download de PDFs enviados pelo advogado |
| `ingestion.py._extrair_texto_pdf()` | Extração de texto de petições |
| `worker_queries.py` | Queries de processos/clientes para contexto Harvey |
| `crm/aggregator.py` | Contexto de CRM para insights do advogado |
| `pybreaker` (circuit breaker) | Harvey API com circuit breaker igual ao DataJud |
| `TenantMixin` + `TimestampMixin` | `SessaoAdvogado` herda sem modificação |
| `celery_app.py` (filas) | Adiciona `hub_advogado` às filas existentes |
| `prompts.py` | Adiciona seção Harvey ao final do arquivo |
| Redis cache + TTL | Cache de respostas Harvey (30min TTL) |
| JWT auth middleware | Endpoints do hub reutilizam sem alteração |
| Prometheus metrics | Adiciona métricas Harvey ao coletor existente |
| Testes (fixtures + mocks) | Suite existente reutilizada para Harvey |

**Estimativa:** ~80% da infraestrutura já existe. A feature adiciona principalmente lógica de negócio (roteamento, prompts, novo client) sem refatorar a base.
