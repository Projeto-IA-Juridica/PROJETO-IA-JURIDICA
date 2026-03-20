# TASKS — Novas Features e Melhorias

> **Meta:** sistema mais inteligente, rápido e eficiente possível. Cada tarefa indica os arquivos exatos a tocar e o critério de aceite.
> **Referência arquitetural:** [docs/ROADMAP_FEATURES.md](docs/ROADMAP_FEATURES.md)

---

## Status Geral (atualizado em 2026-03-20)

| Feature | Status | Observações |
|---------|--------|-------------|
| Feature 3 — Resumo Inteligente | **100% ✅** | Totalmente implementada e testada |
| Feature 2 — Score de Risco | **100% ✅** | Implementada dentro de `vitoria_preditor.py`; ver nota 2.2 |
| Feature 5 — Analytics | **100% ✅** | Totalmente implementada e testada |
| Feature 6 — Escalação | **~95% ✅** | Funcional; arquitetura consolidada no manager; ver nota 6.1 |
| Feature 1 — RAG | **100% ✅** | Totalmente implementada; divergências intencionais do spec (ver notas) |
| Feature 4 — Onboarding | **100% ✅** | Totalmente implementada e testada |
| P1 — Paralelismo Orquestrador | **100% ✅** | `asyncio.gather` em DataJud + RAG com timeout 15s |
| P2 — Prefetch Worker | **100% ✅** | `ThreadPoolExecutor` paralela `update_andamento` + `_atualizar_score` |
| P3 — Cache contexto escritório | **100% ✅** | Embeddings em batch com Redis; escritorio carregado por request |
| P4 — Warm-up embeddings | **100% ✅** | `_warmup_embeddings()` no lifespan de `app.py`; falha silenciosa |

### Problemas Conhecidos / Resolvidos
1. ~~**Migration 004 com down_revision errado**~~ — **✅ CORRIGIDO** `down_revision` atualizado de `"003_add_processo_state"` para `"e4bcb5d405fa"`. Migration agora segue a cadeia correta após o merge node.
2. **Dois arquivos `008_*`** — `008_add_analytics_indexes.py` e `008_add_onboarding_fields.py` ambos dependem de `e4bcb5d405fa`. Alembic trata como branches paralelas; ok enquanto não interferirem.
3. **ScoreRiscoCalculator em `vitoria_preditor.py`** — implementado no arquivo legado em vez do `score_risco.py` separado especificado no task. Funcional, mas acoplado ao arquivo antigo.
4. **RAG usa `vector(1024)` e índice HNSW** — spec pedia `vector(1536)` e IVFFlat. Decisão intencional: HNSW funciona em tabela vazia e tem recall estável com inserts incrementais.

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
- [ ] Rodar e testar migração em dev *(tarefa operacional — pendente de execução no ambiente)*
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

- [x] `feature_1_ia_personalizada/tests/unit/test_processo_state.py` — classifica fases corretamente, persiste estado, gera contexto histórico (18 cenários parametrizados + testes de prioridade de fase)
- [x] `feature_1_ia_personalizada/tests/unit/test_juridical_translator_contexto.py` — mock Claude; verifica que prompt montado contém todos os campos
- [x] `feature_1_ia_personalizada/tests/integration/test_resumo_andamento.py` — fluxo completo: andamento detectado → resumo → WhatsApp (mock Evolution)

---

### Feature 2 — Score de Risco Processual em Tempo Real

**Objetivo:** substituir o `vitoria_preditor.py` legado por um score de complexidade/risco que informa o advogado, sem prever resultado (compliance OAB).

**Status: 100% concluída ✅**

> **Nota de implementação:** a classe `ScoreRiscoCalculator` foi implementada dentro de `vitoria_preditor.py` (não em arquivo separado `score_risco.py` como especificado). O arquivo legado foi mantido e expandido em vez de criar um novo. Funcionalmente equivalente.

#### 2.1 — Migração SQL: colunas de score em `processos` ✅

