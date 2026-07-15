# 09 — Máquina de Vendas (feature_vendas)

Ferramenta **interna** que usa a tecnologia do produto para vender o produto. Uma
persona de IA chamada **Clara** prospecta advogados pelo WhatsApp com humanização
extrema, qualifica o lead e passa o bastão para um sócio fechar. É dogfooding: a
IA de vendas é o próprio Concierge apontado para nós.

> **Princípio de isolamento (inegociável):** desligada (sem `VENDAS_TENANT_ID`),
> o produto principal boota e roda idêntico — zero rotas, zero tasks, nada tocado.
> Os únicos pontos de contato com o produto são guardados por try/except e
> feature-flag. Verificado por boot real: produto com vendas OFF = 75 rotas, zero
> de vendas; ON = 6 rotas + 4 tasks.

## O funil de ponta a ponta

```
DESCOBERTA (você faz)  →  planilha CSV de alvos
   │ filtragem ICP (score A/B/C) — C não é abordado
ABORDAGEM  →  3 plays (espelho / currículo / inbound), máx. 5–10/dia
   │
CLARA trata o lead no WhatsApp (buffer → LLM Opus → entrega humanizada)
   │ qualificação conversacional (3 perguntas, sem parecer formulário)
HANDOFF  →  lead quente vai para um sócio (Gabriel ou sócia), SLA 15 min
   │ a Clara agenda a call de 20 min na agenda do sócio
FECHAMENTO  →  trial 7 dias (self-service) ou call (Profissional+)
```

## Descoberta e a pergunta "a IA pega os processos sozinha?"

- **Descobrir quais processos são de um advogado a partir da OAB:** o sistema
  NÃO consegue (o DataJud não indexa por OAB — é o mesmo bloqueio da F3). Essa
  parte é manual: você monta a planilha.
- **Dado o número CNJ de um processo, buscar a movimentação recente:** consegue
  hoje, sem Escavador, reusando `DataJudClient.buscar_andamentos_async(cnj)`. Se a
  planilha trouxer a coluna `processo_cnj`, a máquina busca o andamento, traduz e
  monta a mensagem-espelho sozinha.

## Filtragem (ICP scoring)

Pontos: 5–15 advogados (+3), 2–4 (+2), área cível/trabalhista/previdenciário/
família (+2), vaga aberta de secretária (+3), anuncia online (+3), Instagram
ativo (+1), WhatsApp publicado (+1).
- **A (≥6):** abordagem premium. **B (3–5):** espelho padrão. **C (<3): não abordar.**
- Desqualificação automática: enterprise com legado, solo sem carteira,
  contencioso de massa, fora das áreas atendidas.

## Os 3 plays de abordagem

1. **Mensagem-espelho** (A/B frios): cita um processo real do escritório com
   movimentação recente e mostra a notificação que o cliente dele teria recebido.
2. **Currículo da Clara** (A com vaga aberta): peça A4 formato currículo
   ("pretensão salarial R$ 997/mês, sem INSS, 24h") com QR do número-vitrine.
3. **Inbound/indicação:** resposta em < 5 min, CTA único = conversar com a Clara.

## A Clara (persona de vendas)

Objetivo: não é explicar o produto, é fazer o advogado **viver** o produto,
conduzindo para uma de três demonstrações (processo real / agendamento / dúvida
jurídica). Arquivo da persona: `feature_vendas/services/humanizacao/estilo.py`.

### Regra de identidade (não-removível)
A Clara soa como gente, mas **se perguntarem se é uma IA/robô/pessoa, ela responde
a verdade, sempre** — nunca afirma ser humana, nunca nega ser IA. E usa isso como
fechamento: *"sou uma IA sim, e é essa a demonstração — se você levou até agora
pra perceber, seus clientes também levariam."* Três razões: vende-se para
advogados (enganar queima a marca), o produto é vendido como IA transparente, e
negar seria indefensável (CDC, LGPD, marco de IA). Isso está no prompt e é
testado (não pode sumir num refactor).

