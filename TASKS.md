# TASKS — Novas Features e Melhorias

> **Meta:** sistema mais inteligente, rápido e eficiente possível. Cada tarefa indica os arquivos exatos a tocar e o critério de aceite.
> **Referência arquitetural:** [docs/ROADMAP_FEATURES.md](docs/ROADMAP_FEATURES.md)

---

## Sprint 1 — Inteligência de Contexto (Features 3 e 2)

> Menor risco, maior impacto imediato. Zero novas dependências. Aproveita 100% da infra existente.

---

### Feature 3 — Resumo Inteligente de Movimentação

**Objetivo:** transformar andamentos técnicos em mensagens que o cliente entende de verdade, com contexto histórico do processo.

**Status: 100% concluída ✅**

#### 3.1 — Migração SQL: estado do processo ✅

- [x] Criar `alembic/versions/003_add_processo_state.py`
- [x] Adicionar em `processos`:
  - `estado_atual JSONB DEFAULT NULL` — snapshot do estado: fase, andamentos recentes, próximo passo esperado
  - `fase_processual VARCHAR(100) DEFAULT NULL` — `conhecimento` | `instrucao` | `saneamento` | `julgamento` | `recurso` | `execucao` | `encerrado`
- [x] Adicionar índice: `CREATE INDEX ON processos (escritorio_id, fase_processual)`
- [ ] Rodar e testar migração em dev
- **Arquivo:** `alembic/versions/003_add_processo_state.py`
- **Critério:** `alembic upgrade head` sem erros; colunas visíveis no schema

> Modelo `shared/models/processo.py` também atualizado com as novas colunas.

#### 3.2 — Serviço `ProcessoStateManager` ✅

- [x] Criar `feature_1_ia_personalizada/services/ai/processo_state.py`
- [x] Implementar `get_state(processo_id)` — lê estado_atual, inicializa com fase `conhecimento` se nulo
- [x] Implementar `update_state(processo_id, novo_andamento)` — classifica fase por mapa de palavras-chave, persiste no banco
- [x] Implementar `gerar_contexto_historico(processo_id, n_ultimos=5)` — query indexada com LIMIT
- [x] Expor versões `async_*` para uso no FastAPI/orchestrator sem bloquear o event loop
- **Arquivo:** `feature_1_ia_personalizada/services/ai/processo_state.py`

#### 3.3 — Novo prompt contextualizado ✅

- [x] Adicionar `SYSTEM_PROMPT_ANDAMENTO_CONTEXTUALIZADO` em `feature_1_ia_personalizada/services/ai/prompts.py`
- [x] Variáveis: `{nome_escritorio}`, `{nome_cliente}`, `{tipo_acao}`, `{fase_processual}`, `{polo_cliente}`, `{historico_andamentos}`, `{novo_andamento}`
- [x] 5 instruções explícitas + limite de 4 parágrafos / 250 palavras
- **Arquivo:** `feature_1_ia_personalizada/services/ai/prompts.py`

#### 3.4 — Refatorar `juridical_translator.py` para aceitar contexto ✅

- [x] Adicionar método `traduzir_com_contexto(andamento, fase_atual, historico, tipo_acao, polo_cliente, nome_escritorio, nome_cliente)`
- [x] Monta `SYSTEM_PROMPT_ANDAMENTO_CONTEXTUALIZADO` e chama Claude Haiku com `max_tokens=400`
- [x] Método original `traduzir_andamento()` mantido intacto
- [x] Loga `tokens_input` e `tokens_output` para monitorar critério < 1500 tokens
- **Arquivo:** `feature_1_ia_personalizada/services/ai/juridical_translator.py`

#### 3.5 — Integrar no worker `monitor_processos.py` ✅

- [x] Import do `ProcessoStateManager`
- [x] Extrai `tipo_acao` e `polo_cliente` dos dados do processo (query atualizada em `worker_queries.py`)
- [x] Para cada andamento: `update_state()` → `gerar_contexto_historico()` → `traduzir_com_contexto()`
- [x] Envia resumo contextualizado via Celery (mesmo canal, fila `notificacoes`)
- **Arquivos:** `monitor_processos.py`, `shared/database/worker_queries.py`

#### 3.6 — Testes ✅

- [x] `feature_1_ia_personalizada/tests/unit/test_processo_state.py` — classifica fases corretamente, persiste estado, gera contexto histórico
- [x] `feature_1_ia_personalizada/tests/unit/test_juridical_translator_contexto.py` — mock Claude; verifica que prompt montado contém todos os campos
- [x] `feature_1_ia_personalizada/tests/integration/test_resumo_andamento.py` — fluxo completo: andamento detectado → resumo → WhatsApp (mock Evolution)

---

### Feature 2 — Score de Risco Processual em Tempo Real

**Objetivo:** substituir o `vitoria_preditor.py` legado por um score de complexidade/risco que informa o advogado, sem prever resultado (compliance OAB).

#### 2.1 — Migração SQL: colunas de score em `processos`

- [ ] Criar `alembic/versions/004_add_score_risco.py`
- [ ] Adicionar em `processos`:
  - `score_risco SMALLINT DEFAULT NULL` — 0 a 100
  - `score_nivel VARCHAR(20) DEFAULT NULL` — `baixo` | `moderado` | `alto` | `critico`
  - `score_componentes JSONB DEFAULT NULL` — detalhamento por fator
  - `score_interpretacao TEXT DEFAULT NULL` — texto gerado para o advogado
  - `score_atualizado_em TIMESTAMPTZ DEFAULT NULL`
- [ ] Criar índice parcial: `CREATE INDEX ON processos (escritorio_id, score_risco) WHERE score_risco IS NOT NULL`
- **Arquivo:** `alembic/versions/004_add_score_risco.py`
- **Critério:** migração reversível; índice criado