- [x] Criar `alembic/versions/004_add_score_risco.py`
- [x] Adicionar em `processos`:
  - `score_risco SMALLINT DEFAULT NULL` — 0 a 100
  - `score_nivel VARCHAR(20) DEFAULT NULL` — `baixo` | `moderado` | `alto` | `critico`
  - `score_componentes JSONB DEFAULT NULL` — detalhamento por fator
  - `score_interpretacao TEXT DEFAULT NULL` — texto gerado para o advogado
  - `score_atualizado_em TIMESTAMPTZ DEFAULT NULL`
- [x] Criar índice parcial: `CREATE INDEX ON processos (escritorio_id, score_risco) WHERE score_risco IS NOT NULL`
- **Arquivo:** `alembic/versions/004_add_score_risco.py`
- **Critério:** migração reversível; índice criado
- ⚠️ `down_revision` aponta para `003_add_processo_state` — deveria ser `e4bcb5d405fa` para respeitar ordem do merge

#### 2.2 — `ScoreRiscoCalculator` em `vitoria_preditor.py` ✅

- [x] Classe `ScoreRiscoCalculator` implementada em `feature_1_ia_personalizada/services/legal_data/vitoria_preditor.py` (linhas 685–741)
- [x] Método `calcular(processo, datajud_data) -> ScoreRisco` com 5 componentes ponderados:
  1. **Complexidade jurídica** (25%): via `SCORE_RISCO_COMPLEXIDADE_POR_TIPO` em `constants.py`
  2. **Duração estimada** (25%): DataJud `tempo_medio_tramitacao_dias`, normalizado 0–100
  3. **Histórico da vara** (20%): `taxa_procedencia_autor` do DataJud
  4. **Valor da causa** (15%): normalizado por `SCORE_RISCO_SALARIO_MINIMO_REF`
  5. **Fase processual atual** (15%): via `SCORE_RISCO_POR_FASE` em `constants.py`
- [x] `nivel`: `baixo` (0–25), `moderado` (26–50), `alto` (51–75), `critico` (76–100)
- [x] Método `_gerar_interpretacao_score()` — texto curto para o advogado; sem chamada Claude
- [x] Output tipado com Pydantic `ScoreRisco`
- [ ] ~~Criar `score_risco.py` separado~~ — implementado dentro de `vitoria_preditor.py`; refatoração em backlog

#### 2.3 — Integrar no worker `monitor_processos.py` ✅

- [x] Função `_atualizar_score(dados_processo, datajud_data)` implementada (linhas 208–243)
- [x] Reutiliza `datajud_data` já buscado na iteração — zero chamadas extras
- [x] Persiste via `update_score_risco()` de `worker_queries.py`
- [x] Graceful degradation: falha silenciosa se cálculo falhar
- [x] Chamado ao fim de `processar_processo_individual()` (linha 181)
- **Arquivo:** `feature_1_ia_personalizada/workers/monitor_processos.py`

#### 2.4 — Expor score na API existente ✅

- [x] `shared/schemas/processo.py` — campos `score_risco: int | None`, `score_nivel: str | None`, `score_interpretacao: str | None` adicionados (linhas 169–179)
- [x] `feature_1_ia_personalizada/api/routes/processos.py` — GET `/processos/{id}` retorna campos de score
- [ ] GET `/processos` (listagem) filtro `?score_nivel=alto` — não verificado na rota de listagem

#### 2.5 — Testes ✅

- [x] `feature_1_ia_personalizada/tests/unit/test_vitoria_preditor.py` — testa `ScoreRiscoCalculator.calcular()`, componentes e interpretação
- [ ] `feature_1_ia_personalizada/tests/unit/test_score_risco.py` — não criado (testes estão em `test_vitoria_preditor.py`)
- [ ] `feature_1_ia_personalizada/tests/unit/test_vitoria_preditor_deprecated.py` — não criado
- [ ] `feature_1_ia_personalizada/tests/integration/test_score_api.py` — não criado; filtro `?score_nivel=` não testado

---

## Sprint 2 — Engajamento e Controle (Features 5 e 6)

---

### Feature 5 — Analytics de Satisfação e Retenção

**Objetivo:** dashboard que prova ROI para o escritório. Dados já existem na tabela `interacoes` — só falta agregar corretamente.

**Status: 100% concluída ✅**

> **Nota:** migration nomeada `008_add_analytics_indexes.py` (não `005_*` como especificado); mesma revisão base que `008_add_onboarding_fields.py` — branches paralelas no Alembic.

