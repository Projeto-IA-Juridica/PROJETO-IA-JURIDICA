# Feature — Agendamento Inteligente

> **Acesso:** advogado e admin
> **Plano:** profissional e enterprise

---

## O problema que resolve

O advogado hoje perde reuniões por fricção: o cliente pede reunião no WhatsApp, o advogado vê depois, esquece de responder, o cliente perde a confiança. Ou o advogado confirma sem checar a agenda e cria conflito com prazo processual.

| Problema | Impacto |
|---|---|
| Cliente pede reunião no chat e não recebe resposta rápida | Sensação de abandono, risco de churn |
| Advogado confirma horário sem checar própria agenda | Duplo agendamento, reagendamentos |
| Reunião marcada no mesmo dia de prazo processual | Pressão, erro, imagem profissional |
| Cliente fica sem confirmação formal | Insegurança, não comparece |
| Agendamento manual fora da plataforma | Dados fragmentados, sem histórico |

---

## Como a feature resolve

O fluxo completo não exige nenhuma ação manual até o momento em que o advogado aprova. O advogado recebe a solicitação **simultaneamente no próprio WhatsApp e no Hub** — e pode aprovar por qualquer um dos dois. O primeiro canal que receber a resposta confirma; o outro se atualiza automaticamente.

```
Cliente escreve no WhatsApp
  └─► IA detecta intenção de reunião
        └─► Sistema busca disponibilidade do advogado
              └─► IA propõe 3 opções ao cliente no WhatsApp
                    └─► Cliente escolhe um horário
                          ├─► WhatsApp envia solicitação ao advogado
                          │     (nome do cliente, horário, contexto da conversa)
                          └─► Hub exibe card de aprovação pendente
                                (mesmas infos + histórico completo + motivo)
                                      │
                          ┌───────────┴────────────┐
                          │                        │
                   Advogado responde          Advogado clica
                   no WhatsApp               no Hub
                          │                        │
                          └──────────┬─────────────┘
                                     │
                               (primeiro ganha)
                                     │
                          Card some do Hub em tempo real
                          WhatsApp envia confirmação ao cliente
                          Registro salvo com canal de aprovação
```

---

## Fluxo detalhado

### Passo 1 — Detecção pela IA

O nó de intenção no LangGraph (`nodes/intent.py`) já classifica mensagens. Adiciona-se a intenção `agendar_reuniao`, ativada por frases como:

- "preciso falar com você"
- "podemos marcar uma reunião?"
- "quando você tem horário?"
- "quero conversar sobre meu processo"

Threshold de confiança mínimo: 0.80 (evita falsos positivos).

### Passo 2 — Busca de disponibilidade

O sistema verifica a `DisponibilidadeAdvogado` cadastrada (janelas de horário semanais), desconta agendamentos já confirmados e propõe **3 opções** nos próximos 7 dias úteis.

Para cada opção proposta, verifica conflito com prazos processuais:
- Busca `andamentos` do processo do cliente com `data_prazo` nos próximos 7 dias
- Se o horário sugerido cai no mesmo dia ou dia anterior a um prazo → marca `conflito_prazo = True` e substitui por outra opção
- Se não há alternativa sem conflito → inclui o horário com aviso ao advogado

### Passo 3 — Proposta ao cliente via WhatsApp

A IA envia mensagem estruturada com as 3 opções. O cliente responde com "1", "2" ou "3" (ou escreve preferência em texto livre — a IA interpreta).

```
Olá, João! Para agendarmos nossa conversa, tenho
os seguintes horários disponíveis:

1️⃣  Terça, 08/07 às 14h
2️⃣  Quarta, 09/07 às 10h
3️⃣  Quinta, 10/07 às 16h

Qual prefere?
```

### Passo 4 — Notificação simultânea ao advogado (WhatsApp + Hub)

Após o cliente escolher, o sistema **não confirma automaticamente**. Cria um `Agendamento` com `status = 'aguardando_advogado'` e aciona dois canais em paralelo:

#### 4a — WhatsApp do advogado

A IA envia mensagem para o número do advogado (`Escritorio.telefone_advogado`) com:

```
📅 Solicitação de reunião

Cliente: João da Silva
Horário: Quarta, 09/07 às 10h

Motivo: "preciso falar sobre meu processo urgentemente,
         tem uma novidade que quero entender"

Responda *1* para confirmar ou *2* para recusar.
```

O sistema aguarda resposta na mesma conversa. A IA reconhece "1", "sim", "confirmar", "ok" como aprovação — e "2", "não", "recusar", "cancelar" como recusa.

#### 4b — Hub (card de aprovação pendente)

Simultaneamente, a seção **Clientes** do Hub exibe um card destacado com:
- Nome e foto (iniciais) do cliente
- Horário escolhido pelo cliente
- **Contexto da conversa** — últimas mensagens trocadas que levaram ao pedido de reunião
- **Motivo detectado** pela IA (frase-chave extraída do chat)
- Alerta se há conflito com prazo processual
- Botões: **Confirmar** | **Sugerir outro horário** | **Recusar**

#### Sincronização entre canais (primeiro ganha)

A aprovação via **qualquer um dos dois canais** é válida e definitiva:

| Canal | Como aprova | Efeito no outro canal |
|---|---|---|
| WhatsApp | Advogado responde "1" ou "sim" | Card some do Hub em até 10s (polling) |
| Hub | Advogado clica em Confirmar | Se advogado responder no WPP depois → IA informa "reunião já confirmada" |

O lock de aprovação é feito via Redis (`SET NX`) para evitar dupla confirmação em caso de resposta simultânea nos dois canais.

Se o advogado sugerir outro horário (por qualquer canal), o sistema volta ao Passo 3 com as novas opções.

### Passo 5 — Confirmação ao cliente

Com aprovação do advogado, o sistema envia confirmação via WhatsApp e salva o agendamento como `confirmado`.

```
✅ Reunião confirmada!

📅 Quarta, 09/07 às 10h
👤 Dr. [nome do advogado]
📋 Assunto: [processo ou tema detectado]

Até lá!
```

### Passo 6 — Lembrete de confirmação 3h antes

A task `enviar_confirmacao_pre_reuniao` roda a cada hora e seleciona agendamentos com `status = 'confirmado'` e `horario_confirmado` entre `now + 3h` e `now + 3h59`. Envia **uma única mensagem** ao cliente (controla com o campo `whatsapp_confirmacao_pre_reuniao_enviado`).

```
Olá, João! Só passando para lembrar da sua reunião
com Dr. [nome] hoje às 10h. 😊

Qualquer imprevisto, é só avisar aqui!
```

O tom é leve e informal — função é reduzir no-shows, não ser mais um lembrete corporativo.

---

## Modelo de dados

### `Agendamento`

```python
class Agendamento(Base, TenantMixin):
    __tablename__ = "agendamentos"

    id:                  int          # PK
    cliente_id:          int          # FK → clientes
    escritorio_id:       int          # FK → escritorios (via TenantMixin)
    interacao_id:        int | None   # FK → interacoes (mensagem que disparou)
    processo_id:         int | None   # FK → processos (contexto)

    # Proposta
    opcoes_horario:      list[datetime]  # JSON — 3 opções geradas pela IA
    motivo_cliente:      str             # trecho da mensagem original

    # Horário confirmado
    horario_confirmado:  datetime | None

    # Status
    # aguardando_cliente | aguardando_advogado | confirmado | cancelado | expirado
    status:              str

    # Conflito de prazo
    conflito_prazo:      bool
    conflito_descricao:  str | None   # ex: "prazo de contestação em 09/07"

    # Controle de notificações
    whatsapp_proposta_cliente_enviado:       bool
    whatsapp_notificacao_advogado_enviado:   bool  # mensagem ao advogado
    whatsapp_confirmacao_cliente_enviado:    bool
    whatsapp_confirmacao_pre_reuniao_enviado: bool  # lembrete 3h antes

    # Canal de aprovação
    # 'whatsapp' | 'hub' | None
    canal_aprovacao:     str | None

    # Timestamps
    criado_em:           datetime
    confirmado_em:       datetime | None
    expirado_em:         datetime | None  # proposta expira em 48h sem resposta
```