#### 2.2 — Refatorar `vitoria_preditor.py` → `score_risco.py`

- [ ] Criar `feature_1_ia_personalizada/services/legal_data/score_risco.py` (mantém `vitoria_preditor.py` para não quebrar imports existentes — deprecar gradualmente)
- [ ] Classe `ScoreRiscoCalculator`:
  - `calcular(processo, datajud_data) -> ScoreRisco`
  - Fórmula ponderada com 5 componentes (pesos configuráveis via `constants.py`):
    1. **Complexidade jurídica** (25%): derivada do `tipo_acao` — tabela de pesos em `constants.py`
    2. **Duração estimada** (25%): DataJud — média de dias para essa vara/classe; normalizado 0-100
    3. **Histórico da vara** (20%): % casos com desfecho neutro/negativo para o polo do cliente
    4. **Valor da causa** (15%): normalizado por faixa (< 40 SM = baixo; > 200 SM = alto)
    5. **Fase processual atual** (15%): risco decresce conforme processo avança (execução = menor risco de incerteza)
  - Score final = média ponderada arredondada para inteiro
  - `nivel`: `baixo` (0-25), `moderado` (26-50), `alto` (51-75), `critico` (76-100)
- [ ] Método `gerar_interpretacao(score_obj, processo) -> str` — texto curto para o advogado (sem Claude; template string baseado nos componentes mais altos)
- [ ] **Performance:** score calculado em memória; única chamada externa é DataJud (já cacheada por `cache_manager.py` com TTL 6h)
- **Arquivo:** `feature_1_ia_personalizada/services/legal_data/score_risco.py`
- **Critério:** cálculo < 50ms (sem I/O externo se cache hit); output tipado com Pydantic `ScoreRisco`

#### 2.3 — Integrar no worker `monitor_processos.py`

- [ ] Após atualizar andamento, chamar `ScoreRiscoCalculator.calcular(processo, datajud_data)`
- [ ] Atualizar `processo.score_risco`, `.score_nivel`, `.score_componentes`, `.score_interpretacao`, `.score_atualizado_em`
- [ ] **Eficiência:** reusar o `datajud_data` já buscado nessa iteração — não fazer segunda chamada
- [ ] Persistir junto com o `commit()` do andamento — único flush ao banco
- **Arquivo:** `feature_1_ia_personalizada/workers/monitor_processos.py`
- **Critério:** score atualizado em toda execução do worker sem overhead mensurável

#### 2.4 — Expor score na API existente

- [ ] Em `feature_1_ia_personalizada/api/routes/processos.py`, GET `/processos/{id}` passar a incluir:
  ```json
  {
    "score_risco": 67,
    "score_nivel": "moderado",
    "score_interpretacao": "Processo com duração média estimada em 14 meses nesta vara.",
    "score_atualizado_em": "2026-03-16T10:00:00Z"
  }
  ```
- [ ] Atualizar schema Pydantic em `shared/schemas/processo.py` com campos opcionais de score
- [ ] GET `/processos` (listagem) incluir `score_risco` e `score_nivel` como campos de filtragem: `?score_nivel=alto`
- **Arquivos:** `feature_1_ia_personalizada/api/routes/processos.py`, `shared/schemas/processo.py`
- **Critério:** campos opcionais (null quando ainda não calculado); filtro por nível funciona

#### 2.5 — Testes

- [ ] `feature_1_ia_personalizada/tests/unit/test_score_risco.py` — fórmula correta para casos extremos; pesos somam 100%; nível correto para cada faixa
- [ ] `feature_1_ia_personalizada/tests/unit/test_vitoria_preditor_deprecated.py` — importar `vitoria_preditor` ainda funciona (backward compat)
- [ ] `feature_1_ia_personalizada/tests/integration/test_score_api.py` — GET `/processos/{id}` retorna score; filtro por nível funciona

---

## Sprint 2 — Engajamento e Controle (Features 5 e 6)

---

### Feature 5 — Analytics de Satisfação e Retenção

**Objetivo:** dashboard que prova ROI para o escritório. Dados já existem na tabela `interacoes` — só falta agregar corretamente.

#### 5.1 — Índices SQL para performance de analytics

- [x] Criar `alembic/versions/005_add_analytics_indexes.py`
- [x] Criar índices:
  ```sql
  CREATE INDEX CONCURRENTLY ON interacoes (escritorio_id, created_at DESC);
  CREATE INDEX CONCURRENTLY ON interacoes (escritorio_id, satisfacao) WHERE satisfacao IS NOT NULL;
  CREATE INDEX CONCURRENTLY ON interacoes (escritorio_id, direcao, created_at);
  CREATE INDEX CONCURRENTLY ON interacoes (cliente_id, created_at DESC);
  CREATE INDEX CONCURRENTLY ON interacoes (escritorio_id, tipo, created_at);
  ```
- [x] Usar `CONCURRENTLY` para não bloquear tabela em produção
- **Arquivo:** `alembic/versions/005_add_analytics_indexes.py`
- **Critério:** queries de dashboard executam em < 200ms com 100k linhas

#### 5.2 — Serviço `AnalyticsCalculadora`

- [x] Criar `feature_1_ia_personalizada/services/analytics/calculadora.py`
- [x] Método `resumo_periodo(escritorio_id, dias=30) -> dict`:
  - Total de interações (entrada + saída)
  - Clientes únicos ativos no período
  - NPS médio atual vs período anterior (variação absoluta)
  - % interações resolvidas sem humano (saída com `direcao=saida` sem escalação)
  - Horas economizadas: `(interacoes_autonomas × 8min) / 60`
  - Custo total IA no período (`SUM(custo_estimado)`)
  - Tempo médio de resposta (`AVG(tempo_resposta_ms)`)