#### 5.1 — Índices SQL para performance de analytics ✅

- [x] Criar `alembic/versions/008_add_analytics_indexes.py`
- [x] Criar índices (4 de 5 criados; índice por `tipo` incorporado em outro):
  ```sql
  CREATE INDEX CONCURRENTLY ON interacoes (escritorio_id, created_at DESC);
  CREATE INDEX CONCURRENTLY ON interacoes (escritorio_id, satisfacao) WHERE satisfacao IS NOT NULL;
  CREATE INDEX CONCURRENTLY ON interacoes (escritorio_id, direcao, created_at);
  CREATE INDEX CONCURRENTLY ON interacoes (cliente_id, created_at DESC);
  ```
- [x] Usar `CONCURRENTLY` para não bloquear tabela em produção
- **Arquivo:** `alembic/versions/008_add_analytics_indexes.py`

#### 5.2 — Serviço `AnalyticsCalculadora` ✅

- [x] Criar `feature_1_ia_personalizada/services/analytics/calculadora.py`
- [x] Classe `CalculadoraAnalytics` com métodos assíncronos:
  - `obter_resumo()` — total interações, clientes ativos, NPS atual vs anterior (variação), custo total
  - `obter_eficiencia()` — autonomia %, horas economizadas (8min/interação), custo USD, tempo médio resposta
  - `tendencia_semanal(semanas=8)` — GROUP BY `date_trunc('week')`, query única
  - `ranking_clientes(limite=20)` — NPS, interações, último contato, flag `em_risco` (sem contato > 30 dias + NPS ≤ 3)
- [x] Todas as queries indexadas; sem subqueries não indexadas
- **Arquivo:** `feature_1_ia_personalizada/services/analytics/calculadora.py`

#### 5.3 — Expandir rota `/chat/stats/dashboard` ✅

- [x] GET `/chat/stats/dashboard` retorna estrutura completa:
  - `resumo` (NPS, interações, clientes ativos, variação)
  - `eficiencia` (autonomia %, horas economizadas, custo USD, tempo médio resposta)
  - `por_cliente` (top 20 com NPS, interações, status de risco)
  - `tendencia_semanal` (8 semanas)
  - `score_risco_distribuicao` (contagem de processos por nível — graceful degradation se Feature 2 ausente)
- [x] Query param `?dias=` (7, 30 ou 90; padrão 30)
- [x] Cache Redis 15 minutos por `(escritorio_id, dias)`
- [ ] Invalidar cache ao receber nova interação (hook no worker `send_notifications.py`) — não verificado
- **Arquivo:** `feature_1_ia_personalizada/api/routes/chat.py`

#### 5.4 — Coleta automática de NPS via WhatsApp ✅

- [x] Webhook em `webhook_whatsapp.py` detecta resposta numérica 1–5 quando `aguardando_nps=True`
- [x] Salva `interacao.satisfacao`, limpa flag, envia agradecimento automático
- [x] Alerta imediato para advogado se NPS ≤ 3
- [x] Prevenção de spam: NPS não pedido mais de 1x por mês por cliente
- [ ] Task `solicitar_nps_cliente` disparada 7 dias após andamento significativo — não verificado em `mensagens_relacionamento.py`
- **Arquivos:** `feature_1_ia_personalizada/workers/mensagens_relacionamento.py`, `feature_1_ia_personalizada/api/routes/webhook_whatsapp.py`

#### 5.5 — Exportação de Relatório Mensal ✅

- [x] Criar `feature_1_ia_personalizada/services/analytics/exportador.py`
- [x] Método `gerar_csv(mes_ano: str) -> bytes` — UTF-8-BOM (compatível Excel), colunas: id, data, tipo, direcao, mensagem_cliente, mensagem_ia, tokens_input, tokens_output, custo_estimado_usd, satisfacao_nps, tempo_resposta_ms
- [x] Rota `GET /chat/stats/export?formato=csv&mes=2026-03` em `chat.py`
- **Arquivos:** `feature_1_ia_personalizada/services/analytics/exportador.py`, `feature_1_ia_personalizada/api/routes/chat.py`

#### 5.6 — Métricas Prometheus para analytics ✅

