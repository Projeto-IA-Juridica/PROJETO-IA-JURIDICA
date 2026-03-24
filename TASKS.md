# TASKS — Feature 3: Resumo Inteligente de Movimentação (Visão do Advogado)

> **Escopo:** esta é a única feature ativa no momento. Tudo aqui é exclusivo para o papel `advogado` e `admin` — clientes nunca veem nada disso.
> **Referência arquitetural:** [docs/ROADMAP_FEATURES.md](docs/ROADMAP_FEATURES.md)
> **Princípio:** aproveitar ao máximo o que já existe. Cada subtarefa indica o arquivo exato a tocar.

---

## O que a Feature 3 entrega (lado do advogado)

O advogado precisa de uma visão inteligente sobre o que está acontecendo em **todos os seus processos**, sem ter que entrar caso a caso no sistema de tribunais. A feature entrega:

| Entrega | Descrição |
|---|---|
| **Briefing Diário** | Uma chamada única que lista o que aconteceu hoje em todos os processos ativos. Com anotação da IA sobre o que cada movimento significa para o escritório. |
| **Timeline Inteligente** | Para cada processo: histórico de andamentos com anotações geradas pela IA, indicando fase, impacto e o que esperar a seguir. |
| **Alertas Processuais** | Processos que precisam de atenção agora: score alto, fase crítica atingida, prazo provável se aproximando, ou longa inatividade suspeita. |
| **Próximos Passos** | Por processo: o que o juiz provavelmente vai fazer a seguir, com prazo estimado baseado na fase atual e no histórico do DataJud. |

> **Diferença do que já existe:** o worker `monitor_processos.py` já gera resumo em linguagem simples e envia para o **cliente** via WhatsApp. A Feature 3 gera anotações técnicas para o **advogado**, acessíveis via API, com tom jurídico, incluindo score de risco e fase processual — dados que nunca são expostos ao cliente (compliance OAB Provimento 205/2021).

---

## O que já existe e SERÁ reaproveitado

| Componente existente | Arquivo | Como será usado |
|---|---|---|
| `ProcessoStateManager` | `services/ai/processo_state.py` | Classifica fase e gera contexto histórico dos últimos 5 andamentos. Usado em todas as sub-features. |
| `JuridicalTranslator.traduzir_com_contexto()` | `services/ai/juridical_translator.py` | Chamado para gerar anotações técnicas para o advogado (novo prompt, mesmo método). |
| `ScoreRiscoCalculator` | `services/legal_data/vitoria_preditor.py` | Score 0–100 com 5 componentes; aparece junto com cada alerta e no briefing. |
| Campo `processo.estado_atual` (JSONB) | `shared/models/processo.py` | Contém fase + últimos andamentos + próximo passo. Já persistido pelo worker. |
| Campo `processo.fase_processual` | `shared/models/processo.py` | Fase textual (`instrucao`, `julgamento`, etc.). Indexado por `(escritorio_id, fase_processual)`. |
| Campo `processo.score_risco` + `score_nivel` | `shared/models/processo.py` | Alimenta os alertas e o briefing. |
| `jusbrasil_client.py` + `datajud_client.py` | `services/legal_data/` | Fonte dos andamentos brutos. DataJud fornece `tempo_medio_tramitacao_dias` por vara/classe. |
| `interacoes` table + `metadata_json` | `shared/models/interacao.py` | Armazena anotações da IA por andamento para evitar recalcular (cache persistente). |
| `cache_manager.py` (Redis) | `services/` | Cacheia briefing por `(escritorio_id)` TTL 30 min e alertas TTL 15 min. |
| `ClaudeClient` | `services/ai/claude_client.py` | Chama Claude com retry e log de tokens para todos os novos prompts. |
| `TenantMixin` | `shared/models/base.py` | Garante isolamento multi-tenant automático por `escritorio_id`. |
| JWT payload com `role` | `api/middleware/` | Extrai papel do usuário para guard de acesso (`advogado` \| `admin`). |
| `processos.py` route | `api/routes/processos.py` | Novas rotas serão adicionadas neste mesmo arquivo. |