- [ ] Método `tendencia_semanal(escritorio_id, semanas=8) -> list`:
  - Agrega por semana ISO: total de interações, NPS médio, autonomia %
  - **Performance:** query única com `date_trunc('week', created_at)` GROUP BY
- [ ] Método `ranking_clientes(escritorio_id, limite=20) -> list`:
  - Por NPS, interações, último contato
  - Identifica clientes em risco (sem interação há > 30 dias + NPS < 6)
- [ ] **Performance:** todas as queries usam apenas `interacoes` com os índices criados em 5.1; sem subqueries não indexadas
- **Arquivo:** `feature_1_ia_personalizada/services/analytics/calculadora.py`
- **Critério:** cada método executa query única; resultado em < 300ms em produção

#### 5.3 — Expandir rota `/chat/stats/dashboard`

- [x] Em `feature_1_ia_personalizada/api/routes/chat.py`, GET `/chat/stats/dashboard` passar a retornar estrutura completa:
  - `resumo` (NPS, interações, clientes ativos, variação)
  - `eficiencia` (autonomia %, horas economizadas, custo USD, tempo médio resposta)
  - `por_cliente` (top 20 com NPS, interações, status de risco)
  - `tendencia_semanal` (8 semanas)
  - `score_risco_distribuicao` (contagem de processos por nível de risco — aproveita Feature 2)
- [ ] Aceitar query params: `?dias=30` (padrão 30), `?dias=7`, `?dias=90`
- [ ] **Cache:** resultado cacheado no Redis por 15 minutos (chave `analytics:{escritorio_id}:{dias}`) — usar `cache_manager.py` existente
- [ ] Invalidar cache ao receber nova interação (hook no worker `send_notifications.py`)
- **Arquivo:** `feature_1_ia_personalizada/api/routes/chat.py`
- **Critério:** endpoint responde em < 100ms (cache hit) ou < 500ms (cache miss); payload < 50KB

#### 5.4 — Coleta automática de NPS via WhatsApp

- [ ] Em `feature_1_ia_personalizada/workers/mensagens_relacionamento.py`, adicionar task `solicitar_nps_cliente`:
  - Disparada 7 dias após cada andamento significativo (sentença, decisão interlocutória, despacho)
  - Mensagem: "Olá {nome_cliente}! Como avalia o atendimento do {nome_escritorio} até agora? Responda com um número de 1 a 5."
  - Salva `metadata_json["aguardando_nps"] = True` na interação atual
- [ ] Em `feature_1_ia_personalizada/api/routes/webhook_whatsapp.py`, detectar resposta numérica 1-5 quando `aguardando_nps=True`:
  - Salva `interacao.satisfacao = int(resposta)`
  - Limpa flag `aguardando_nps`
  - Envia agradecimento automático
  - **Inteligência:** se NPS ≤ 3, envia alerta imediato para advogado responsável
- [ ] Garantir que NPS não seja pedido mais de 1x por mês por cliente
- **Arquivos:** `feature_1_ia_personalizada/workers/mensagens_relacionamento.py`, `feature_1_ia_personalizada/api/routes/webhook_whatsapp.py`
- **Critério:** NPS coletado automaticamente; alerta disparado para NPS baixo; sem spam de pesquisa

#### 5.5 — Exportação de Relatório Mensal

- [ ] Criar `feature_1_ia_personalizada/services/analytics/exportador.py`
- [ ] Método `gerar_csv(escritorio_id, mes_ano) -> bytes` — exportação de todas as interações do mês
- [ ] Adicionar rota `GET /chat/stats/export?formato=csv&mes=2026-03` em `chat.py`
- [ ] Sem dependência `reportlab` por enquanto — CSV suficiente para MVP; PDF em backlog
- **Arquivos:** `feature_1_ia_personalizada/services/analytics/exportador.py`, `feature_1_ia_personalizada/api/routes/chat.py`
- **Critério:** CSV gerado corretamente; download via API funciona

#### 5.6 — Métricas Prometheus para analytics

- [ ] Adicionar contadores em `feature_1_ia_personalizada/api/routes/metrics.py`:
  - `nps_score_gauge` (by escritorio_id) — NPS médio atual
  - `ia_autonomia_percent_gauge` (by escritorio_id) — % resolvidas sem humano
  - `escalacoes_pendentes_gauge` (by escritorio_id) — para Feature 6
- [ ] Atualizar métricas a cada cálculo do dashboard (hook no serviço `calculadora.py`)
- **Arquivo:** `feature_1_ia_personalizada/api/routes/metrics.py`
- **Critério:** métricas visíveis no `/metrics`; Grafana consegue criar alertas por escritório

#### 5.7 — Testes

- [ ] `feature_1_ia_personalizada/tests/unit/test_analytics_calculadora.py` — resultados corretos com dados mock; edge cases (zero interações, NPS nulo)
- [ ] `feature_1_ia_personalizada/tests/integration/test_analytics_dashboard.py` — endpoint retorna estrutura completa; cache funciona; parâmetro `?dias=` respeitado
- [ ] `feature_1_ia_personalizada/tests/unit/test_nps_coleta.py` — webhook detecta resposta NPS; alerta disparado para NPS ≤ 3

---

### Feature 6 — Modo "Advogado no Loop" com Escalação Inteligente

**Objetivo:** IA escala com contexto completo quando detecta pergunta além do escopo. Advogado aprova em 2 cliques. Resolve compliance OAB e aumenta valor percebido.

#### 6.1 — Migração SQL: suporte a escalação

- [ ] Criar `alembic/versions/006_add_escalacao.py`
- [ ] Adicionar em `usuarios`:
  - `whatsapp_numero VARCHAR(20) DEFAULT NULL`
  - `escalacao_ativa BOOLEAN DEFAULT TRUE`