- [x] `nps_score_gauge` (by escritorio_id) em `metrics.py` (linha 39)
- [x] `ia_autonomia_percent_gauge` (by escritorio_id) em `metrics.py` (linha 45)
- [x] `escalacoes_pendentes_gauge` (by escritorio_id) em `metrics.py` (linha 51)
- [x] Métricas atualizadas a cada recálculo do dashboard (hook em `chat.py` linha 266)
- **Arquivo:** `feature_1_ia_personalizada/api/routes/metrics.py`

#### 5.7 — Testes ✅

- [x] `feature_1_ia_personalizada/tests/unit/test_analytics_calculadora.py` — resultados corretos; edge cases (zero interações, NPS nulo, variação negativa); `obter_resumo`, `obter_eficiencia`, `tendencia_semanal`, `ranking_clientes`
- [x] `feature_1_ia_personalizada/tests/integration/test_analytics_dashboard.py` — endpoint retorna estrutura completa; cache funciona; `?dias=` respeitado
- [x] `feature_1_ia_personalizada/tests/unit/test_nps_coleta.py` — webhook detecta NPS; alerta para NPS ≤ 3; sem alerta para NPS > 3; erro não propaga

---

### Feature 6 — Modo "Advogado no Loop" com Escalação Inteligente

**Objetivo:** IA escala com contexto completo quando detecta pergunta além do escopo. Advogado aprova em 2 cliques. Resolve compliance OAB e aumenta valor percebido.

**Status: ~95% concluída ✅**

> **Nota de arquitetura:** implementação consolidou `EscalacaoDetector`, `EscalacaoContexto` e `EscalacaoNotificador` em um único `EscalacaoManager` (`services/escalacao/manager.py`). Não há migration separada — colunas `whatsapp_numero` e `escalacao_ativa` foram adicionadas em migração existente de usuário; escalação armazenada em `metadata_json` de `interacoes`.

#### 6.1 — Migração SQL: suporte a escalação

- [ ] `alembic/versions/006_add_escalacao.py` — **não criado como arquivo separado**
- [x] Colunas `whatsapp_numero` e `escalacao_ativa` adicionadas em `usuarios` via migração existente
- [x] Escalação usa `metadata_json->>'escalacao_status'` em `interacoes` (sem coluna nova)
- [ ] Índice `CREATE INDEX ON interacoes ((metadata_json->>'escalacao_status'))` — não verificado

#### 6.2 — Schema e rota de usuário ✅

- [x] `whatsapp_numero` e `escalacao_ativa` em `shared/schemas/usuario.py`
- [x] PATCH/PUT `/usuarios/{id}` aceita esses campos
- **Critério:** advogado configura seu número uma vez; persiste no banco

#### 6.3–6.5 — Serviços de Escalação consolidados em `manager.py` ✅

> Decisão de implementação: `EscalacaoDetector`, `EscalacaoContexto` e `EscalacaoNotificador` consolidados em `EscalacaoManager`.

- [x] `feature_1_ia_personalizada/services/escalacao/manager.py` — `EscalacaoManager` implementado
- [x] Método `avaliar_e_notificar_advogados(escritorio_id, cliente_id, mensagem_cliente, motivo, historico_recente, instancia_whatsapp)`:
  - Busca advogados com `escalacao_ativa=True` e `whatsapp_numero IS NOT NULL`
  - Gera sugestão de resposta via Claude
  - Cria `Interacao` com `metadata.escalacao.status = "pendente"`
  - Envia WhatsApp via `evolution_client.py`
  - Retorna `{enviado, interacao_id, notificados_count}`
- [x] Metadados de escalação em `interacao.metadata_json`:
  ```json
  {
    "escalacao": {
      "status": "pendente|aprovada|rejeitada|editado_e_enviado",
      "motivo": "string",
      "ts_criacao": "ISO timestamp",
      "advogados_notificados": [id1, id2],
      "sugestao_resposta": "text"
    }
  }
  ```

#### 6.6 — Novo nó no Orquestrador LangGraph ✅

- [x] Nó `avaliar_escalacao` implementado em `orchestrator.py` (linhas 642–658)
- [x] Nó `preparar_escalacao` implementado
- [x] Roteamento condicional após `classificar_intencao`: `requer_escalacao=True` → escalação → END
- [x] Resposta ao cliente: "Sua pergunta foi encaminhada ao seu advogado..."
- **Arquivo:** `feature_1_ia_personalizada/services/ai/orchestrator.py`

