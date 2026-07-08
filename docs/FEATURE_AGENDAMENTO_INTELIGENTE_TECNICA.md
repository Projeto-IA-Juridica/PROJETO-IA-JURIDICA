# Agendamento Inteligente — Documentação Técnica

> Detecta intenção de reunião no WhatsApp, propõe horários disponíveis ao cliente, notifica o advogado em dois canais simultaneamente e confirma com trava atômica via Redis — sem nenhuma ação manual até o aval final.

| Fase | Status |
|---|---|
| Fase 1 — Banco de dados | ✅ Concluída |
| Fase 2 — Backend core | ✅ Concluída e revisada |
| Fase 3 — IA + WhatsApp | ✅ Concluída |
| Fase 4 — Workers Celery | ✅ Concluída |
| Fase 5 — Frontend | ✅ Concluída |

---

## Índice

- [O problema](#o-problema)
- [Fluxo completo](#fluxo-completo)
- [Máquina de estados](#máquina-de-estados)
- [Modelo de dados](#modelo-de-dados)
  - [Agendamento](#agendamento)
  - [DisponibilidadeAdvogado](#disponibilidadeadvogado)
  - [Escritorio — campos adicionados](#escritorio--campos-adicionados)
- [API](#api)
  - [Configuração — /agenda](#configuração--agenda)
  - [Hub do Advogado — /agendamentos](#hub-do-advogado--agendamentos)
- [Serviços](#serviços)
  - [AgendamentoDetector](#agendamentodetector)
  - [AgendamentoNotifier](#agendamentonotifier)
- [Workers Celery](#workers-celery)
- [Frontend](#frontend)
- [Regras de negócio](#regras-de-negócio)
- [Integrações com o sistema existente](#integrações-com-o-sistema-existente)
- [Status de implementação](#status-de-implementação)

---

## O problema

| Problema | Impacto |
|---|---|
| Pedido no chat sem resposta rápida | Sensação de abandono, risco de churn |
| Advogado confirma sem checar agenda | Duplo agendamento, reagendamentos |
| Reunião marcada no dia de prazo processual | Pressão, erro, dano à imagem profissional |
| Cliente fica sem confirmação formal | Insegurança, não comparece à reunião |

---

## Fluxo completo

```
Cliente escreve no WhatsApp
  └─► IA detecta intenção agendar_reuniao (threshold 0.80)
        └─► AgendamentoDetector busca disponibilidade
              └─► IA propõe 3 opções ao cliente (status: aguardando_cliente)
                    └─► Cliente responde "1", "2" ou "3"
                          ├─► WhatsApp do advogado (nome, horário, motivo)
                          └─► Card no Hub (polling 10s)
                                    │
                          ┌─────────┴──────────┐
                          │                    │
                   Advogado responde     Advogado clica
                   no WhatsApp           no Hub
                          │                    │
                          └────────┬───────────┘
                                   │
                             (primeiro ganha)
                             Redis SET NX lock
                                   │
                   Card some do Hub no próximo polling
                   WhatsApp envia confirmação ao cliente
                   status → confirmado, canal_aprovacao registrado
```

---

## Máquina de estados

```
[aguardando_cliente] ──(cliente escolhe)──► [aguardando_advogado] ──(advogado confirma)──► [confirmado]
         │                                           │
   (48h sem resposta)                         (advogado recusa)
         │                                           │
     [expirado]                                 [cancelado]
```

Quando o advogado usa `/sugerir`, o fluxo retorna:
`aguardando_advogado` → `aguardando_cliente` (com novas opções e expiração resetada em 48h)

---

## Modelo de dados

### Agendamento

**Tabela:** `agendamentos`
**Herança:** `TenantMixin` (escritorio_id) + `TimestampMixin` (created_at, updated_at)

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | int PK | Chave primária auto-incremental |
| `escritorio_id` | int FK | FK → escritorios (CASCADE). Via TenantMixin. |
| `cliente_id` | int FK | FK → clientes (CASCADE). Índice individual. |
| `interacao_id` | int? FK | FK → interacoes (SET NULL). Conversa que originou o agendamento. |
| `processo_id` | int? FK | FK → processos (SET NULL). Contexto processual para conflito de prazos. |
| `status` | str(30) | Estado atual. Default: `aguardando_cliente`. Ver máquina de estados. |
| `data_hora_inicio` | datetime? tz | Slot confirmado em UTC. Preenchido quando cliente seleciona (Fase 3). |
| `data_hora_fim` | datetime? tz | Fim do slot confirmado em UTC. |
| `opcoes_propostas` | JSONB? | 3 slots propostos: `[{inicio: ISO, fim: ISO, label: str}]` |
| `opcao_selecionada_pos` | smallint? | Posição 0–2 na lista escolhida pelo cliente. |
| `canal_aprovacao` | str(20)? | Canal que confirmou primeiro: `'hub'` ou `'whatsapp'` |
| `motivo_cliente` | text? | Trecho da conversa que originou o pedido. **Imutável após criação.** Exibido no Hub e no WhatsApp ao advogado. |
| `nota_advogado` | text? | Nota interna do advogado ao sugerir novos horários. Não exibida ao cliente. |
| `whatsapp_proposta_cliente_enviado` | bool | Flag de idempotência. `True` após `enviar_proposta_cliente()` concluir. |
| `whatsapp_notificacao_advogado_enviado` | bool | Flag de idempotência. `True` após `enviar_notificacao_advogado()` concluir. |
| `whatsapp_confirmacao_cliente_enviado` | bool | Flag de idempotência. `True` após `enviar_confirmacao_cliente()` concluir. |
| `whatsapp_confirmacao_pre_reuniao_enviado` | bool | Flag de idempotência. `True` após worker enviar lembrete 3h antes. |
| `proposta_enviada_em` | datetime? tz | Timestamp do envio da proposta. Resetado a `None` em `/sugerir`. |
| `expira_em` | datetime? tz | Deadline 48h para resposta do cliente. Usado pelo worker `expirar_propostas`. |
| `resposta_cliente_em` | datetime? tz | Quando o cliente escolheu o horário. |
| `resposta_advogado_em` | datetime? tz | Quando o advogado confirmou ou recusou. |
| `motivo_cancelamento` | text? | Preenchido pelo endpoint `/cancelar`. |

**Índices:**

| Nome | Campos | Uso |
|---|---|---|
| `ix_agendamentos_escritorio_status` | `escritorio_id, status` | Principal: listagem e polling do Hub |
| `ix_agendamentos_expira_em` | `expira_em` | Worker `expirar_propostas` |
| `ix_agendamentos_cliente_id` | `cliente_id` | Busca por cliente |
| `ix_agendamentos_status` | `status` | Filtros de status sem escritório |

---

### DisponibilidadeAdvogado

**Tabela:** `disponibilidade_advogado`
Uma linha por dia da semana ativo. Ausência de linha = dia não atende.

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | int PK | Chave primária |
| `escritorio_id` | int FK | FK → escritorios (CASCADE). Via TenantMixin. |
| `dia_semana` | smallint | 0 = segunda … 5 = sábado. Constraint: `BETWEEN 0 AND 5`. |
| `hora_inicio` | time | Ex: `09:00` |
| `hora_fim` | time | Ex: `18:00`. Constraint: `hora_fim > hora_inicio`. |
| `ativo` | bool | Desativa temporariamente sem excluir. Default: `true`. |

**Constraints:**
- `UniqueConstraint(escritorio_id, dia_semana)` — cria índice B-tree implícito no PostgreSQL
- `CheckConstraint("dia_semana BETWEEN 0 AND 5")`
- `CheckConstraint("hora_fim > hora_inicio")`

---

### Escritorio — campos adicionados

| Campo | Tipo | Descrição |
|---|---|---|
| `telefone_advogado` | str(20)? | Número WhatsApp do advogado para notificações de agendamento. Distinto de `escalacao_canal_advogado_numero`. Webhook usa este campo para identificar remetentes. |
| `timezone` | str(50) | Fuso IANA do escritório. Ex: `America/Sao_Paulo`, `America/Manaus`. Default: `America/Sao_Paulo`. |

**Migration:** `alembic/versions/20260630_1000_add_agendamento_tables.py`

---

## API

### Configuração — /agenda

Todos os endpoints exigem autenticação JWT com `escritorio_id` no payload.

#### `GET /agenda/disponibilidade`

Lista janelas cadastradas, ordenadas por `dia_semana`. Inclui dias com `ativo=false` (para exibição na ConfigPage).

**Response:** `list[DisponibilidadeResponse]`

---

#### `PUT /agenda/disponibilidade`

Substitui integralmente as janelas da semana (delete-all + insert). Máx. 6 entradas (seg–sáb).

**Validações antes de executar:**
- `hora_fim > hora_inicio` para cada item
- Sem `dia_semana` duplicado na requisição

**Body:** `list[DisponibilidadeItem]`

```json
[
  {"dia_semana": 0, "hora_inicio": "09:00", "hora_fim": "18:00", "ativo": true},
  {"dia_semana": 2, "hora_inicio": "09:00", "hora_fim": "17:00", "ativo": true}
]
```

---

#### `GET /agenda/slots`

Retorna os próximos N slots livres. Usado pela ConfigPage para prévia e internamente pelo LangGraph.

| Parâmetro | Default | Limites | Descrição |
|---|---|---|---|
| `num_slots` | 3 | 1–10 | Quantidade de slots a retornar |
| `duracao_min` | 60 | 15–480 | Duração de cada slot em minutos |

**Response:** `list[SlotResponse]` — cada item com `inicio` (ISO UTC), `fim` (ISO UTC), `label` (horário local formatado)

---

### Hub do Advogado — /agendamentos

#### `GET /agendamentos`

Lista agendamentos com filtros e paginação. Nomes de clientes resolvidos em batch (sem N+1).

O frontend faz polling `?status=aguardando_advogado` a cada 10s para sincronizar cards de aprovação.

| Parâmetro | Descrição |
|---|---|
| `status` | Filtra por status. Valores: `aguardando_cliente`, `aguardando_advogado`, `confirmado`, `cancelado`, `expirado` |
| `data_inicio` | Filtra `data_hora_inicio >=` |
| `data_fim` | Filtra `data_hora_inicio <=` |
| `page` | Default: 1 |
| `page_size` | Default: 20, max: 100 |

---

#### `GET /agendamentos/{id}`

Detalhe de um agendamento. Valida isolamento multi-tenant (escritorio_id do JWT).

---

#### `POST /agendamentos/{id}/confirmar`

Advogado confirma pelo Hub. **Idempotente**: se `status == 'confirmado'` (qualquer canal), retorna 200 sem re-processar.

**Fluxo:**
1. Adquire lock Redis `agendamento_confirmar:{id}` (TTL 30s)
2. Valida bounds de `opcao_selecionada_pos`
3. Seta `status=confirmado`, `canal_aprovacao='hub'`, `data_hora_inicio`, `data_hora_fim`
4. Libera lock (finally)

**Erros 409:** status não é `aguardando_advogado` | cliente ainda não selecionou | lock em andamento

---

#### `POST /agendamentos/{id}/sugerir`

Advogado propõe novos horários. Volta ao início do fluxo do cliente com novas opções.

Exige `status == 'aguardando_advogado'`. Com lock Redis, invoca `AgendamentoDetector` para 3 novos slots.

**Campos resetados:**
- `opcoes_propostas` → novas opções
- `opcao_selecionada_pos` → `None`
- `status` → `aguardando_cliente`
- `proposta_enviada_em` → `None`
- `expira_em` → `now + 48h`
- `whatsapp_proposta_cliente_enviado` → `False`
- `whatsapp_notificacao_advogado_enviado` → `False`

**Body:** `{"nota_advogado": "string opcional, max 500 chars"}`

---

#### `POST /agendamentos/{id}/cancelar`

Cancela o agendamento. Aceita qualquer status exceto `cancelado` e `expirado`.

Seta `status=cancelado` e `motivo_cancelamento`. A Fase 3 complementará com envio de WhatsApp ao cliente.

**Body:** `{"motivo": "string opcional, max 500 chars"}`

---

## Serviços

### AgendamentoDetector

**Arquivo:** `feature_1_ia_personalizada/services/agendamento/detector.py`

Calcula os próximos slots livres para um escritório. Acionado pelo nó LangGraph, por `/agenda/slots` e por `/agendamentos/{id}/sugerir`.

**Lógica de busca (`buscar_slots`):**
1. Carrega `DisponibilidadeAdvogado` ativas do escritório
2. Itera dias à frente (até 30 dias) gerando candidatos de `duracao_min` min dentro de cada janela
3. Para cada candidato, consulta conflitos via `_tem_conflito()`
4. Retorna os primeiros `num_slots` livres como `list[SlotDisponivel]`

**Detecção de conflitos (`_tem_conflito`):**

Dois casos cobertos pela query PostgreSQL:

```sql
-- Caso 1: data_hora já preenchida (confirmado ou aguardando_advogado pós-Fase 3)
status IN ('confirmado', 'aguardando_advogado')
AND data_hora_inicio IS NOT NULL
AND data_hora_inicio < :fim AND data_hora_fim > :inicio

-- Caso 2: aguardando_advogado sem data_hora (fallback JSONB até Fase 3 popular o campo)
status = 'aguardando_advogado'
AND opcao_selecionada_pos IS NOT NULL
AND data_hora_inicio IS NULL
AND (opcoes_propostas->opcao_selecionada_pos->>'inicio')::timestamptz < :fim
AND (opcoes_propostas->opcao_selecionada_pos->>'fim')::timestamptz > :inicio
```

**Conversão de fuso:** slots gerados em horário local (`ZoneInfo(timezone_str)`) e convertidos para UTC. Labels exibem horário local.

---

### AgendamentoNotifier

**Arquivo:** `feature_1_ia_personalizada/services/agendamento/notifier.py` *(Fase 3)*

Responsável por todas as mensagens WhatsApp do fluxo. Cada método checa sua flag de idempotência antes de enviar.

| Método | Destinatário | Flag de idempotência |
|---|---|---|
| `enviar_proposta_cliente(ag)` | Cliente | `whatsapp_proposta_cliente_enviado` |
| `enviar_notificacao_advogado(ag)` | Advogado | `whatsapp_notificacao_advogado_enviado` |
| `enviar_confirmacao_cliente(ag)` | Cliente | `whatsapp_confirmacao_cliente_enviado` |
| `enviar_confirmacao_pre_reuniao(ag)` | Cliente | `whatsapp_confirmacao_pre_reuniao_enviado` |
| `enviar_cancelamento(ag)` | Cliente | — |
| `enviar_lembrete(ag)` | Cliente + Advogado | — |
| `processar_resposta_advogado(texto, escritorio_id)` | — | Redis SET NX |

**Regex para `processar_resposta_advogado` (sem gastar tokens Claude):**

```python
CONFIRMAR = re.compile(r'\b(1|sim|confirmar?|ok|pode|confirmado)\b', re.I)
RECUSAR   = re.compile(r'\b(2|n[aã]o|recusar?|cancelar?|nao)\b', re.I)
# Se não bater → Claude interpreta em linguagem natural
```

**Lock de aprovação:** Redis `SET NX` na chave `agendamento_confirmar:{id}` (TTL 30s) — evita dupla confirmação simultânea Hub + WhatsApp.

**Importante (Fase 3):** ao processar a escolha do cliente (transição `aguardando_cliente → aguardando_advogado`), o nó LangGraph deve popular `data_hora_inicio` e `data_hora_fim` com o slot selecionado, ativando o Caso 1 do detector para conflitos futuros.

---

## Workers Celery

**Arquivo:** `workers/agendamento_worker.py` *(Fase 4)*

Tasks registradas no beat schedule existente, fila `ia`.

| Task | Trigger | O que faz |
|---|---|---|
| `expirar_propostas` | Cron a cada hora | Busca `status=aguardando_cliente AND expira_em < now`. Seta `status=expirado`. Usa índice `ix_agendamentos_expira_em`. |
| `enviar_lembretes` | Cron diário às 8h | Reuniões `confirmadas` com `data_hora_inicio` amanhã. Envia WhatsApp ao cliente E ao advogado. |
| `enviar_confirmacao_pre_reuniao` | Cron a cada hora | Reuniões `confirmadas` com `data_hora_inicio IN [now+3h, now+3h59]` e flag `False`. Envia e seta a flag. |
| `verificar_conflitos_prazos` | Hook pós-andamento | Re-verifica agendamentos `confirmados` vs. novos prazos em `andamentos`. Alerta o advogado. |

---

## Frontend

### Cards de aprovação *(Fase 5)*

Na seção **Clientes** do Hub. Polling a cada **10s** — sem WebSocket para o MVP.

- **Badge no header** — total de `aguardando_advogado`. Clique filtra a lista.
- **Card destacado** — nome do cliente, horário escolhido, `motivo_cliente` (palavras do cliente), contexto da conversa, alerta de prazo processual.
- **Botões inline** — `Confirmar` | `Sugerir outro horário` | `Recusar`
- **Sincronização automática** — polling `GET /agendamentos?status=aguardando_advogado`. Card some sem refresh quando WhatsApp confirma.

---

### Aba Agenda *(Fase 5)*

Toggle adicional na CRMPage: **Lista | Relacionamento | Agenda**. Visão semanal com navegação por semana.

| Tipo de item | Cor | Origem |
|---|---|---|
| Reunião confirmada | Azul | `Agendamento.status = 'confirmado'` |
| Aprovação pendente | Âmbar | `Agendamento.status = 'aguardando_advogado'` |
| Prazo processual | Vermelho (read-only) | `andamentos` dos processos ativos |

Banner fixo no topo quando há pendentes na semana. Empty states com link para Configurações quando não há disponibilidade cadastrada.

---

### Configurações + Widget Painel *(Fase 5)*

- **ConfigPage — "Horários de atendimento"** — grade seg–sáb com hora início/fim e toggle ativo. Campo `telefone_advogado`. Prévia dos próximos slots.
- **PainelPage — "Próximas reuniões"** — 3 próximas reuniões `confirmadas` + contador de pendentes. Oculto se vazio. Link para Clientes → Agenda.

---

## Regras de negócio

- **Sem confirmação automática** — o advogado sempre tem o aval final antes de qualquer confirmação ao cliente.
- **Primeiro canal ganha** — aprovação via WhatsApp ou Hub é válida e definitiva. Lock atômico Redis `SET NX` evita dupla confirmação.
- **Proposta expira em 48h** — se o cliente não responder, status vira `expirado` e o slot fica disponível novamente.
- **Máximo de 3 opções** — não sobrecarregar o cliente. Sugestão do advogado também gera exatamente 3 opções.
- **Identificação do advogado no webhook** — remetente == `Escritorio.telefone_advogado` → fluxo do advogado. Caso contrário → fluxo normal do cliente.
- **Conflito de prazo não bloqueia** — apenas avisa o advogado. Ele decide se confirma mesmo assim.
- **Timezone** — armazenado sempre em UTC. Exibido no fuso IANA do escritório. Label dos slots gerado em horário local.
- **Compliance OAB** — mensagens não sugerem resultado do processo. Motivo da reunião é neutro: "conversar sobre seu processo".
- **Sem agenda externa** — usa apenas `DisponibilidadeAdvogado` cadastrada. Integração com Google Calendar é melhoria futura.

---

## Integrações com o sistema existente

| Componente existente | Como aproveita |
|---|---|
| `nodes/intent.py` | Adiciona intenção `agendar_reuniao` (threshold 0.80) sem criar novo arquivo |
| `services/ai/orchestrator.py` | Novo branch LangGraph: `intent → agendamento` quando detectado; senão `→ retrieve` |
| `services/messaging/` (Evolution API) | `AgendamentoNotifier` usa o mesmo dispatcher WhatsApp |
| Webhook incoming WhatsApp | Reutilizado para identificar remetente como advogado pelo `telefone_advogado` |
| Redis | Lock `SET NX agendamento_confirmar:{id}` para dupla confirmação |
| Celery + filas | 4 novas tasks na fila `ia` existente, registradas no beat schedule |
| `shared/models/interacao.py` | `interacao_id` FK rastreia a conversa que disparou o agendamento |
| `shared/models/processo.py` | `processo_id` FK permite verificar `andamentos` para conflito de prazos |

---

## Status de implementação

### ✅ Fase 1 — Banco de dados

- `shared/models/agendamento.py` — modelo `Agendamento`
- `shared/models/disponibilidade_advogado.py` — modelo `DisponibilidadeAdvogado`
- `shared/models/escritorio.py` — campos `telefone_advogado` e `timezone`
- `shared/models/cliente.py`, `interacao.py`, `processo.py` — relacionamentos
- `shared/models/__init__.py` — exportações
- `alembic/versions/20260630_1000_add_agendamento_tables.py` — migration completa

### ✅ Fase 2 — Backend core

- `shared/schemas/agendamento.py` — schemas Pydantic completos
- `feature_1_ia_personalizada/services/agendamento/detector.py` — `AgendamentoDetector` com JSONB fallback
- `feature_1_ia_personalizada/services/agendamento/__init__.py`
- `feature_1_ia_personalizada/api/routes/agenda.py` — `/agenda/*`
- `feature_1_ia_personalizada/api/routes/agendamentos.py` — `/agendamentos/*`
- `feature_1_ia_personalizada/api/app.py` — routers registrados com `_guard`

### ✅ Fase 3 — IA + WhatsApp

- [x] Intenção `agendar_reuniao` em `nodes/intent.py` (threshold de confiança 0.80 + keywords fallback em `state.py`)
- [x] Nó `agendamento` no LangGraph (`services/ai/nodes/agendamento.py`, registrado em `orchestrator.py`)
- [x] `AgendamentoNotifier` (`services/agendamento/notifier.py`) — 8 métodos, flags de idempotência, lock Redis SET NX
- [x] Seleção do cliente (`processar_resposta_cliente`) — early-exit no orchestrator, regex 1/2/3 + matching por label + fallback Claude; popula `data_hora_inicio`/`data_hora_fim`
- [x] Roteamento webhook advogado vs. cliente (`webhook_whatsapp.py`) — só desvia quando há agendamento relevante
- [x] Extração de prazos processuais dos andamentos (`services/agendamento/prazos.py`) — detector evita dia do prazo e véspera; conflito avisa, nunca bloqueia
- [x] Endpoints do Hub complementados: confirmar/sugerir/cancelar disparam WhatsApp via Celery; listagem enriquece cards pendentes com `contexto_conversa` + `conflito_prazo`

### ✅ Fase 4 — Workers Celery

- [x] `expirar_propostas` (cron horário :05)
- [x] `enviar_lembretes` (cron diário 8h15 — cliente E advogado, dedup Redis)
- [x] `enviar_confirmacao_pre_reuniao` (cron horário :10, janela [now+3h, now+4h), flag de idempotência)
- [x] `verificar_conflitos_prazos` (hook pós-andamento em `monitor_processos.py` + cron diário 7h30)
- [x] `processar_resposta_advogado_wpp` + `enviar_mensagens_pos_acao` (webhook/Hub → fila `ia`)
- [x] Registro no `celery_app.py` (task_routes + beat schedule + import)

### ✅ Fase 5 — Frontend

- [x] Cards de aprovação com polling 10s (`components/agendamento/AprovacaoCard.tsx`, integrado na HubPage/Clientes) — contexto de conversa, alerta de prazo, Confirmar | Sugerir | Recusar
- [x] Badge de pendentes no header de Clientes (filtra pendentes ao clicar)
- [x] Aba Agenda — calendário semanal com 3 tipos de item (`components/agendamento/AgendaSemanal.tsx`) — banner de pendentes, empty states, navegação por semana, legenda
- [x] Widget "Próximas reuniões" (`components/agendamento/ProximasReunioes.tsx`, PainelPage) — 3 próximas + contador de pendentes; clique navega para Clientes → Agenda/Lista
- [x] Seção "Horários de atendimento" + campo `telefone_advogado` + prévia de slots (`components/agendamento/HorariosAtendimento.tsx`, ConfigPage)
- [x] API client (`api/agendamentos.ts`) + `GET /agenda/eventos` (agendamentos + prazos da semana)

### 🛡️ Robustez de produção (auditoria pós-implementação)

| Cenário | Comportamento |
|---|---|
| Cliente escolhe slot que **já passou** (respondeu perto do fim das 48h) | Sistema regenera 3 novas opções na mesma resposta — advogado nunca recebe pedido de horário inválido |
| **Race**: outro cliente confirmou o mesmo slot entre a proposta e a escolha | Idem — reproposta automática excluindo o horário ocupado |
| Sem alternativa ao repropor | Status → `expirado` + mensagem amigável ("escritório entrará em contato") |
| Cliente pede reunião com **proposta antiga vencida** (worker ainda não varreu) | Nó expira a antiga e gera proposta nova na hora |
| Cliente tem **NPS pendente E proposta de horários** e responde "1" | Seleção de horário tem prioridade; NPS não captura a mensagem |
| Advogado com **várias solicitações** responde "1" no WhatsApp | Ack informa qual foi confirmada + mostra a próxima da fila (dá para despachar tudo por WhatsApp) |
| Reunião **remarcada** (sugerir → reconfirmar) | Flags de confirmação/pré-reunião são resetadas — cliente recebe confirmação e lembretes da NOVA data; dedup do lembrete 24h inclui a data |
| Workers Celery + asyncio.run | `worker_session_factory` global (NullPool) em **todos** os workers e serviços de worker (agendamento, dispatcher, relacionamento, hub_advogado, orchestrator, whatsapp service, worker_queries, processo_state) — elimina "Future attached to a different loop" na raiz |
| Polling da Agenda (15s) | Varredura de prazos cacheada no Redis por 2 min (`agenda_prazos:{eid}`) |
| **Prazos relativos** ("prazo de 15 dias úteis") | Calculados em dias úteis (CPC art. 219; "corridos" quando explícito) a partir da âncora — data no próprio texto ou `data_ultimo_andamento`. Sem âncora confiável, não arrisca. Datas calculadas levam `estimado=true` e aparecem com **≈** na Agenda |
| **Tempo real (SSE)** | `GET /agendamentos/stream` (Redis pub/sub, canal `agendamento_ev:{eid}`): toda transição de estado publica evento; o frontend invalida as queries — card some em milissegundos. Polling vira fallback (10→60s pendentes, 15→60s agenda com stream conectado). Publicação é best-effort: Redis fora nunca quebra uma confirmação |
| **Feriados + recesso forense** | Dias úteis pulam feriados nacionais (fixos + móveis via Páscoa/Meeus) e o recesso do CPC art. 220 (20/12–20/01). Feriados estaduais/municipais fora → resultado segue `estimado` |
| **Performance dos workers (medida)** | Benchmark real (`scripts/benchmark_worker_db.py`): NullPool ≈395ms/query vs pooled ≈180ms. Hot path (`executar_fluxo_orquestrador`) usa `create_worker_session_factory(pooled=True)` + dispose por task — reusa conexão dentro da task (~1,5–3s economizados por mensagem), sem cruzar event loops |
| **Google Calendar** | OAuth2 por escritório (`/google-calendar/auth-url|callback|status|disconnect`; refresh token Fernet em `Escritorio`; migration `20260707_1000`). Confirmação → evento na agenda (a secretária vê); cancelar/remarcar remove; freeBusy filtra horários ocupados externamente nas 3 origens de proposta (nó IA, /sugerir, /agenda/slots). Tudo best-effort; desabilitada sem `GOOGLE_CALENDAR_CLIENT_ID/SECRET/REDIRECT_URI` |

### 🧪 Testes

- `feature_1_ia_personalizada/tests/unit/test_agendamento_fluxo.py` — 70 testes: prazos, números,
  interpretação de respostas (advogado e cliente), lock "primeiro ganha", threshold de intenção,
  nó LangGraph com banco (SQLite in-memory), reproposta por slot passado/ocupado, renovação de
  proposta obsoleta, fila de pendências do advogado e guard NPS×seleção