### `DisponibilidadeAdvogado`

```python
class DisponibilidadeAdvogado(Base, TenantMixin):
    __tablename__ = "disponibilidade_advogado"

    id:           int   # PK
    escritorio_id: int  # FK → escritorios
    dia_semana:   int   # 0 = segunda … 6 = domingo
    hora_inicio:  time  # ex: 09:00
    hora_fim:     time  # ex: 18:00
    ativo:        bool
```

---

## API — novos endpoints

### Agendamentos

| Método | Endpoint | Descrição |
|---|---|---|
| `GET` | `/agendamentos` | Lista agendamentos do escritório (filtro por status/data) |
| `GET` | `/agendamentos/{id}` | Detalhe de um agendamento |
| `POST` | `/agendamentos/{id}/confirmar` | Advogado confirma o horário escolhido |
| `POST` | `/agendamentos/{id}/sugerir` | Advogado propõe novos horários |
| `POST` | `/agendamentos/{id}/cancelar` | Cancela o agendamento |

### Disponibilidade

| Método | Endpoint | Descrição |
|---|---|---|
| `GET` | `/agenda/disponibilidade` | Retorna janelas cadastradas |
| `PUT` | `/agenda/disponibilidade` | Atualiza janelas da semana |
| `GET` | `/agenda/slots` | Retorna horários livres nos próximos N dias |

---

## Serviços a criar

### `AgendamentoDetector` (`services/agendamento/detector.py`)

Acionado pelo orquestrador LangGraph quando `intencao == 'agendar_reuniao'`.

1. Busca `DisponibilidadeAdvogado` do escritório
2. Desconta `Agendamento` com `status IN ('aguardando_cliente', 'aguardando_advogado', 'confirmado')` no período
3. Verifica conflitos com `andamentos` do processo do cliente
4. Retorna 3 slots livres e sem conflito (ou com aviso de conflito se inevitável)
5. Cria `Agendamento` com `status = 'aguardando_cliente'` e chama o dispatcher WhatsApp

### `AgendamentoNotifier` (`services/agendamento/notifier.py`)

Responsável por todas as mensagens WhatsApp do fluxo de agendamento:

| Método | Destinatário | Quando |
|---|---|---|
| `enviar_proposta_cliente(agendamento)` | Cliente | Após IA gerar os 3 slots |
| `enviar_notificacao_advogado(agendamento)` | **Advogado** | Após cliente escolher horário |
| `enviar_confirmacao_cliente(agendamento)` | Cliente | Após advogado aprovar |
| `processar_resposta_advogado(texto, escritorio_id)` | — | Webhook incoming do advogado |
| `enviar_lembrete(agendamento)` | Cliente + Advogado | 24h antes da reunião |
| `enviar_confirmacao_pre_reuniao(agendamento)` | Cliente | 3h antes da reunião |
| `enviar_cancelamento(agendamento)` | Cliente | Se advogado recusar |

#### `processar_resposta_advogado`

Chamado pelo webhook de mensagens recebidas quando o remetente é o número do advogado. Usa regex simples antes de chamar Claude para não gastar tokens:

```python
CONFIRMAR = re.compile(r'\b(1|sim|confirmar?|ok|pode|confirmado)\b', re.I)
RECUSAR   = re.compile(r'\b(2|n[aã]o|recusar?|cancelar?|nao)\b', re.I)
```

Se não bater em nenhum padrão, Claude interpreta o texto em linguagem natural.

Usa Redis `SET NX` com TTL de 30s na chave `agendamento_lock:{id}` para garantir que aprovação via Hub simultânea não processe duas vezes.

### `AgendamentoWorker` (`workers/agendamento_worker.py`)

Tasks Celery:

| Task | Trigger | O que faz |
|---|---|---|
| `expirar_propostas` | Cron a cada hora | Expira agendamentos `aguardando_cliente` com mais de 48h |
| `enviar_lembretes` | Cron diário às 8h | Envia lembrete WhatsApp ao cliente E ao advogado para reuniões do dia seguinte |
| `enviar_confirmacao_pre_reuniao` | Cron a cada hora | 3h antes da reunião, envia confirmação ao cliente no WhatsApp |
| `verificar_conflitos_prazos` | Hook após novo andamento | Re-verifica agendamentos confirmados vs. novos prazos detectados |
| `processar_resposta_advogado_wpp` | Webhook incoming | Processa resposta do advogado no WhatsApp e confirma/recusa agendamento |