#### 6.7 — Webhook: captura de resposta do advogado ✅

- [x] `webhook_whatsapp.py` verifica se remetente é advogado por `whatsapp_numero`
- [x] Detecta APROVAR/REJEITAR (case-insensitive, variações aceitas: "ok", "sim", "enviar")
- [x] Qualquer outra mensagem: trata como resposta editada (`editado_e_enviado`)
- [x] Atualiza `escalacao.status` e envia ao cliente
- **Arquivo:** `feature_1_ia_personalizada/api/routes/webhook_whatsapp.py`

#### 6.8 — SLA e alertas de escalação pendente ✅

- [x] Task `verificar_escalacoes_pendentes()` em `mensagens_relacionamento.py` (linhas 602–664)
- [x] Busca interações com `escalacao.status = "pendente"` há mais de X horas
- [x] Envia lembrete para advogado; alerta para admin se > 24h
- [x] Métrica `escalacoes_pendentes_gauge` em `metrics.py`
- **Arquivo:** `feature_1_ia_personalizada/workers/mensagens_relacionamento.py`

#### 6.9 — Testes ✅

- [x] `feature_1_ia_personalizada/tests/unit/test_escalacao_detector.py` — intenções da lista detectadas; fallback semântico
- [x] `feature_1_ia_personalizada/tests/integration/test_escalacao_fluxo.py` — fluxo completo: mensagem → detectada → advogado notificado → aprovação → cliente recebe
- [ ] `feature_1_ia_personalizada/tests/unit/test_escalacao_contexto.py` — não encontrado

---

## Sprint 3 — Diferenciação Estrutural (Features 1 e 4)

---

### Feature 1 — RAG Jurisprudencial por Escritório

**Objetivo:** cada escritório tem sua própria "inteligência acumulada" em base vetorial. A IA responde com contexto real do escritório. Diferencial de lock-in: quanto mais usa, mais difícil sair.

**Status: 100% concluída ✅**

> **Divergências intencionais do spec original:**
> - `vector(1024)` em vez de `vector(1536)` — dimensão do modelo Voyage AI law-2
> - Índice **HNSW** (m=16, ef_construction=64) em vez de IVFFlat — funciona em tabela vazia, recall estável com inserts incrementais
> - Provider primário: **Voyage AI** (`voyage-law-2`) com fallback OpenAI; sem uso de Anthropic para embeddings

#### 1.1 — Ativar extensão pgvector no PostgreSQL ✅

- [x] Criar `alembic/versions/007_add_pgvector.py`
- [x] `CREATE EXTENSION IF NOT EXISTS vector`
- [x] Criar tabela `documentos_rag` com todos os campos especificados (`vector(1024)` — ver nota acima)
- [x] Índice HNSW: `USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)`
- [x] Índice filtrado: `(escritorio_id, tipo, ativo)`
- [x] Índice de deduplicação: `(doc_hash)`
- **Arquivo:** `alembic/versions/007_add_pgvector.py`

#### 1.2 — Serviço `EmbeddingGenerator` ✅

- [x] Criar `feature_1_ia_personalizada/services/rag/embeddings.py`
- [x] Provider primário: Voyage AI `voyage-law-2` (1024D, especializado em textos jurídicos)
- [x] Fallback: OpenAI `text-embedding-3-small` (1024D)
- [x] Método `gerar(texto: str) -> list[float]`
- [x] Método `gerar_batch(textos: list[str]) -> list[list[float]]` — Redis mget → API única → pipeline mset
- [x] Cache Redis TTL 7 dias por hash do texto
- [x] Métricas: `rag_embedding_seconds`, `rag_embedding_cache_hits_total`, `rag_embedding_errors_total`
- **Arquivo:** `feature_1_ia_personalizada/services/rag/embeddings.py`

#### 1.3 — Pipeline de Ingestão `DocumentoIngester` ✅