- [ ] Adicionar em `interacoes` via índice (sem coluna nova — usa `metadata_json`):
  - `CREATE INDEX ON interacoes ((metadata_json->>'escalacao_status')) WHERE metadata_json ? 'escalacao_status'`
- **Arquivo:** `alembic/versions/006_add_escalacao.py`
- **Critério:** migração ok; índice de escalação funciona para queries de pendentes

#### 6.2 — Atualizar schema e rota de usuário

- [ ] Adicionar `whatsapp_numero` e `escalacao_ativa` em `shared/schemas/usuario.py`
- [ ] PUT `/usuarios/{id}` (ou novo PATCH) aceitar esses campos
- [ ] Admin pode configurar número WhatsApp do advogado via painel
- **Arquivos:** `shared/schemas/usuario.py`, `feature_1_ia_personalizada/api/routes/` (rota de usuários)
- **Critério:** advogado configura seu número uma vez; persiste no banco

#### 6.3 — Serviço `EscalacaoDetector`

- [ ] Criar `feature_1_ia_personalizada/services/escalacao/detector.py`
- [ ] Lista `ESCALACAO_TRIGGERS` extraída de `disclaimers.json` (reutiliza base existente):
  ```python
  ESCALACAO_OBRIGATORIA = [
      "parecer_juridico", "estrategia_processual", "negociacao",
      "acordo_extrajudicial", "recurso_cabivel", "prazo_fatal",
      "decisao_judicial_impacto_alto", "tutela_urgencia"
  ]
  ```
- [ ] Método `deve_escalar(intencao: str, mensagem: str) -> tuple[bool, str]`:
  - Verifica se `intencao` está em `ESCALACAO_OBRIGATORIA`
  - Fallback: análise semântica da mensagem via Claude (somente se intencao for `duvida_geral` — evita chamada extra nos outros casos)
  - Retorna `(True, motivo)` ou `(False, "")`
- [ ] **Inteligência:** usar resultado da classificação de intenção já feita no orquestrador — não fazer segunda chamada ao Claude quando intencao já classifica claramente
- **Arquivo:** `feature_1_ia_personalizada/services/escalacao/detector.py`
- **Critério:** detecção correta; custo extra de tokens zero para intencoes claras

#### 6.4 — Serviço `EscalacaoContexto`

- [ ] Criar `feature_1_ia_personalizada/services/escalacao/contexto.py`
- [ ] Método `montar_contexto_advogado(cliente, processo, mensagem, historico) -> str`:
  - Formata mensagem estruturada para o advogado:
    ```
    ESCALACAO — {nome_cliente} / {numero_cnj}

    Pergunta do cliente:
    "{mensagem_cliente}"

    Contexto (ultimas 5 mensagens):
    {historico_resumido}

    Sugestao de resposta para aprovacao:
    "{sugestao_claude}"

    [ APROVAR ] | [ REJEITAR ]
    ```
  - Chama `ClaudeClient` para gerar `sugestao_claude` — prompt específico com instrução "responda como advogado, de forma simples, sem dar parecer formal"
  - `historico_resumido` vem de `memory.py` (já em Redis — sem query ao banco)
- [ ] **Eficiência:** sugestão gerada em paralelo com envio ao banco (`asyncio.gather`)
- **Arquivo:** `feature_1_ia_personalizada/services/escalacao/contexto.py`
- **Critério:** mensagem formatada clara; sugestão gerada em < 2s

#### 6.5 — Serviço `EscalacaoNotificador`

- [ ] Criar `feature_1_ia_personalizada/services/escalacao/notificador.py`
- [ ] Método `notificar_advogado(advogado, contexto_escalacao) -> str`:
  - Envia via `evolution_client.py` (mesmo cliente WhatsApp já usado)
  - Usa instância WhatsApp do escritório (`escritorio.webhook_whatsapp_instance`)
  - Retorna `message_id` do WhatsApp para rastreamento
- [ ] Persistir em `interacao.metadata_json`:
  ```json
  {
    "escalacao_status": "pendente",
    "advogado_id": 5,
    "advogado_whatsapp": "5511999999999",
    "whatsapp_message_id": "WAMID...",
    "escalado_em": "2026-03-16T10:00:00Z",
    "motivo": "parecer_juridico"
  }
  ```
- **Arquivo:** `feature_1_ia_personalizada/services/escalacao/notificador.py`
- **Critério:** advogado recebe mensagem; rastreamento salvo no banco

#### 6.6 — Novo nó no Orquestrador LangGraph

- [ ] Em `feature_1_ia_personalizada/services/ai/orchestrator.py`, adicionar nós:
  - **`avaliar_escalacao`**: após `classificar_intencao`, chama `EscalacaoDetector.deve_escalar()`
  - **`preparar_escalacao`**: se `requer_escalacao=True`, chama `EscalacaoContexto` + `EscalacaoNotificador`
- [ ] Novo fluxo do grafo:
  ```
  classificar_intencao
      │
      ├─ requer_escalacao=True ──► preparar_escalacao ──► enviar_resposta ("encaminhado ao advogado") ──► END
      │
      └─ requer_escalacao=False ──► [fluxo normal: buscar_dados → gerar_resposta → ...]
  ```
- [ ] Resposta ao cliente quando escalado: "Sua pergunta foi encaminhada ao seu advogado. Você receberá o retorno em breve. Caso seja urgente, entre em contato diretamente pelo {telefone_escritorio}."
- **Arquivo:** `feature_1_ia_personalizada/services/ai/orchestrator.py`
- **Critério:** fluxo correto no grafo; escalação transparente para o cliente; sem loop ou nó morto

#### 6.7 — Webhook: captura de resposta do advogado

