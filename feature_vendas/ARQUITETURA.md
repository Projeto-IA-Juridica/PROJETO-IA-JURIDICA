# Máquina de Vendas — Arquitetura e Build

> Documentação técnica do que foi construído em `feature_vendas/`. O playbook comercial (funil, plays, metas) está em [PLAYBOOK_VENDAS.md](PLAYBOOK_VENDAS.md). Este arquivo cobre o código: como funciona, como rodar, o que falta plugar.

Princípio de projeto: **camada fina que reusa o produto.** `feature_vendas` importa de `feature_1_ia_personalizada` e `shared`, **nunca o contrário**. O produto não sabe que vendas existe. O tenant de vendas é configuração (`VENDAS_TENANT_ID`), não código especial no orquestrador.

---

## O roteiro, mapeado no código

```
1. UPLOAD      api/routes/leads.py            POST /vendas/leads/importar
                 └─ filtragem.py (ICP score)  → classe A/B/C, descarta C e desqualificados

2. ENRIQUECE   workers/maquina_vendas.py      enriquecer_alvos (cron 10min)
                 └─ enriquecimento.py         OAB → processo → traduz → mensagem-espelho
                    (reusa JuridicalTranslator do produto)

3. VALIDA      validacao.py                   confere CNJ, movimentação, matéria sensível
                 ├─ confiança ≥ 70  → fila_envio
                 ├─ confiança < 70  → fila_excecao (humano revisa em /vendas/leads/excecao)
                 └─ template B      → fila_envio (genérico, nada a validar)

4. DISPARA     workers/maquina_vendas.py      disparar_frios (cron 5min)
                 └─ dispatcher_pacing.py      janela, jitter, cap+warm-up, circuit breaker
                    humanizacao/cadencia.py   "digitando" + delay no envio

5. CADÊNCIA    workers/maquina_vendas.py      avancar_cadencia (toque 2 D+3, toque 3 D+7)
                 └─ respondeu → sai da cadência, status vira "respondeu"

6. FUNIL       o produto assume: a Clara (persona do tenant de vendas) atende no
               vitrine com todo o motor de humanização, qualifica, detecta quente
               e agenda a call via Agendamento Inteligente.
```

---

## Motor de humanização (`services/humanizacao/`)

O que faz a conversa não parecer robô. Quatro peças independentes e testáveis:

### `chunker.py` — quebra de texto
- `quebrar(texto)` → lista de 1–3 balões curtos (alvo 130 chars, teto 220).
- `limpar(texto)` remove **emoji, markdown, bullets e travessão** (os tiques de LLM que sobrevivem ao prompt). Travessão vira vírgula.
- Resposta curta continua 1 balão só (o caso mais natural). Textão vira rajada.

### `cadencia.py` — ritmo
- `calcular_ritmo(recebido, chunks)` → tempos de **leitura → digitação → pausa entre balões**, todos com jitter (nada determinístico — timing constante é o tique nº 1).
- `EntregaHumanizada.responder(...)` executa a sequência: tick azul (marcar como lida), pausa de leitura, e cada balão com **"digitando..." proporcional ao tamanho** via delay nativo do Evolution.
- Digitação ~11–14 cps; teto por balão 6,5s; leitura satura em ~6s. Uma resposta típica leva 6–14s.

### `buffer.py` — esperar a pessoa terminar
- Resolve o problema clássico: pessoa manda 3 mensagens picadas, bot responde 3 vezes e se entrega.
- `aguardar_e_consolidar(...)` implementa **debounce distribuído sem lock** via contador de sequência no Redis: cada mensagem reinicia a janela de silêncio (4,5–7s texto, 7–10s áudio); só a última invocação responde, as outras desistem. Funciona com N workers Celery em paralelo. Teto de 25s para quem escreve sem parar.

### `estilo.py` — como a Clara escreve
- `ESTILO_WHATSAPP` — regras de escrita (curto, sem emoji/markdown/travessão, voz de gente, uma ideia por mensagem). Vale para qualquer persona, inclusive as dos escritórios no produto.
- `CLARA_PERSONA` — objetivo (fazer viver o produto, não explicar), as 3 trilhas de demo, qualificação conversacional, quando chamar humano.
- `REGRA_IDENTIDADE` — **a regra de honestidade (ver abaixo). Não remover.**
- `evolution_humano.py` — wrapper do EvolutionClient que adiciona `delay`/`presence` no sendText, sem tocar o cliente do produto.