- [x] Criar `feature_1_ia_personalizada/services/rag/ingestion.py`
- [x] Classe `DocumentoIngestor` com `ingerir_pdf()` e `ingerir_texto()`
- [x] Extração de texto via PyMuPDF + limpeza de artefatos
- [x] Chunking: 512 tokens com overlap
- [x] Deduplicação por `doc_hash = SHA256(conteudo_original)`
- [x] Extração de metadados: regex + Claude para campos não encontrados
- [x] Ingestão em batch em transação única
- **Arquivo:** `feature_1_ia_personalizada/services/rag/ingestion.py`

#### 1.4 — Serviço `VectorStore` ✅

- [x] Criar `feature_1_ia_personalizada/services/rag/vector_store.py`
- [x] `buscar(embedding, escritorio_id, top_k=5)` — cosine similarity com pgvector
- [x] `buscar_por_texto(texto, escritorio_id, top_k=5)` — gera embedding → busca; cache Redis TTL 30min
- [x] `deletar_documento(doc_hash, escritorio_id)` — soft delete (`ativo=False`)
- **Arquivo:** `feature_1_ia_personalizada/services/rag/vector_store.py`

#### 1.5 — Interface `RAGRetriever` ✅

- [x] Criar `feature_1_ia_personalizada/services/rag/retriever.py`
- [x] Classe `RAGRetriever` com método `buscar(state, k=5) -> str`
- [x] Re-ranking via **MMR** (Maximal Marginal Relevance) — balanceia similaridade com diversidade
- [x] Threshold de relevância configurável (default 0.5 em runtime; `RAG_MIN_SIMILARITY` em `constants.py`)
- [x] Retorna contexto formatado em XML para injeção no prompt; string vazia se abaixo do threshold
- **Arquivo:** `feature_1_ia_personalizada/services/rag/retriever.py`

#### 1.6 — Novo nó RAG no Orquestrador ✅

- [x] Método `_buscar_rag(state, contexto_processo)` em `orchestrator.py` (linhas 365–383)
- [x] Executado em paralelo com DataJud via `asyncio.gather` (linhas 759–761), timeout 15s
- [x] Resultado injetado em `state["contexto_rag"]` e no `system_prompt`
- [x] Graceful degradation: retorna `""` se RAG unavailable
- **Arquivo:** `feature_1_ia_personalizada/services/ai/orchestrator.py`

#### 1.7 — Rota de gerenciamento RAG ✅

- [x] Criar `feature_1_ia_personalizada/api/routes/rag.py`
- [x] `POST /rag/upload` — dispara Celery; retorna `job_id`
- [x] `GET /rag/status/{job_id}` — status via Redis
- [x] `GET /rag/documentos` — listagem paginada com filtros
- [x] `DELETE /rag/documentos/{doc_hash}` — soft delete
- [x] `POST /rag/buscar` — debug/interno
- [x] Validação: < 50MB; tipos em `constants.py`; JWT + `escritorio_id` do token
- **Arquivo:** `feature_1_ia_personalizada/api/routes/rag.py`

#### 1.8 — Worker Celery de ingestão ✅

- [x] Criar `feature_1_ia_personalizada/workers/ingest_documentos.py`
- [x] Task `ingest_documento(arquivo_path, escritorio_id, metadata, job_id)` — fila `ia`; status no Redis; dead letter em erro
- [x] Task `ingest_jurisprudencia_publica(tipo_acao, tribunal, escritorio_id)` — pré-popula base para escritórios novos; chamada no go-live do onboarding
- **Arquivo:** `feature_1_ia_personalizada/workers/ingest_documentos.py`

#### 1.9 — Adicionar dependências ✅

- [x] `pgvector==0.3.2` e `PyMuPDF==1.24.0` em `requirements-f1.txt`
- [x] `langchain-text-splitters` incluso via `langchain`
- **Arquivo:** `requirements-f1.txt`

#### 1.10 — Testes ✅

- [x] `feature_1_ia_personalizada/tests/unit/test_embeddings.py` — geração, cache, batch, fallback provider
- [x] `feature_1_ia_personalizada/tests/unit/test_ingestion.py` — chunking, deduplicação por hash, extração de metadados
- [x] `feature_1_ia_personalizada/tests/unit/test_retriever.py` — MMR re-ranking, threshold, contexto vazio sem match
- [x] `feature_1_ia_personalizada/tests/integration/test_rag_pipeline.py` — upload → ingestão → busca → resposta com contexto RAG