---

## Integração com o LangGraph existente

No orquestrador (`services/ai/orchestrator.py`), após o nó `intent`:

```python
# Novo branch no grafo
if state["intencao"] == "agendar_reuniao":
    graph.add_edge("intent", "agendamento")
else:
    graph.add_edge("intent", "retrieve")  # fluxo normal existente

# Novo nó
graph.add_node("agendamento", agendamento_node)
```

O nó `agendamento` chama `AgendamentoDetector`, gera a resposta com as opções e retorna ao cliente sem passar pelo RAG (não precisa de contexto jurídico para propor horários).

---

## Frontend — mudanças

### Badge de aprovações pendentes

No header da seção **Clientes**, um badge numérico vermelho indica quantos agendamentos estão `aguardando_advogado`. Clicando, filtra a lista mostrando os pendentes no topo.

### Card de aprovação pendente

Na vista **Lista** da página de Clientes, clientes com agendamento pendente ganham um card destacado acima da lista normal. O card exibe **o mesmo conteúdo que o WhatsApp enviou ao advogado**, mais o contexto completo da conversa:

```
┌──────────────────────────────────────────────────────────┐
│  ⏰  João da Silva quer reunião                           │
│  📅  Quarta, 09/07 às 10h                                │
│                                                          │
│  Motivo detectado pela IA:                               │
│  "preciso falar sobre meu processo urgentemente,         │
│   tem uma novidade que quero entender"                   │
│                                                          │
│  Contexto da conversa:                                   │
│  Cliente: quando sai o resultado?                        │
│  IA: ainda não há movimentação registrada...             │
│  Cliente: preciso falar com você sobre isso              │
│                                                          │
│  ⚠️  Prazo de contestação em 10/07 — verifique agenda   │
│                                                          │
│  [Confirmar]   [Sugerir outro horário]   [Recusar]      │
└──────────────────────────────────────────────────────────┘
```

#### Sincronização em tempo real com o WhatsApp

O Hub faz polling leve em `GET /agendamentos?status=aguardando_advogado` a cada **10 segundos**. Quando o advogado responde pelo WhatsApp e o webhook processa a aprovação, o card desaparece no próximo ciclo de polling sem necessidade de WebSocket.

Se o advogado aprovar pelo Hub, a variável `canal_aprovacao = 'hub'` é salva e — caso ele responda no WhatsApp depois — a IA responde automaticamente: _"Reunião já confirmada pelo sistema! Até lá."_

### Aba "Agenda" na seção Clientes

Toggle adicional ao lado de **Lista | Relacionamento**: **Agenda**

Exibe calendário semanal simples com:
- Reuniões confirmadas (cor azul)
- Prazos processuais de clientes (cor vermelha, read-only — vem dos andamentos)
- Slots de disponibilidade cadastrados (cor cinza claro)

### Configuração de disponibilidade

Na página **Configurações**, nova seção "Horários de atendimento":
- Grade semanal (seg–sáb) com hora início / hora fim por dia
- Toggle ativo/inativo por dia
- Campo **telefone do advogado** para receber as notificações WhatsApp (separado do número do escritório usado pelos clientes)
- Prévia dos próximos slots que serão oferecidos aos clientes

---

## O que já existe e será reaproveitado

| Existente | Como aproveita |
|---|---|
| `nodes/intent.py` | Adiciona intenção `agendar_reuniao` sem criar novo arquivo |
| `services/messaging/` (Evolution API) | `AgendamentoNotifier` usa o mesmo dispatcher WhatsApp |
| `TenantMixin` | `Agendamento` herda, isolamento multi-tenant automático |
| `Celery + filas` | Tasks de expiração e lembrete vão na fila `ia` existente |
| `shared/models/interacao.py` | `interacao_id` FK mantém rastreabilidade do que disparou o agendamento |
| `shared/models/processo.py` / `andamentos` | Verificação de conflito de prazos lê `andamentos` já persistidos |
| `Redis` | Debounce de proposta + lock `SET NX` para evitar dupla aprovação entre canais |
| Webhook incoming WhatsApp | Já existe para receber mensagens de clientes — reutiliza para identificar remetente como advogado |