- [ ] Em `feature_1_ia_personalizada/api/routes/webhook_whatsapp.py`, adicionar lógica:
  1. Verifica se remetente é advogado (lookup por `whatsapp_numero` na tabela `usuarios`)
  2. Se sim, busca `interacao` com `escalacao_status=pendente` mais recente para o escritório
  3. Detecta comando:
     - Mensagem contém "APROVAR" → envia `sugestao_claude` para o cliente, atualiza status para `aprovado`
     - Mensagem contém "REJEITAR" → atualiza status para `rejeitado`, notifica outro advogado se configurado
     - Qualquer outra mensagem → trata como resposta editada → envia ao cliente como está, status `editado_e_enviado`
- [ ] **Inteligência:** normalizar comandos case-insensitive; aceitar variações ("aprovar", "ok", "sim", "enviar")
- **Arquivo:** `feature_1_ia_personalizada/api/routes/webhook_whatsapp.py`
- **Critério:** aprovação em 2 respostas pelo WhatsApp; cliente recebe resposta corretamente

#### 6.8 — SLA e alertas de escalação pendente

- [ ] Em `feature_1_ia_personalizada/workers/mensagens_relacionamento.py`, adicionar task `verificar_escalacoes_pendentes`:
  - Schedule: a cada 30 minutos
  - Busca `interacoes` com `escalacao_status=pendente` há mais de 2h
  - Envia lembrete para advogado: "Você tem uma escalação pendente de {nome_cliente} há {X} horas."
  - Se > 24h: alerta para admin do escritório
- [ ] Adicionar métrica Prometheus: `escalacoes_pendentes_gauge` por `escritorio_id`
- **Arquivo:** `feature_1_ia_personalizada/workers/mensagens_relacionamento.py`
- **Critério:** nenhuma escalação fica sem resposta por mais de 24h sem alerta

#### 6.9 — Testes

- [ ] `feature_1_ia_personalizada/tests/unit/test_escalacao_detector.py` — todas as intencoes da lista detectadas; fallback semântico funciona; custo extra de token correto
- [ ] `feature_1_ia_personalizada/tests/unit/test_escalacao_contexto.py` — mensagem formatada corretamente; sugestão Claude mockada
- [ ] `feature_1_ia_personalizada/tests/integration/test_escalacao_fluxo.py` — fluxo completo: mensagem cliente → detectada → advogado notificado → aprovação → cliente recebe resposta

---

## Sprint 3 — Diferenciação Estrutural (Features 1 e 4)

---

### Feature 1 — RAG Jurisprudencial por Escritório

**Objetivo:** cada escritório tem sua própria "inteligência acumulada" em base vetorial. A IA responde com contexto real do escritório. Diferencial de lock-in: quanto mais usa, mais difícil sair.

#### 1.1 — Ativar extensão pgvector no PostgreSQL

- [x] Criar `alembic/versions/007_add_pgvector.py`
- [x] `CREATE EXTENSION IF NOT EXISTS vector`
- [x] Criar tabela `documentos_rag`:
  ```sql
  CREATE TABLE documentos_rag (
      id            SERIAL PRIMARY KEY,
      escritorio_id INTEGER NOT NULL REFERENCES escritorios(id) ON DELETE CASCADE,
      titulo        VARCHAR(500) NOT NULL,
      tipo          VARCHAR(50) NOT NULL,  -- 'peticao'|'sentenca'|'jurisprudencia'|'tese'|'parecer'
      conteudo      TEXT NOT NULL,
      embedding     vector(1536) NOT NULL,
      metadata_json JSONB DEFAULT '{}',    -- tribunal, vara, tipo_acao, data_doc, resultado, tags
      chunk_index   SMALLINT DEFAULT 0,    -- posição do chunk no doc original
      doc_hash      VARCHAR(64),           -- SHA256 do doc para detectar duplicatas
      ativo         BOOLEAN DEFAULT TRUE,
      created_at    TIMESTAMPTZ DEFAULT NOW(),
      updated_at    TIMESTAMPTZ DEFAULT NOW()
  );
  ```
- [x] Índices:
  ```sql
  CREATE INDEX ON documentos_rag USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
  CREATE INDEX ON documentos_rag (escritorio_id, tipo, ativo);
  CREATE INDEX ON documentos_rag (doc_hash);  -- deduplicação
  ```
- **Arquivo:** `alembic/versions/007_add_pgvector.py`
- **Critério:** tabela criada; índice IVFFlat funcional; `doc_hash` previne duplicatas

#### 1.2 — Serviço `EmbeddingGenerator`

- [x] Criar `feature_1_ia_personalizada/services/rag/embeddings.py`
- [x] Classe `EmbeddingGenerator`:
  - Usa **`claude-3-5-haiku`** para embeddings via API Anthropic (mais barato; dimensão 1536)
  - Fallback: Voyage AI (`voyage-law-2` — especializado em textos jurídicos; ativar com env var `VOYAGE_API_KEY`)
  - Método `gerar(texto: str) -> list[float]`: retorna vetor 1536D
  - Método `gerar_batch(textos: list[str]) -> list[list[float]]`: paraleliza com `asyncio.gather` (máx 10 concurrent)
- [x] **Eficiência:** batch de embeddings reduz latência total; usar semáforo para limitar concorrência e não estourar rate limit
- [x] **Cache:** hash do texto como chave no Redis (TTL 7 dias) — mesmo chunk do mesmo texto não gera embedding novamente
- **Arquivo:** `feature_1_ia_personalizada/services/rag/embeddings.py`
- **Critério:** batch de 20 chunks < 5s; embedding cacheado reutilizado corretamente; fallback para Voyage funciona

#### 1.3 — Pipeline de Ingestão `DocumentoIngester`