### Conhecimento de produto
Existe um módulo `services/produto.py` (o que faz, preços, o que NÃO faz,
compliance, objeções) para a Clara não travar nem alucinar em "quanto custa?".
**Status: escrito mas ainda não ligado no prompt** (falta 1 linha) — pendente de
ativação.

## Humanização (o diferencial técnico)

Três camadas, em `services/humanizacao/`:

- **buffer.py** — espera a pessoa terminar de falar. Rajada de N mensagens picadas
  vira UMA entrada consolidada (debounce distribuído por sequência no Redis, sem
  lock, funciona com N workers concorrentes). Janela de silêncio 4,5–7s (texto) /
  7–10s (áudio), com jitter; teto de 25s.
- **chunker.py** — quebra a resposta em 1–3 balões curtos. Quebra de linha é
  **fronteira dura** (ideia nova = mensagem nova). Remove tiques de LLM: emoji,
  markdown, travessão, bullet. Alvo ~130 chars/balão, máx. 220.
- **cadencia.py** — o ritmo: tick azul (marca como lida) → pausa de leitura →
  "digitando" (delay nativo da Evolution) → balão → respiro → próximo balão. Todo
  intervalo tem jitter; **os limites min/max também têm jitter** — balões que
  batem no teto NÃO saem com delay idêntico (timing repetido é o tique nº 1 de
  bot). Latência total típica 6–14s.

## Detecção de lead quente e handoff

Gatilhos (qualquer um): pediu preço/trial/proposta/reunião; escritório 5+
advogados engajado; qualificação completa + score alto. Ao disparar: a Clara
agenda a call na agenda do sócio (round-robin persistido no Redis; leads de
indicação vão para Gabriel), e o sócio recebe no WhatsApp um **briefing** com o
resumo da conversa. SLA de primeiro contato humano: 15 min. Handoff é idempotente
(alvo promovido uma vez só). Serviço: `services/handoff.py`.

## Opt-out (o que separa prospecção de spam)

`services/opt_out.py`: detecta pedido de parar (regex barata, antes de gastar
token), marca o alvo como descartado + `opt_out`, manda UMA confirmação e nunca
mais aborda — **nem se o número voltar numa planilha futura** (a importação pula
quem já optou por sair). A importação também deduplica por número. Falso positivo
custa um lead; falso negativo custa a reputação — o código erra para respeitar o
pedido.

## Tabela `alvos_vendas` e tenant

Tabela própria e separada de `leads_prospeccao`. Campos: dados do escritório,
`whatsapp`, `origem`, `template_usado`, `processo_cnj`, `status`
(`novo`→`abordado`→`respondeu`→`quente`→`descartado`), `score`, `proximo_toque_em`,
`metadados` (JSONB — inclui `opt_out`, gatilho do handoff, sócio responsável).
Tudo no tenant de vendas (`VENDAS_TENANT_ID`).

## Envs necessárias
`VENDAS_TENANT_ID`, `VENDAS_VITRINE_URL`, `VENDAS_EVOLUTION_INSTANCE`,
`VENDAS_EVOLUTION_API_KEY`, `VENDAS_CHIP_INICIADO_EM`, `VENDAS_SOCIOS`
(`Nome:numero:id,...`). Não precisa de serviço novo no Railway — só instâncias
novas na Evolution (chips diferentes) e essas envs.

## Painel interno
App Vite **separado** em `feature_vendas/painel/` (porta 5199), fora do hub dos
clientes. Não faz deploy: roda local apontando para a API
(`VITE_API_TARGET=https://sua-api npm run dev`). Seções: leads quentes, funil,
upload de planilha, fila de revisão humana.

## Segurança (auditada)
- `/vendas/webhook` isento de JWT/CSRF (declarado explícito nos middlewares, não
  monkeypatch), autenticado por apikey `compare_digest`.
- Rotas internas do painel exigem JWT do tenant de vendas (403 fora dele).
- Queries filtram por `escritorio_id`; zero SQL cru; nenhum segredo/PII em log.
- 68 testes cobrindo humanização, funil, contexto, opt-out e segurança.

## Documentos relacionados
- Playbook operacional: `feature_vendas/PLAYBOOK_VENDAS.md`
- Arquitetura técnica: `feature_vendas/ARQUITETURA.md`