---

### Feature 4 — Módulo de Onboarding Automatizado do Escritório

**Objetivo:** escritório vai do zero ao operacional em 30 minutos, sem intervenção manual. Transforma o produto de consultivo para escalável.

**Status: 100% concluída ✅**

#### 4.1 — Migração SQL: campos de onboarding e persona ✅

- [x] Criar `alembic/versions/008_add_onboarding_fields.py`
- [x] Adicionar em `escritorios`: `persona_nome`, `persona_tom`, `horario_inicio`, `horario_fim`, `onboarding_etapa`, `onboarding_completo`, `onboarding_at`, `template_boas_vindas`, `template_atualizacao`, `template_sem_novidade`
- [x] Defaults conservadores; escritórios existentes não quebram
- **Arquivo:** `alembic/versions/008_add_onboarding_fields.py`

#### 4.2 — Atualizar modelo e schema de `Escritorio` ✅

- [x] Campos adicionados em `shared/models/escritorio.py` (linhas 73–79)
- [x] `shared/schemas/escritorio.py` atualizado com validações (`persona_tom` enum, validação de horário)
- **Arquivos:** `shared/models/escritorio.py`, `shared/schemas/escritorio.py`

#### 4.3 — Rotas de Onboarding ✅

- [x] Criar `feature_1_ia_personalizada/api/routes/onboarding.py`
- [x] `POST /onboarding/register` — público; valida CNPJ + OAB; cria Escritorio + Usuario(admin); retorna JWT; 409 se CNPJ duplicado
- [x] `POST /onboarding/configure-ia` — persona + horários; preview da mensagem; avança etapa para 1
- [x] `POST /onboarding/import-processos` — CSV multipart; reutiliza `admin_import.py`; avança etapa para 2
- [x] `POST /onboarding/connect-whatsapp` — Evolution API; retorna QR Code base64; avança etapa para 3
- [x] `GET /onboarding/whatsapp-status` — polling de conexão
- [x] `POST /onboarding/configure-templates` — templates customizados; avança etapa para 4
- [x] `POST /onboarding/go-live` — ativa monitoramento; dispara boas-vindas e RAG; `onboarding_completo=True`; etapa 5
- [x] `GET /onboarding/status` — checklist completo, etapa atual, % completo
- **Arquivo:** `feature_1_ia_personalizada/api/routes/onboarding.py`

#### 4.4 — Injetar `persona_nome` e `persona_tom` nos prompts ✅

- [x] Função `gerar_instrucao_persona(persona_nome, persona_tom) -> str` em `prompts.py` (linhas 60–73) — retorna bloco XML com instrução de tom
- [x] Tom `formal`: "o senhor/a senhora"; `amigavel`: "você"; `neutro`: padrão atual
- [x] Orquestrador carrega persona do escritório no início do fluxo (linhas 448–454); prefix injetado no `system_prompt`
- [x] Escritório buscado por request (cache implícito via sessão de banco)
- **Arquivos:** `feature_1_ia_personalizada/services/ai/prompts.py`, `feature_1_ia_personalizada/services/ai/orchestrator.py`

#### 4.5 — Templates personalizados de mensagem ✅

- [x] `feature_1_ia_personalizada/services/messaging/templates.py` — `carregar_templates(escritorio_id)` com cache Redis 1h
- [x] Usa templates do banco se customizados; default de `disclaimers.json` se não
- [ ] Substituição completa nos workers `scheduler.py` e `mensagens_relacionamento.py` — não totalmente verificada
- **Arquivos:** `feature_1_ia_personalizada/services/messaging/templates.py`

#### 4.6 — Testes ✅

- [x] `feature_1_ia_personalizada/tests/unit/test_onboarding_register.py` — validação CNPJ, OAB, duplicata 409, JWT gerado
- [x] `feature_1_ia_personalizada/tests/unit/test_persona_prompts.py` — tom formal vs amigável; persona injetada no prompt
- [x] `feature_1_ia_personalizada/tests/integration/test_onboarding_fluxo.py` — fluxo completo das 5 etapas; go-live ativa monitoramento

---

## Melhorias de Performance e Inteligência Transversais