---

## Fontes de dados

| Dado | Origem | Detalhes |
|---|---|---|
| Andamentos brutos | Jusbrasil API | Polling já feito pelo `monitor_processos.py` a cada 6h. Resultados em `processo.estado_atual`. |
| Estatísticas da vara | DataJud CNJ (gratuito) | `tempo_medio_tramitacao_dias`, `taxa_procedencia_autor` por classe/vara. Já em `vitoria_preditor.py`. |
| Score de risco | Calculado internamente | `ScoreRiscoCalculator` com 5 componentes ponderados. Persistido em `processo.score_risco`. |
| Fase processual | `processo.fase_processual` | Classificada por `ProcessoStateManager._classificar_fase()` via palavras-chave. |
| Contexto histórico | `processo.estado_atual` (JSONB) | Snapshot: fase atual, últimos 5 andamentos, próximo passo esperado. |
| Anotações anteriores | `interacoes.metadata_json` | Evita rechamar Claude para o mesmo andamento (hash do texto como chave). |
| Tempo sem movimentação | `processo.data_ultimo_andamento` | Campo existente no modelo. |

---

## Controle de acesso — quem pode usar

Todas as rotas desta feature são protegidas por:
1. **JWT válido** — middleware já existente valida token e injeta `request.state.user_payload`
2. **Role guard** — `role` no payload deve ser `advogado` ou `admin`. Clientes (`cliente`) e estagiários recebem HTTP 403.
3. **Isolamento de tenant** — `escritorio_id` extraído do token; advogado só vê processos do seu escritório.

```
cliente       → 403 Forbidden (nunca vê score nem anotações técnicas)
estagiario    → 403 Forbidden
assistente    → 403 Forbidden (pode ser liberado futuramente via config)
advogado      → acesso total às rotas da Feature 3
admin         → acesso total (gerencia o escritório)
```

---

## Status Geral

| Subtarefa | Status |
|---|---|
| 3.1 — Role guard (dependency FastAPI) | ⬜ Pendente |
| 3.2 — Novos prompts para advogado | ⬜ Pendente |
| 3.3 — Serviço `ResumoDiarioService` | ⬜ Pendente |
| 3.4 — Serviço `AlertaProcessualService` | ⬜ Pendente |
| 3.5 — Serviço `TimelineInteligenteService` | ⬜ Pendente |
| 3.6 — Schemas Pydantic de resposta | ⬜ Pendente |
| 3.7 — Novas rotas em `processos.py` | ⬜ Pendente |
| 3.8 — Persistência de anotações em `interacoes` | ⬜ Pendente |
| 3.9 — Testes unitários | ⬜ Pendente |
| 3.10 — Testes de integração | ⬜ Pendente |

---

## 3.1 — Role guard: dependency FastAPI para rotas do advogado

**Objetivo:** criar uma dependency reutilizável que bloqueia qualquer role que não seja `advogado` ou `admin`, retornando 403 com mensagem clara.

**Por que precisa disso:** o middleware JWT já autentica, mas não autoriza por role. As rotas existentes de processos não fazem essa verificação — qualquer usuário autenticado consegue acessar. As rotas da Feature 3 são mais sensíveis (score de risco, análise técnica).

- [ ] Criar função `require_advogado(request: Request)` em `feature_1_ia_personalizada/api/middleware/auth.py`
  - Lê `request.state.user_payload["role"]`
  - Se `role not in ("advogado", "admin")` → `raise HTTPException(status_code=403, detail="Acesso restrito a advogados")`
  - Retorna `user_payload` para uso na rota
- [ ] Criar função `get_escritorio_id_advogado(payload=Depends(require_advogado))` — extrai `escritorio_id` do payload já validado
- [ ] Criar função `get_advogado_id(payload=Depends(require_advogado))` — extrai `sub` (user_id) do payload

**Arquivos a tocar:**
- `feature_1_ia_personalizada/api/middleware/auth.py` — adicionar as duas funções
- Não alterar middleware global — apenas adicionar dependencies opcionais