- [x] Criar `feature_1_ia_personalizada/services/rag/ingestion.py`
- [x] Classe `DocumentoIngester`:
  - `ingerir_pdf(arquivo_bytes, escritorio_id, metadata) -> IngestaoResultado`:
    1. Extrai texto com `PyMuPDF` (fitz)
    2. Limpa texto: remove cabeçalhos de rodapé, numeração de página, artefatos de scan
    3. Chunking: 512 tokens, 50 tokens de overlap (usa `langchain_text_splitters.RecursiveCharacterTextSplitter`)
    4. Calcula `doc_hash = SHA256(conteudo_original)` — verifica duplicata antes de prosseguir
    5. Gera embeddings em batch via `EmbeddingGenerator`
    6. Salva todos os chunks em `documentos_rag` em transação única
  - `ingerir_texto(texto, escritorio_id, titulo, tipo, metadata)`: mesmo fluxo sem etapa 1
- [x] **Inteligência:** extrair metadados automaticamente do PDF (tribunal, número CNJ, data, tipo de ação) via regex + Claude (somente para campos não encontrados por regex)
- [x] **Performance:** ingestão de PDF 10 páginas < 15s (processamento + embeddings)
- **Arquivo:** `feature_1_ia_personalizada/services/rag/ingestion.py`
- **Critério:** deduplicação por hash funciona; chunks com overlap correto; metadados extraídos automaticamente

#### 1.4 — Serviço `VectorStore`

- [x] Criar `feature_1_ia_personalizada/services/rag/vector_store.py`
- [x] Classe `VectorStore`:
  - `buscar(query_embedding, escritorio_id, top_k=5, filtros=None) -> list[DocumentoRAG]`:
    - Query pgvector: `ORDER BY embedding <=> $1 LIMIT $2`
    - Filtros opcionais: `tipo`, `tribunal`, `tipo_acao` (via `metadata_json @> '...'`)
    - **Performance:** query com índice IVFFlat retorna em < 50ms
  - `buscar_por_texto(query_texto, escritorio_id, top_k=5) -> list[DocumentoRAG]`:
    - Gera embedding da query → chama `buscar()`
    - **Cache:** chave `rag_search:{hash(query)}:{escritorio_id}` no Redis (TTL 30min)
  - `deletar_documento(doc_hash, escritorio_id)`: soft delete (`ativo=False`) para todos os chunks do doc
- **Arquivo:** `feature_1_ia_personalizada/services/rag/vector_store.py`
- **Critério:** busca retorna documentos relevantes; cache funciona; filtros por tipo corretos

#### 1.5 — Interface `RAGRetriever`

- [x] Criar `feature_1_ia_personalizada/services/rag/retriever.py`
- [x] Classe `RAGRetriever` — interface de alto nível para o orquestrador:
  - `buscar(query, escritorio_id, contexto_processo=None) -> str`:
    - Chama `VectorStore.buscar_por_texto()`
    - Formata os chunks encontrados em texto estruturado para injeção no prompt
    - **Inteligência — Re-ranking:** dos top_k=10 candidatos, usa similaridade cruzada para selecionar os 3 mais complementares entre si (não apenas os 3 mais próximos da query — evita redundância)
    - Se `contexto_processo` fornecido, filtra preferindo docs do mesmo `tipo_acao`
    - Retorna string vazia se nenhum doc relevante (similaridade mínima > 0.75)
  - Threshold de relevância configurável em `constants.py`: `RAG_MIN_SIMILARITY = 0.75`
- **Arquivo:** `feature_1_ia_personalizada/services/rag/retriever.py`
- **Critério:** re-ranking funciona; contexto irrelevante não polui o prompt (threshold)

#### 1.6 — Novo nó RAG no Orquestrador

- [x] Em `feature_1_ia_personalizada/services/ai/orchestrator.py`, adicionar nó `buscar_contexto_rag`:
  - Posição: entre `buscar_dados` e `gerar_resposta`
  - Chama `RAGRetriever.buscar(mensagem, escritorio_id, processo)`
  - Salva em `state["contexto_rag"]`
  - **Performance:** executado em paralelo com `buscar_dados` via `asyncio.gather` — não adiciona latência ao caminho crítico
- [x] Em `gerar_resposta`, injetar `{contexto_escritorio}` nos prompts onde aplicável (status, perspectivas, dúvida geral)
- [x] Se `contexto_rag` vazio: gera resposta normalmente sem menção ao RAG
- **Arquivo:** `feature_1_ia_personalizada/services/ai/orchestrator.py`
- **Critério:** RAG não adiciona latência perceptível (paralelo); prompt só recebe contexto quando relevante

#### 1.7 — Rota de gerenciamento RAG

- [x] Criar `feature_1_ia_personalizada/api/routes/rag.py`
- [x] Endpoints:
  - `POST /rag/upload` — Upload de PDF/DOCX/TXT; dispara task Celery de ingestão; retorna `job_id`
  - `GET /rag/status/{job_id}` — Status da ingestão (pendente/processando/concluído/erro)
  - `GET /rag/documentos` — Lista documentos do escritório (paginado, filtros por tipo)
  - `DELETE /rag/documentos/{doc_hash}` — Remove documento (soft delete)
  - `POST /rag/buscar` — Testa busca semântica (uso interno/debug)
- [x] Validação: só aceita arquivos < 50MB; tipos permitidos em `constants.py`
- [x] **Segurança:** todos os endpoints protegidos por JWT + `escritorio_id` do token
- **Arquivo:** `feature_1_ia_personalizada/api/routes/rag.py`
- **Critério:** upload funciona; task Celery disparada; status rastreável

#### 1.8 — Worker Celery de ingestão

- [x] Criar `feature_1_ia_personalizada/workers/ingest_documentos.py`
- [x] Task `ingest_documento(arquivo_path, escritorio_id, metadata, job_id)`:
  - Fila: `ia` (já existente)
  - Chama `DocumentoIngester.ingerir_pdf()`
  - Atualiza status do job no Redis: `job:{job_id}` → `{status, chunks, erro}`
  - Em caso de erro: envia para `dead_letter` queue (padrão existente)