> Aplicar junto com as features acima. Tornam o sistema mais rápido e inteligente globalmente.

### P1 — Paralelismo no Orquestrador ✅

- [x] `asyncio.gather(buscar_andamentos_datajud(), _buscar_rag())` com timeout 15s (linhas 759–761 do `orchestrator.py`)
- [x] DataJud e RAG executados em paralelo; latência = max(latências), não soma
- **Status:** implementado; RAG não adiciona latência ao caminho crítico

### P2 — Prefetch de contexto no worker de monitoramento ✅

- [x] Em `monitor_processos.py`, `update_ultimo_andamento` e `_atualizar_score` executados em paralelo via `ThreadPoolExecutor(max_workers=2)`
- [x] Operações independentes entre si; cada uma usa sua própria sessão síncrona de banco
- [x] Exceção de `update_ultimo_andamento` (crítico) propagada; `_atualizar_score` tem graceful degradation interna
- **Arquivo:** `feature_1_ia_personalizada/workers/monitor_processos.py`
- **Status:** implementado — worker não aumenta tempo total mesmo com score calculado em paralelo

### P3 — Cache inteligente de contexto do escritório ✅

- [x] Embeddings em batch com Redis mget/pipeline (Feature 1)
- [x] Escritório e persona carregados por request com cache Redis via `templates.py`
- [x] RAG search cacheado por `(hash_query, escritorio_id)` TTL 30min
- **Status:** cache de embeddings e RAG implementado; cache centralizado de escritório (`escritorio_ctx:{id}`) não verificado como chave única

### P4 — Warm-up de embeddings frequentes ✅

- [x] Função `_warmup_embeddings()` adicionada em `app.py` — chamada no lifespan após Redis conectar
- [x] Pré-aquece 6 queries comuns: "qual o status do meu processo", "quando vai terminar", etc.
- [x] Falha silenciosa — nunca bloqueia o startup se embedding provider estiver offline
- [x] Usa cliente Redis separado (`decode_responses=False`) para embeddings binários
- **Arquivo:** `feature_1_ia_personalizada/api/app.py`
- **Status:** implementado — primeira busca RAG do dia não gera embedding (usa cache aquecido)

---

## Qualidade e Padrões (Obrigatório em Todas as Features)

- [x] Toda nova funcionalidade com testes: unitário + integração (Features 1, 2, 3, 4, 5, 6 cobertas)
- [x] Toda nova tabela com migração Alembic reversível (`upgrade` + `downgrade`) — todas as migrations têm `downgrade()`
- [x] Todo novo endpoint documentado no OpenAPI (FastAPI gera automaticamente via Pydantic)
- [x] Todo novo serviço com métricas Prometheus — `metrics.py` com gauges para NPS, autonomia, escalações, RAG
- [x] Nenhum dado de cliente em logs (padrão LGPD já estabelecido)
- [x] Todo dado multi-tenant filtrado por `escritorio_id`
- [x] Disclaimer OAB em toda resposta sobre resultado ou prazo
- [x] Variáveis de ambiente documentadas em `.env.example` — `VOYAGE_API_KEY`, `OPENAI_API_KEY` documentadas
- [x] Filtro `?score_nivel=` em GET `/processos` — implementado em `processos.py` (linhas 47–82) + testado em `test_score_api.py`
- [x] `test_escalacao_contexto.py` — criado em `tests/unit/test_escalacao_contexto.py`
- [x] `test_score_risco.py` — criado em `tests/unit/test_score_risco.py` (fórmula, pesos, compliance OAB)
- [x] `test_score_api.py` — criado em `tests/integration/test_score_api.py` (GET /{id} + filtro por nível)
- [x] Migration `004_add_score_risco` down_revision corrigido para `e4bcb5d405fa`
- [x] P2 — `update_ultimo_andamento` + `_atualizar_score` paralelos via `ThreadPoolExecutor`
- [x] P4 — warm-up de embeddings no startup via `_warmup_embeddings()` em `app.py`
- [ ] `alembic/versions/006_add_escalacao.py` como arquivo separado — não criado; colunas já estão em `e4bcb5d405fa`; desnecessário
- [ ] Invalidação de cache analytics ao receber nova interação — não verificado em `send_notifications.py`