**Critério de aceite:** rota com `Depends(require_advogado)` retorna 403 para role `cliente` e 200 para role `advogado`. Testável com pytest + mock de `request.state`.

---

## 3.2 — Novos prompts em `prompts.py`

**Objetivo:** três prompts novos, todos com tom técnico-jurídico para o advogado — diferente do prompt de cliente (linguagem simples).

- [ ] Adicionar `SYSTEM_PROMPT_BRIEFING_ADVOGADO` em `feature_1_ia_personalizada/services/ai/prompts.py`
  - Variáveis: `{nome_escritorio}`, `{processo_numero}`, `{tipo_acao}`, `{fase_processual}`, `{score_risco}`, `{score_nivel}`, `{polo_cliente}`, `{andamentos_recentes}` (últimos 3)
  - Instrução: gerar anotação técnica de 2–3 parágrafos indicando (1) o que o andamento significa juridicamente, (2) se o prazo está dentro do normal para essa vara/fase, (3) ação recomendada ao advogado (ex: "verificar prazo de contestação")
  - Regra: nunca prever resultado; focar em prazos e próximos atos processuais
  - Max 300 palavras
- [ ] Adicionar `SYSTEM_PROMPT_ALERTA_PROCESSUAL` em `prompts.py`
  - Variáveis: `{tipo_alerta}`, `{processo_numero}`, `{fase_processual}`, `{score_risco}`, `{score_nivel}`, `{dias_sem_movimentacao}`, `{proximo_passo_esperado}`
  - Instrução: 1 parágrafo curto explicando por que o processo precisa de atenção e qual ação o advogado deve tomar
  - Max 100 palavras
- [ ] Adicionar `SYSTEM_PROMPT_TIMELINE_ANOTACAO` em `prompts.py`
  - Variáveis: `{andamento_texto}`, `{fase}`, `{tipo_acao}`, `{polo_cliente}`
  - Instrução: 1 parágrafo técnico-jurídico anotando o andamento para o advogado (o que é, qual impacto, se há prazo a observar)
  - Max 150 palavras; Claude Haiku (velocidade)

**Arquivo a tocar:**
- `feature_1_ia_personalizada/services/ai/prompts.py` — adicionar as três constantes após os prompts existentes

**Critério de aceite:** prompts contêm todas as variáveis listadas; não há instrução de linguagem simples (só tom jurídico); sem instrução de "nunca predizer resultado do ponto de vista de percentual" mas sem fazer previsões de resultado.

---

## 3.3 — Serviço `ResumoDiarioService`

**Objetivo:** serviço que agrega o que aconteceu em todos os processos ativos nas últimas 24h e gera uma anotação por processo, montando o briefing do dia para o advogado.

**Arquivo a criar:** `feature_1_ia_personalizada/services/ai/resumo_diario.py`

- [ ] Criar classe `ResumoDiarioService`
- [ ] Método `async gerar_briefing(escritorio_id: int) -> BriefingDiario`:
  1. Query: buscar processos do escritório com `data_ultimo_andamento >= now() - 24h` e `monitoramento_ativo = True`
     - Campos necessários: `id`, `numero_cnj`, `tipo_acao`, `polo_cliente`, `fase_processual`, `estado_atual`, `score_risco`, `score_nivel`, `score_interpretacao`
     - Ordenar por `score_risco DESC` (processos mais críticos primeiro)
  2. Para cada processo:
     - Extrair `andamentos_recentes` de `processo.estado_atual["ultimos_andamentos"]` (já populado pelo worker)
     - Verificar se já existe anotação em `interacoes` para esse andamento (hash do texto — ver 3.8)
     - Se não existe: chamar `ClaudeClient` com `SYSTEM_PROMPT_BRIEFING_ADVOGADO`, `max_tokens=400`, modelo `claude-haiku-4-5-20251001`
     - Se existe: reutilizar anotação do banco (zero tokens gastos)
  3. Montar `BriefingDiario` com lista de `ProcessoBriefingItem` + totais
  4. Cachear resultado no Redis: chave `briefing:{escritorio_id}`, TTL 30 min
  5. Log estruturado: `escritorio_id`, `total_processos`, `total_tokens_usados`, `cache_hit`