- [x] Task `ingest_jurisprudencia_publica(tipo_acao, tribunal, escritorio_id)`:
  - Busca jurisprudência no DataJud e JusBrasil para o tipo/tribunal
  - Ingere automaticamente como contexto base para escritórios novos
  - **Inteligência:** executado no onboarding (Feature 4) para pré-popular a base
- **Arquivo:** `feature_1_ia_personalizada/workers/ingest_documentos.py`
- **Critério:** ingestão assíncrona; status rastreável; dead letter em caso de falha

#### 1.9 — Adicionar dependências

- [x] Em `requirements-f1.txt`:
  ```
  pgvector==0.3.2
  PyMuPDF==1.24.0
  ```
- [x] Verificar `langchain-text-splitters` já incluso via `langchain==0.2.16`
- **Arquivo:** `requirements-f1.txt`

#### 1.10 — Testes

- [x] `feature_1_ia_personalizada/tests/unit/test_embeddings.py` — geração, cache, batch, fallback Voyage
- [x] `feature_1_ia_personalizada/tests/unit/test_ingestion.py` — chunking correto; deduplicação por hash; extração de metadados
- [x] `feature_1_ia_personalizada/tests/unit/test_retriever.py` — re-ranking; threshold de relevância; contexto vazio quando sem match
- [x] `feature_1_ia_personalizada/tests/integration/test_rag_pipeline.py` — upload → ingestão → busca → resposta com contexto RAG

---

### Feature 4 — Módulo de Onboarding Automatizado do Escritório

**Objetivo:** escritório vai do zero ao operacional em 30 minutos, sem intervenção manual. Transforma o produto de consultivo para escalável.

#### 4.1 — Migração SQL: campos de onboarding e persona

- [ ] Criar `alembic/versions/008_add_onboarding_fields.py`
- [ ] Adicionar em `escritorios`:
  ```sql
  ALTER TABLE escritorios
      ADD COLUMN persona_nome        VARCHAR(100) DEFAULT 'Assistente Jurídico',
      ADD COLUMN persona_tom         VARCHAR(50)  DEFAULT 'formal',
      ADD COLUMN horario_inicio      TIME         DEFAULT '08:00',
      ADD COLUMN horario_fim         TIME DEFAULT '18:00',
      ADD COLUMN onboarding_etapa    SMALLINT DEFAULT 0,
      ADD COLUMN onboarding_completo BOOLEAN  DEFAULT FALSE,
      ADD COLUMN onboarding_at       TIMESTAMPTZ DEFAULT NULL,
      ADD COLUMN template_boas_vindas  TEXT DEFAULT NULL,
      ADD COLUMN template_atualizacao  TEXT DEFAULT NULL,
      ADD COLUMN template_sem_novidade TEXT DEFAULT NULL;
  ```
- **Arquivo:** `alembic/versions/008_add_onboarding_fields.py`
- **Critério:** migração com defaults; escritórios existentes não quebram

#### 4.2 — Atualizar modelo e schema de `Escritorio`

- [ ] Adicionar campos em `shared/models/escritorio.py`
- [ ] Atualizar `shared/schemas/escritorio.py` com novos campos + validações:
  - `persona_tom`: enum `formal|amigavel|neutro`
  - `horario_inicio/fim`: validação de formato HH:MM
  - `template_boas_vindas`: máx 500 chars; obrigatório conter `{nome_cliente}`
- **Arquivos:** `shared/models/escritorio.py`, `shared/schemas/escritorio.py`
- **Critério:** Pydantic valida campos; schema exportado na OpenAPI

#### 4.3 — Rotas de Onboarding

- [ ] Criar `feature_1_ia_personalizada/api/routes/onboarding.py`
- [ ] Implementar endpoints:

  **`POST /onboarding/register`** — público (sem JWT)
  - Recebe: `nome_escritorio`, `cnpj`, `email_admin`, `senha`, `nome_responsavel`, `oab_responsavel`
  - Valida CNPJ via `validators.py` (já existe)
  - Cria `Escritorio` + `Usuario` (role=admin) em transação única
  - Envia email de boas-vindas (via Celery — não bloqueia)
  - Retorna JWT do admin criado
  - **Idempotência:** CNPJ único; retorna 409 se já cadastrado

  **`POST /onboarding/configure-ia`** — requer JWT admin
  - Recebe: `persona_nome`, `persona_tom`, `horario_inicio`, `horario_fim`
  - Gera preview da mensagem de boas-vindas com os parâmetros escolhidos
  - Avança `onboarding_etapa` para 1
  - Retorna: `{"preview": "Olá João! Sou Dra. Ana, assistente do Escritório Silva..."}`

  **`POST /onboarding/import-processos`** — requer JWT admin
  - Aceita CSV multipart ou URL de Google Sheets
  - Chama `admin_import.py` internamente (reutiliza toda a lógica existente)
  - Retorna relatório: total importado, erros, CNJs inválidos
  - Avança `onboarding_etapa` para 2

  **`POST /onboarding/connect-whatsapp`** — requer JWT admin
  - Chama `evolution_client.py` para criar instância
  - Retorna QR Code base64 para o front exibir
  - Polling: `GET /onboarding/whatsapp-status` verifica conexão (pool de 30s no frontend)
  - Ao conectar: avança `onboarding_etapa` para 3

  **`POST /onboarding/configure-templates`** — requer JWT admin
  - Salva templates customizados (validação de variáveis obrigatórias)
  - Templates padrão carregados de `disclaimers.json` se não fornecidos
  - Avança `onboarding_etapa` para 4

  **`POST /onboarding/go-live`** — requer JWT admin
  - Ativa `monitoramento_ativo=True` para todos os processos importados
  - Dispara task Celery de boas-vindas para todos os clientes
  - **Feature 1 (RAG):** dispara `ingest_jurisprudencia_publica` para tipos de ação mais comuns do escritório
  - Define `onboarding_completo=True` + `onboarding_at=now()`
  - Avança `onboarding_etapa` para 5

  **`GET /onboarding/status`** — requer JWT admin
  - Retorna checklist completo: qual etapa atual, o que falta, % completo