---

## A regra de identidade — leia isto

Você pediu "impossível descobrir que é IA, só se for perguntada". Implementei **exatamente isso**: humanização máxima (timing, digitando, buffer, quebra, voz), e a IA não anuncia que é IA — conversa normal. A única exceção, gravada em `estilo.REGRA_IDENTIDADE`:

> Se perguntarem **diretamente** se é uma IA/robô/bot/pessoa de verdade, a Clara fala a verdade, na hora, e usa como gancho: *"sou uma IA sim. e é justamente essa a demonstração: se você levou até agora pra perceber, seus clientes também levariam."*

Por que essa linha fica, e por que ela é a favor de vocês:

1. **O comprador é advogado.** Um advogado que descobre depois que foi enganado no primeiro contato não vira cliente — vira processo ou post. A marca de vocês é confiança; o pitch é compliance-first.
2. **O produto se vende como "IA que atende".** Se a IA de vendas mente sobre ser IA, o produto mente sobre o produto. A revelação honesta É o pitch mais forte que existe.
3. **Negar ser IA quando perguntado diretamente** é o único ponto que seria indefensável numa discussão pública, contratual ou regulatória — e o marco legal de IA + o CDC caminham para exigir essa transparência.

Repare: isso não enfraquece nada. A Clara soa 100% humana até alguém desconfiar e perguntar — e aí a resposta honesta vira o fechamento, não a derrota. É a diferença entre *soar humano* (legítimo, e o que faz o produto bom) e *mentir sobre ser humano* (o que traria risco real para vocês).

---

## Filtragem, enriquecimento, validação, pacing

| Módulo | Papel | Reusa do produto |
|--------|-------|------------------|
| `services/filtragem.py` | Score ICP A/B/C, desqualificação. Sem LLM. | — |
| `services/enriquecimento.py` | OAB → processo → mensagem-espelho (Template A) ou genérico (Template B) | `JuridicalTranslator` |
| `services/validacao.py` | Confere CNJ/movimentação/matéria sensível → fila_envio ou fila_excecao | mesmo espírito do `FactChecker` |
| `services/dispatcher_pacing.py` | Janela 8h30–11h dia útil, intervalo 3–12min, **cap com warm-up** (5→30/dia), **circuit breaker** | Redis |
| `services/lead_scoring.py` | Detecção de lead quente (etapa 5): pediu preço/trial/reunião, ou 5+ advogados engajado, ou qualificação completa | — |
| `services/handoff.py` | Escolhe o sócio (round-robin, indicação→Gabriel), monta o briefing, notifica no WhatsApp | Agendamento Inteligente (agenda a call) |

**Handoff e call (etapa 5→6):** quando `lead_scoring` marca quente, `handoff` notifica o sócio com um briefing escaneável e a Clara oferece os horários livres dele. O agendamento da call **reusa o Agendamento Inteligente**: cada sócio é um "advogado" no tenant de vendas com disponibilidade configurada. Nenhum motor de reunião novo.

**Cadência (etapa 5):** `workers/maquina_vendas.py::avancar_cadencia` envia toque 2 (D+3) e toque 3 (D+7) só para quem não respondeu; quem engaja sai da cadência (status `respondeu`). Respeita janela/cap/breaker também nos follow-ups.

**Painel (frontend):** `frontend/hub-react/src/pages/VendasPage.tsx` + `api/vendas.ts` — leads quentes no topo (ação humana), funil ao vivo, upload de planilha e fila de exceção editável. Falta só registrar a rota no router do hub.

**Cintos de segurança do chip** (todos em `dispatcher_pacing.py`, porque proteger o chip é proteger a máquina):
- Warm-up: chip novo começa em 5/dia e sobe até 30. Chip novo cuspindo 50 no dia 1 = ban.
- Circuit breaker: 2+ bloqueios no dia → **pausa tudo e exige rearme humano**.
- Cap e contadores no Redis (funciona com múltiplos workers).
- Dedup/opt-out: responsabilidade do worker antes de enfileirar (opt-out é eterno).

---

## Estado do wiring (runtime)