- [ ] Método `async invalidar_cache(escritorio_id: int)` — chamado pelo worker quando novo andamento detectado
- [ ] Graceful degradation: se Claude falhar para um processo específico, incluir no briefing com `anotacao=None` (não quebrar o briefing inteiro)

**Dependências que serão injetadas:**
- `db: AsyncSession` — para queries
- `claude_client: ClaudeClient` — já existe
- `cache_manager` — já existe (Redis)

**Arquivo a tocar além do novo:**
- `shared/database/worker_queries.py` — adicionar `get_processos_com_andamento_recente(escritorio_id, horas=24)`

**Critério de aceite:** `gerar_briefing()` retorna estrutura completa; processos sem novo andamento não aparecem; cache funciona; falha no Claude de um processo não quebra os outros.

---

## 3.4 — Serviço `AlertaProcessualService`

**Objetivo:** detectar automaticamente processos que precisam de atenção do advogado, com base em critérios objetivos — sem precisar que o advogado faça a varredura manualmente.

**Arquivo a criar:** `feature_1_ia_personalizada/services/ai/alertas_processuais.py`

- [ ] Criar classe `AlertaProcessualService`
- [ ] Definir enum `TipoAlerta` com os seguintes valores:
  - `SCORE_CRITICO_COM_MOVIMENTO` — score ≥ 75 + andamento nas últimas 48h
  - `FASE_JULGAMENTO_ATINGIDA` — `fase_processual` mudou para `julgamento` nas últimas 24h
  - `FASE_EXECUCAO_INICIADA` — `fase_processual` mudou para `execucao`
  - `INATIVIDADE_SUSPEITA` — sem andamento por mais tempo que o normal para a fase:
    - `conhecimento` > 60 dias sem movimento
    - `instrucao` > 90 dias sem movimento
    - `saneamento` > 120 dias sem movimento
    - `julgamento` > 45 dias sem sentença após designação
  - `PRAZO_RECURSO_PROXIMO` — fase `julgamento` encerrada há entre 12 e 15 dias (janela de recurso)
- [ ] Método `async gerar_alertas(escritorio_id: int) -> list[AlertaProcessual]`:
  1. Query única buscando todos os processos ativos do escritório com campos: `id`, `numero_cnj`, `tipo_acao`, `fase_processual`, `score_risco`, `score_nivel`, `data_ultimo_andamento`, `estado_atual`
  2. Para cada processo: verificar cada critério de alerta e gerar `AlertaProcessual` se ativado
  3. Gerar mensagem de alerta: para cada alerta, montar texto com `SYSTEM_PROMPT_ALERTA_PROCESSUAL` (Claude Haiku, max_tokens=150)
     - Reutilizar cache de anotação se o alerta já foi gerado para o mesmo estado (hash de `fase + score + dias_sem_mov`)
  4. Ordenar por urgência: `FASE_EXECUCAO_INICIADA` > `SCORE_CRITICO_COM_MOVIMENTO` > `FASE_JULGAMENTO_ATINGIDA` > `PRAZO_RECURSO_PROXIMO` > `INATIVIDADE_SUSPEITA`
  5. Cachear no Redis: chave `alertas:{escritorio_id}`, TTL 15 min
- [ ] Método `async contar_alertas(escritorio_id: int) -> int` — versão leve para o header do dashboard (sem gerar mensagens Claude)

**Arquivo a tocar:**
- `shared/database/worker_queries.py` — adicionar `get_processos_para_alertas(escritorio_id)`

**Critério de aceite:** processo com score 80 + andamento ontem → gera alerta `SCORE_CRITICO_COM_MOVIMENTO`; processo em `julgamento` há 13 dias → gera alerta `PRAZO_RECURSO_PROXIMO`; processo sem movimento há 100 dias em `instrucao` → gera `INATIVIDADE_SUSPEITA`.

---

## 3.5 — Serviço `TimelineInteligenteService`