- **Arquivo:** `feature_1_ia_personalizada/api/routes/onboarding.py`
- **Critério:** escritório do zero ao operacional em < 30 minutos seguindo o fluxo

#### 4.4 — Injetar `persona_nome` e `persona_tom` nos prompts

- [ ] Em `feature_1_ia_personalizada/services/ai/prompts.py`, atualizar `SYSTEM_PROMPT_BASE`:
  - Receber `persona_nome` e `persona_tom` como parâmetros
  - Tom `formal`: linguagem respeitosa, "o senhor/a senhora"
  - Tom `amigavel`: "você", linguagem leve mas profissional
  - Tom `neutro`: padrão atual
- [ ] Em `feature_1_ia_personalizada/services/ai/orchestrator.py`, carregar persona do escritório no início do fluxo (já tem `escritorio_id` no state)
- [ ] **Cache:** dados da persona cacheados no Redis por 1h (mudam raramente)
- **Arquivos:** `feature_1_ia_personalizada/services/ai/prompts.py`, `feature_1_ia_personalizada/services/ai/orchestrator.py`
- **Critério:** persona aplicada em todas as respostas; troca de tom sem reiniciar serviço

#### 4.5 — Templates personalizados de mensagem

- [ ] Em `feature_1_ia_personalizada/services/messaging/templates.py`, criar `carregar_templates(escritorio_id)`:
  - Carrega templates do banco se customizados, senão usa defaults de `disclaimers.json`
  - Cache Redis por 1h
- [ ] Substituir uso hardcoded de templates em `scheduler.py` e `mensagens_relacionamento.py` por esta função
- **Arquivos:** `feature_1_ia_personalizada/services/messaging/templates.py`, `feature_1_ia_personalizada/workers/mensagens_relacionamento.py`
- **Critério:** cada escritório usa seu template; default funciona se não customizado

#### 4.6 — Testes

- [ ] `feature_1_ia_personalizada/tests/unit/test_onboarding_register.py` — validação CNPJ; duplicata retorna 409; usuário admin criado com role correto
- [ ] `feature_1_ia_personalizada/tests/unit/test_persona_prompts.py` — tom formal gera linguagem diferente de amigavel; persona injetada no prompt
- [ ] `feature_1_ia_personalizada/tests/integration/test_onboarding_fluxo.py` — fluxo completo das 5 etapas; go-live ativa monitoramento

---

## Melhorias de Performance e Inteligência Transversais

> Aplicar junto com as features acima. Tornam o sistema mais rápido e inteligente globalmente.

### P1 — Paralelismo no Orquestrador

- [ ] Em `feature_1_ia_personalizada/services/ai/orchestrator.py`, executar em paralelo com `asyncio.gather`:
  - `buscar_dados()` (Jusbrasil/DataJud)
  - `buscar_contexto_rag()` (Feature 1)
  - `get_state()` do ProcessoStateManager (Feature 3)
- [ ] Resultado: latência do caminho busca+RAG+estado = max(latências) em vez de soma
- **Critério:** latência total do orquestrador reduzida em ~40% para mensagens de status

### P2 — Prefetch de contexto no worker de monitoramento

- [ ] Em `monitor_processos.py`, ao detectar andamento, iniciar em paralelo:
  - Atualizar banco
  - Gerar embedding do novo andamento (Feature 1)
  - Recalcular score de risco (Feature 2)
  - Atualizar estado do processo (Feature 3)
- [ ] Único `session.commit()` no final com todas as mudanças
- **Critério:** worker não aumenta tempo por processo mesmo com 3 features novas

### P3 — Cache inteligente de contexto do escritório

- [ ] Criar chave Redis `escritorio_ctx:{escritorio_id}` com TTL 1h contendo:
  - `persona_nome`, `persona_tom`, `horario_inicio`, `horario_fim`
  - Templates carregados
  - Score médio de risco dos processos ativos
- [ ] Evita queries ao banco em todo request de chat
- **Arquivo:** `feature_1_ia_personalizada/services/ai/orchestrator.py`
- **Critério:** requests de chat não fazem query ao banco para dados estáticos do escritório

### P4 — Warm-up de embeddings frequentes

- [ ] No startup da aplicação (`feature_1_ia_personalizada/api/app.py`), pré-aquecer embeddings das intenções mais comuns:
  - "qual o status do meu processo", "quando vai terminar", "o que aconteceu"
  - Salvar no Redis com TTL 24h
- [ ] RAGRetriever usa embeddings pre-computados para queries de intent comum
- **Critério:** primeira busca RAG do dia não gera embedding (usa cache aquecido)

---

## Qualidade e Padrões (Obrigatório em Todas as Features)

- [ ] Toda nova funcionalidade com testes: unitário + integração (cobertura mínima 70%)
- [ ] Toda nova tabela com migração Alembic reversível (`upgrade` + `downgrade`)
- [ ] Todo novo endpoint documentado no OpenAPI (FastAPI gera automaticamente via Pydantic)
- [ ] Todo novo serviço com métricas Prometheus (latência + erros)
- [ ] Nenhum dado de cliente em logs (padrão LGPD já estabelecido)
- [ ] Todo dado multi-tenant filtrado por `escritorio_id` (usar `TenantMixin`)
- [ ] Disclaimer OAB em toda resposta sobre resultado ou prazo
- [ ] Variáveis de ambiente novas documentadas em `.env.example`