| Item | Situação |
|------|----------|
| **Migration `alvos_vendas`** | ✅ escrita à mão em `alembic/versions/20260714_1000_add_alvos_vendas.py` (down_revision = head `20260707_1000`). Aditiva e inerte. |
| **Rotas no app** | ✅ registradas via `feature_vendas.integration.incluir_rotas(app)` — bloco guardado em `app.py`, no-op se a feature está off. |
| **Tasks no Celery Beat** | ✅ `beat_schedule_vendas()` mesclado em `celery_app.py` (guardado) + import guardado das tasks. |
| **Webhook do vitrine → buffer → Clara → humanização** | ✅ `POST /vendas/webhook` → `conversa_worker.responder_conversa` → `ConversaClara.processar` (buffer + Claude com `system_prompt_clara()` + `EntregaHumanizada`). |
| **Detecção de lead quente + handoff** | ✅ `lead_scoring` + `handoff` no `conversa_worker` (notifica sócio, marca `quente`). |
| **Persona da Clara gravada** | seed imprime `system_prompt_clara()`; gravar no campo de persona do tenant. |
| **Descoberta automática por OAB** | interface `DescobridorProcessos` como `None` (Escavador futuro). Você faz a descoberta e informa `processo_cnj` → **não é bloqueador**. |

### Isolamento — pontos de contato com o produto (todos guardados/inertes)

O produto boota e roda idêntico com a feature desligada (`VENDAS_TENANT_ID` ausente) ou a pasta removida. Os únicos toques no código do produto:

1. `app.py` — um `try/except` que chama `incluir_rotas(app)` (no-op se off).
2. `celery_app.py` — um `try/except` que mescla `beat_schedule_vendas()` e importa as tasks (no-op se off).
3. `alembic/versions/…add_alvos_vendas.py` — migração **aditiva** (cria uma tabela nova; não altera nada existente).

Tudo mais vive sob `feature_vendas/` (inclusive o model, em `feature_vendas/models/`, e o painel, app frontend separado). O webhook é `/vendas/webhook`, separado do `/webhook/whatsapp`. As rotas têm guard de tenant (403 para qualquer escritório que não seja o de vendas).

---

## Variáveis de ambiente (`feature_vendas/config.py`)

Todas opcionais — sem elas o disparo desliga limpo (o vitrine/Clara seguem na infra normal):

```bash
VENDAS_TENANT_ID=...              # id do escritório interno (sai do seed)
VENDAS_VITRINE_URL=https://wa.me/55XXXXXXXXXXX   # CTA dos templates
VENDAS_EVOLUTION_INSTANCE=...     # instância do CHIP DE DISPARO (separado do vitrine!)
VENDAS_EVOLUTION_API_KEY=...
VENDAS_CHIP_INICIADO_EM=2026-07-20   # 1º disparo do chip (base do warm-up)
```

> **Isolamento de chips:** disparo, vitrine e produção são **três chips/instâncias separados**. Se o chip de disparo cair (o de maior risco), o vitrine e o produto não sofrem nada. Tenha um chip B aquecendo de reserva desde o dia 1 — disparo frio automatizado viola os termos do WhatsApp e o chip é peça descartável por design.

---

## Como rodar (quando for ativar)

```bash
# 1. Migration da nova tabela
alembic revision --autogenerate -m "alvos_vendas"
alembic upgrade head

# 2. Criar o tenant de vendas + ver o prompt da Clara
python -m feature_vendas.seeds.tenant_vendas
# → exporte o VENDAS_TENANT_ID impresso

# 3. Subir a planilha (CSV com cabeçalho descrito em routes/leads.py)
#    POST /vendas/leads/importar

# 4. Workers já rodando (enriquecer_alvos, disparar_frios) processam a fila.
#    Acompanhe em GET /vendas/leads/funil e revise GET /vendas/leads/excecao
```

Colunas do CSV: `nome_escritorio, nome_contato, oab, cnpj, whatsapp, cidade, area, num_advogados, tem_vaga, anuncia, instagram_ativo, whatsapp_publico`

---

## Testado

Módulos de lógica pura validados manualmente (quebra de textão em balões, ritmo com jitter, score ICP A/B/C, validação de espelho incluindo rejeição de matéria sensível e CNJ inválido). Falta suíte pytest formal — recomendado antes de ligar o disparo real, principalmente para `buffer.py` (debounce concorrente) e `dispatcher_pacing.py` (warm-up e breaker).