**Objetivo:** dado um processo específico, montar uma timeline cronológica de todos os andamentos com anotações da IA, mostrando como a fase evoluiu e o que cada movimento significou.

**Arquivo a criar:** `feature_1_ia_personalizada/services/ai/timeline_inteligente.py`

- [ ] Criar classe `TimelineInteligenteService`
- [ ] Método `async gerar_timeline(processo_id: int, escritorio_id: int) -> TimelineProcesso`:
  1. Buscar o processo pelo `id` e `escritorio_id` (validação multi-tenant obrigatória)
  2. Buscar histórico completo de andamentos:
     - Fonte primária: `processo.estado_atual["ultimos_andamentos"]` (últimos 5, já no banco)
     - Fonte secundária: `interacoes` com `metadata_json->>'tipo' = 'andamento_detectado'` para esse `processo_id` — andamentos mais antigos registrados em interações
     - Se precisar buscar mais: `jusbrasil_client.get_andamentos(numero_cnj)` com cache Redis 1h
  3. Para cada andamento (em ordem cronológica):
     - Checar em `interacoes` se já existe anotação (por hash do texto do andamento)
     - Se existe: usar anotação cached do banco
     - Se não existe: chamar Claude com `SYSTEM_PROMPT_TIMELINE_ANOTACAO`, `max_tokens=200`, Claude Haiku
     - Persistir nova anotação em `interacoes` (ver 3.8)
     - Classificar fase do andamento com `ProcessoStateManager._classificar_fase(texto)`
  4. Buscar `proximo_passo` de `processo.estado_atual["proximo_passo"]` (já calculado pelo `ProcessoStateManager`)
  5. Montar `TimelineProcesso` com: `numero_cnj`, `fase_atual`, `score_risco`, `score_nivel`, `movimentos: list[MovimentoAnotado]`, `proximo_passo`
- [ ] Método `async invalidar_anotacoes(processo_id: int)` — para uso quando andamentos forem deletados

**Critério de aceite:** timeline retorna movimentos em ordem cronológica; anotações existentes no banco são reutilizadas (zero chamadas Claude); novo andamento gera nova anotação e persiste; falha no Claude para um movimento não quebra a timeline.

---

## 3.6 — Schemas Pydantic de resposta

**Objetivo:** definir as estruturas tipadas de resposta para todas as novas rotas.

**Arquivo a criar:** `shared/schemas/feature3.py`

- [ ] `ProcessoBriefingItem` — item do briefing diário:
  ```python
  processo_id: int
  numero_cnj: str
  tipo_acao: str
  fase_processual: str
  score_risco: int | None
  score_nivel: str | None        # baixo | moderado | alto | critico
  score_interpretacao: str | None
  andamento_mais_recente: str    # texto bruto do último andamento
  data_andamento: datetime
  anotacao_advogado: str | None  # gerada pela IA, None se falhou
  ```
- [ ] `BriefingDiario` — resposta do endpoint `/processos/briefing-diario`:
  ```python
  data_geracao: datetime
  total_processos_com_movimento: int
  total_alertas_ativos: int      # de AlertaProcessualService.contar_alertas()
  processos: list[ProcessoBriefingItem]
  cache_hit: bool                # para debug/monitoring
  ```
- [ ] `AlertaProcessual` — item de alerta:
  ```python
  tipo: str                      # TipoAlerta value
  urgencia: int                  # 1–5 (5 = mais urgente)
  processo_id: int
  numero_cnj: str
  fase_processual: str
  score_risco: int | None
  mensagem: str                  # gerada pela IA
  criado_em: datetime
  ```
- [ ] `MovimentoAnotado` — item da timeline:
  ```python
  data_movimento: datetime
  texto_original: str            # andamento bruto do tribunal
  fase: str                      # classificada pelo ProcessoStateManager
  anotacao_advogado: str | None  # gerada pela IA
  cached: bool                   # se veio do banco ou foi gerado agora
  ```
- [ ] `ProximoPasso`:
  ```python
  fase_atual: str
  descricao: str                 # de _PROXIMO_PASSO em processo_state.py
  prazo_estimado: str
  ```