---

## O que precisa ser criado do zero

| Componente | Esforço estimado |
|---|---|
| Migração Alembic (2 tabelas + campo `telefone_advogado` em `Escritorio`) | Baixo |
| `AgendamentoDetector` | Médio |
| `AgendamentoNotifier` (inclui notificação ao advogado + `processar_resposta_advogado`) | Médio |
| Lógica de roteamento no webhook — distinguir advogado de cliente pelo número | Baixo |
| `AgendamentoWorker` (4 tasks) | Médio |
| Endpoints API (7 rotas) | Médio |
| Nó LangGraph `agendamento` | Baixo |
| Frontend — cards de aprovação com polling 10s + contexto de conversa | Alto |
| Frontend — aba Agenda (calendário semanal) | Alto |
| Frontend — configuração de disponibilidade + campo telefone advogado | Médio |

---

## Regras de negócio e restrições

- **Não confirmar automaticamente** — o advogado sempre tem o aval final antes da confirmação ao cliente
- **Aprovação por qualquer canal é válida** — WhatsApp ou Hub; o primeiro que chegar confirma; o outro é ignorado
- **Lock atômico de aprovação** — Redis `SET NX` garante que resposta simultânea nos dois canais não gere dupla confirmação
- **Proposta expira em 48h** — se o cliente não responder, o agendamento vai para `expirado` e o slot volta a ficar disponível
- **Máximo de 3 opções por proposta** — não sobrecarregar o cliente com muitas escolhas
- **Identificação do advogado no webhook** — o webhook verifica se o remetente é `Escritorio.telefone_advogado`; se não for, segue o fluxo normal de cliente
- **Conflito de prazo não bloqueia** — apenas avisa o advogado; ele decide se confirma mesmo assim
- **Sem acesso à agenda externa** — o sistema usa apenas a `DisponibilidadeAdvogado` cadastrada; integração com Google Calendar é melhoria futura
- **Compliance OAB** — o texto das mensagens não pode sugerir resultado do processo; o motivo da reunião é neutro ("conversar sobre seu processo")
- **Fuso horário** — armazenar sempre UTC, exibir no fuso do escritório (campo `timezone` no modelo `Escritorio`)

---

## Métricas a acompanhar (Prometheus)

| Métrica | Tipo | Label |
|---|---|---|
| `agendamentos_criados_total` | Counter | `escritorio_id` |
| `agendamentos_confirmados_total` | Counter | `escritorio_id` |
| `agendamentos_expirados_total` | Counter | `escritorio_id` |
| `agendamentos_conflito_prazo_total` | Counter | `escritorio_id` |
| `tempo_aprovacao_advogado_segundos` | Histogram | `escritorio_id` |

---

## Ordem de implementação sugerida

1. **Migração** — tabelas `agendamentos`, `disponibilidade_advogado` + campo `telefone_advogado` em `Escritorio`
2. **Disponibilidade** — endpoint + tela de configuração com campo telefone do advogado
3. **Detector + nó LangGraph** — IA detecta intenção, gera slots, cria proposta
4. **Notifier — proposta ao cliente** — envia as 3 opções e lê escolha
5. **Notifier — notificação ao advogado** — envia WhatsApp com nome, horário e contexto
6. **Roteamento webhook** — distingue mensagem do advogado vs. cliente pelo número; chama `processar_resposta_advogado`
7. **Endpoints de aprovação via Hub** — confirmar / sugerir / cancelar (com lock Redis)
8. **Frontend — cards de aprovação** — polling 10s, contexto de conversa, desaparece ao confirmar por qualquer canal
9. **Frontend — aba Agenda** — visão semanal
10. **Workers** — expiração automática, lembrete 24h (cliente + advogado), confirmação 3h antes (cliente)
11. **Métricas e alertas**