- [ ] `TimelineProcesso` — resposta do endpoint `/processos/{id}/timeline`:
  ```python
  processo_id: int
  numero_cnj: str
  tipo_acao: str
  fase_atual: str
  score_risco: int | None
  score_nivel: str | None
  movimentos: list[MovimentoAnotado]
  proximo_passo: ProximoPasso
  total_movimentos: int
  ```

**Arquivo a tocar:**
- `shared/schemas/__init__.py` — exportar os novos schemas

**Critério de aceite:** todos os campos `None`-able têm `| None`; campos obrigatórios não têm default; schemas importam sem erro circular.

---

## 3.7 — Novas rotas em `processos.py`

**Objetivo:** expor as três funcionalidades via API REST, protegidas pelo role guard do 3.1.

**Arquivo a tocar:** `feature_1_ia_personalizada/api/routes/processos.py`

- [ ] `GET /processos/briefing-diario`
  - Dependency: `Depends(require_advogado)`
  - Extrai `escritorio_id` do payload via `get_escritorio_id_advogado()`
  - Instancia `ResumoDiarioService(db, claude_client, cache_manager)`
  - Chama `gerar_briefing(escritorio_id)`
  - Registra acesso com `registrar_acesso()` (LGPD)
  - Response model: `BriefingDiario`
  - Cache: TTL 30 min no serviço (não duplicar no FastAPI)

- [ ] `GET /processos/alertas`
  - Dependency: `Depends(require_advogado)`
  - Query param: `?urgencia_minima=1` (default 1, filtra alertas abaixo desse nível)
  - Instancia `AlertaProcessualService(db, claude_client, cache_manager)`
  - Chama `gerar_alertas(escritorio_id)`
  - Aplica filtro de urgência se informado
  - Response model: `list[AlertaProcessual]`
  - Header de resposta: `X-Total-Alertas: {len(alertas)}`

- [ ] `GET /processos/{id}/timeline`
  - Dependency: `Depends(require_advogado)`
  - Path param: `id: int` (processo_id)
  - Query param: `?limite_movimentos=20` (default 20, max 100)
  - Valida que o processo pertence ao `escritorio_id` do token (403 se não pertencer)
  - Instancia `TimelineInteligenteService(db, claude_client, jusbrasil_client)`
  - Chama `gerar_timeline(processo_id, escritorio_id)`
  - Response model: `TimelineProcesso`

- [ ] `GET /processos/{id}/proximo-passo`
  - Dependency: `Depends(require_advogado)`
  - Lê `processo.estado_atual["proximo_passo"]` e `processo.fase_processual` diretamente do banco
  - Retorna `ProximoPasso` sem chamar Claude (dados já calculados pelo `ProcessoStateManager`)
  - Response cacheada no header `Cache-Control: max-age=3600`

**Critério de aceite:** todas as 4 rotas retornam 403 para role `cliente`; retornam 200 para role `advogado` com estrutura correta; `GET /processos/{id}/timeline` retorna 403 se processo de outro escritório.

---

## 3.8 — Persistência de anotações em `interacoes`

**Objetivo:** evitar rechamar Claude para o mesmo andamento toda vez que o advogado abrir o briefing ou a timeline. Usar a tabela `interacoes` como cache persistente de anotações, já que ela tem `metadata_json` flexível e está indexada por `processo_id`.

**Não cria nova tabela** — aproveita `interacoes` com `tipo = "anotacao_advogado"`.

- [ ] Definir estrutura de `metadata_json` para anotações:
  ```json
  {
    "andamento_hash": "sha256 do texto original",
    "andamento_texto": "texto bruto do andamento",
    "fase": "instrucao",
    "anotacao": "texto gerado pela IA",
    "prompt_usado": "BRIEFING_ADVOGADO | TIMELINE_ANOTACAO | ALERTA",
    "tokens_input": 245,
    "tokens_output": 187,
    "modelo": "claude-haiku-4-5-20251001"
  }
  ```
- [ ] Criar `get_anotacao_cached(processo_id, andamento_hash, db)` em `shared/database/worker_queries.py`
  - Query: `SELECT * FROM interacoes WHERE processo_id = ? AND metadata_json->>'andamento_hash' = ? AND tipo = 'anotacao_advogado' LIMIT 1`
- [ ] Criar `salvar_anotacao(processo_id, cliente_id, escritorio_id, metadata, db)` em `worker_queries.py`
  - Insere nova `Interacao` com `tipo = "anotacao_advogado"`, `direcao = "interno"`, `mensagem_ia = anotacao`
- [ ] Criar índice para performance (se não existir):
  ```sql
  CREATE INDEX IF NOT EXISTS idx_interacoes_anotacao_advogado
  ON interacoes ((metadata_json->>'andamento_hash'))
  WHERE tipo = 'anotacao_advogado';
  ```
  - Adicionar em nova migration: `alembic/versions/011_add_anotacao_advogado_index.py`

**Critério de aceite:** segunda chamada para o mesmo andamento retorna do banco sem chamar Claude (verificável via log de tokens = 0); índice parcial criado sem bloquear tabela (`CONCURRENTLY`).

---

## 3.9 — Testes unitários

**Objetivo:** cobrir a lógica de negócio de cada serviço de forma isolada (sem banco, sem Claude real).

- [ ] `feature_1_ia_personalizada/tests/unit/test_resumo_diario.py`
  - Mock do `ClaudeClient` retornando anotação fixa
  - Mock do banco com 3 processos: 1 com andamento novo, 1 sem, 1 com anotação cached
  - Verifica: apenas processo com andamento novo aparece no briefing; cache hit não chama Claude; falha Claude não quebra outros processos
  - Testa `invalidar_cache()` limpa chave Redis correta

- [ ] `feature_1_ia_personalizada/tests/unit/test_alertas_processuais.py`
  - Testa cada critério de alerta independentemente (sem banco — processos como dicts)
  - `SCORE_CRITICO_COM_MOVIMENTO`: score=80, andamento=ontem → alerta gerado
  - `SCORE_CRITICO_COM_MOVIMENTO`: score=80, andamento=há 3 dias → alerta NÃO gerado
  - `INATIVIDADE_SUSPEITA`: fase=instrucao, último andamento há 91 dias → alerta gerado
  - `INATIVIDADE_SUSPEITA`: fase=instrucao, último andamento há 89 dias → NÃO gerado
  - `FASE_JULGAMENTO_ATINGIDA`: mudança de fase registrada nas últimas 24h → alerta gerado
  - `PRAZO_RECURSO_PROXIMO`: fase=julgamento encerrado há 13 dias → alerta gerado
  - Verifica ordenação por urgência: execução > critico > julgamento > recurso > inatividade

- [ ] `feature_1_ia_personalizada/tests/unit/test_timeline_inteligente.py`
  - Mock jusbrasil retornando 5 andamentos
  - Mock banco: 2 andamentos com anotação cached, 3 sem
  - Verifica: 2 cached → 0 chamadas Claude para esses; 3 novos → 3 chamadas Claude; timeline cronológica; `proximo_passo` vem de `estado_atual`
  - Testa isolamento multi-tenant: `processo.escritorio_id != escritorio_id_do_token` → retorna None (a rota deve retornar 403)

- [ ] `feature_1_ia_personalizada/tests/unit/test_role_guard.py`
  - `require_advogado` com role=`advogado` → não levanta exceção
  - `require_advogado` com role=`admin` → não levanta exceção
  - `require_advogado` com role=`cliente` → HTTPException 403
  - `require_advogado` com role=`estagiario` → HTTPException 403
  - `require_advogado` sem `user_payload` no estado → HTTPException 401

**Critério de aceite:** `pytest tests/unit/test_resumo_diario.py tests/unit/test_alertas_processuais.py tests/unit/test_timeline_inteligente.py tests/unit/test_role_guard.py` passa sem erros; coverage dos novos serviços ≥ 80%.

---

## 3.10 — Testes de integração

**Objetivo:** validar os endpoints de ponta a ponta com banco de dados real (SQLite em memória ou PostgreSQL de test) e mock apenas do Claude e das APIs externas.

- [ ] `feature_1_ia_personalizada/tests/integration/test_feature3_advogado.py`
  - Setup: criar `escritorio`, `usuario` com role=`advogado`, 3 `processos` com dados variados de score e fase
  - Testar `GET /processos/briefing-diario`:
    - Com token de advogado → 200 + estrutura `BriefingDiario` completa
    - Com token de cliente → 403
    - Com token de advogado de outro escritório → 200 mas lista vazia (isolamento multi-tenant)
    - Segunda chamada no mesmo TTL → `cache_hit=True`
  - Testar `GET /processos/alertas`:
    - Processo com score=90 e andamento ontem → aparece na lista com urgência alta
    - `?urgencia_minima=4` filtra alertas de urgência baixa
    - Role cliente → 403
  - Testar `GET /processos/{id}/timeline`:
    - Processo do escritório → 200 + `TimelineProcesso`
    - Processo de outro escritório (mesmo ID válido) → 403
    - Processo inexistente → 404
  - Testar `GET /processos/{id}/proximo-passo`:
    - Processo com `estado_atual` populado → retorna `ProximoPasso` corretamente
    - Processo sem `estado_atual` (nulo) → retorna próximo passo padrão da fase `conhecimento`

**Critério de aceite:** todos os casos passam; nenhuma chamada real ao Claude (mock); nenhuma chamada real ao Jusbrasil (mock); banco limpo entre testes via rollback de transação.

---

## Arquivos novos a criar (resumo)

```
feature_1_ia_personalizada/
├── services/
│   └── ai/
│       ├── resumo_diario.py          # ResumoDiarioService
│       ├── alertas_processuais.py    # AlertaProcessualService + TipoAlerta
│       └── timeline_inteligente.py  # TimelineInteligenteService
│
└── tests/
    ├── unit/
    │   ├── test_resumo_diario.py
    │   ├── test_alertas_processuais.py
    │   ├── test_timeline_inteligente.py
    │   └── test_role_guard.py
    └── integration/
        └── test_feature3_advogado.py

shared/
└── schemas/
    └── feature3.py                   # Todos os schemas de resposta

alembic/versions/
└── 011_add_anotacao_advogado_index.py  # Índice parcial em interacoes
```

## Arquivos existentes a modificar (resumo)

```
feature_1_ia_personalizada/api/middleware/auth.py
  → + require_advogado(), get_escritorio_id_advogado(), get_advogado_id()

feature_1_ia_personalizada/api/routes/processos.py
  → + GET /processos/briefing-diario
  → + GET /processos/alertas
  → + GET /processos/{id}/timeline
  → + GET /processos/{id}/proximo-passo

feature_1_ia_personalizada/services/ai/prompts.py
  → + SYSTEM_PROMPT_BRIEFING_ADVOGADO
  → + SYSTEM_PROMPT_ALERTA_PROCESSUAL
  → + SYSTEM_PROMPT_TIMELINE_ANOTACAO

shared/database/worker_queries.py
  → + get_processos_com_andamento_recente()
  → + get_processos_para_alertas()
  → + get_anotacao_cached()
  → + salvar_anotacao()

shared/schemas/__init__.py
  → exportar schemas de feature3.py
```

---

## Ordem de implementação sugerida

```
3.1 (role guard)
  → 3.2 (prompts)
    → 3.6 (schemas Pydantic) ← pode ser paralelo com 3.2
      → 3.8 (persistência de anotações)
        → 3.3 (ResumoDiarioService)
        → 3.4 (AlertaProcessualService)  ← pode ser paralelo com 3.3
        → 3.5 (TimelineInteligenteService)
          → 3.7 (rotas)
            → 3.9 (testes unitários)
              → 3.10 (testes de integração)
```

> **Regra de ouro:** não partir para 3.7 (rotas) sem os schemas (3.6) e pelo menos um serviço (3.3) prontos. Não partir para 3.10 sem 3.9 passar 100%.
