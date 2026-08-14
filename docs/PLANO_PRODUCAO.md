# Plano de Produção — Entrega ao Primeiro Cliente

> Auditoria de prontidão realizada em 21/07/2026 sobre a `main` (commit `c448ec4`).
> Contexto: pivô para modelo sob demanda (instância dedicada por cliente), primeiro
> cliente = escritório médio com carteira corporativa (muitos processos).
> Proposta comercial prevê go-live em 4–6 semanas com 4 funcionalidades sob medida.

**Veredito:** a base é sólida, mas o projeto **não está pronto para entrega hoje**.
Esforço total estimado até o go-live: **~90–165 h** (60–115 h das quatro
funcionalidades + gaps; ~30–50 h do restante).

---

## P0 — Bloqueia qualquer entrega (resolver imediatamente)

### 0. PRODUÇÃO ESTÁ FORA DO AR (descoberto em 14/08/2026)

Smoke test contra os domínios de produção retorna **404 `Application not found`**
com header `x-railway-fallback: true` — resposta do edge do Railway quando **não
há aplicação rodando** no domínio:

| Alvo | Resultado |
|---|---|
| `projeto-ia-juridica-production-4bb1.up.railway.app` (API) | 404 `Application not found` |
| `amicus.page` (frontend) | 404 (fallback do Railway) |

Não é um endpoint quebrado: **backend e frontend estão ambos fora**. No início
desta auditoria (21/07) o mesmo domínio respondia normalmente (403 com JSON de
JWT ausente), ou seja, caiu no intervalo.

Causas prováveis, em ordem: serviço removido/pausado no Railway, **billing**
(Railway suspende projeto por falta de pagamento), ou deploy que falhou e
derrubou o serviço.

- [ ] Abrir o painel do Railway e verificar status dos serviços e do billing
- [ ] Confirmar se os domínios ainda estão atribuídos aos serviços
- [ ] Redeployar e validar `/health`

**Nada mais pode ser validado em produção enquanto isso não voltar.**

### 1. Suíte de testes quebrada na main (CI vermelho) — 4–6 h

O refactor que removeu o NPS deixou fallout maior do que o mapeado antes.
Estado medido em 14/08 (`pytest` unit + shared):

```
4 arquivos falham na COLETA (ImportError) + 22 testes falhando
1229 testes passando
```

**Falham na coleta** (importam símbolos removidos — `NPSRegistro`,
`TEMPLATE_PESQUISA_NPS`, `query_clientes_nps_pendente`):

- `tests/unit/test_crm_analyzer.py`
- `tests/unit/test_prompts.py`
- `tests/unit/test_send_notifications_queries.py`
- `tests/unit/test_templates.py`

**22 testes falhando** (asserções sobre comportamento removido):

| Arquivo | Falhas | Causa |
|---|---|---|
| `test_whatsapp_service.py` | 10 | `TestEnviarPesquisaSatisfacao` — método removido |
| `test_analytics_calculadora.py` | 9 | esperam `nps_medio`/`nps_anterior` no resumo |
| `test_scheduler.py` | 2 | `agendar_pesquisa_satisfacao` removido |
| `test_agendamento_fluxo.py` | 1 | importa `_processar_resposta_nps` do webhook |

Há ainda **testes de integração** referenciando NPS (`test_crm_real.py`,
`test_analytics_dashboard.py`, `test_analytics_calculadora_real.py`,
`test_confidence_router.py`) — verificar ao subir ambiente de integração.

Corrigir **atualizando os testes para o comportamento novo** (nunca revertendo o
refactor — código do Bruno).

### 2. As 4 funcionalidades vendidas não existem — 60–115 h (com gaps)

| Funcionalidade | Estado | Esforço |
|---|---|---|
| Relatório personalizado por cliente | Não existe (só CSV do escritório) | 16–30 h |
| Agenda diária do advogado | Não existe (só aniversários + dashboard on-demand) | 12–24 h |
| Resumo das conversas de WhatsApp | Não existe | 8–16 h |
| Alerta de cliente em risco → advogado | Não existe (alerta atual é SLA de escalação; CRM não notifica ninguém) | 8–16 h |
| Gaps estruturais compartilhados (ver seção Gaps) | — | +16–29 h |

### 3. Celery beat ausente em produção — 2–4 h

`railway.worker.json` define só o **worker**; não há processo `celery beat` em
nenhuma config de deploy (o Procfile tem a linha, mas Railway usa os JSONs).
Sem beat, **nada agendado roda**: monitoramento de processos, mensagens de
relacionamento, lembretes, dispatcher de agendadas — e as futuras agenda diária
e relatórios agendados.

- [ ] Conferir no painel Railway se worker e beat existem e estão de pé
- [ ] Criar serviço beat (`celery -A feature_1_ia_personalizada.workers.celery_app beat`)
- [ ] Alerta se worker/beat caírem (ver P1.8)

### 4. `/escalacoes` — 500 em 100% das chamadas · CAUSA CONFIRMADA — 1–2 h

Reproduzido localmente sem banco. A rota monta o filtro assim
(`api/routes/escalacoes.py:127`):

```python
Interacao.metadata_json["escalacao"]["status"].astext == status_filtro
```

Mas `Interacao.metadata_json` é declarado como **`JSON` genérico**
(`shared/models/interacao.py:126`), e `.astext` **só existe no tipo `JSONB` do
dialeto PostgreSQL**. A query estoura na construção, antes de tocar o banco:

```
AttributeError: Neither 'BinaryExpression' object nor 'Comparator' object
has an attribute 'astext'
```

Ou seja: **a aba de escalações nunca funcionou em nenhum ambiente** — não é
intermitente nem de dados. Correções possíveis: trocar a coluna para `JSONB`
(migration; é Postgres em prod), ou reescrever o filtro com
`.op("->")`/`cast(...)` compatível com `JSON`.

**Bug irmão, silencioso** — `services/crm/aggregator.py:173` lê
`metadata_json["escalacao_status"]` (chave **plana**), mas o
`services/escalacao/manager.py:74` grava a estrutura **aninhada**
`{"escalacao": {"status": ...}}`. A expressão é válida, então não estoura: apenas
**conta sempre zero escalações** — a contagem de escalações pendentes/rejeitadas
que alimenta a análise de CRM está sistematicamente errada.

### 4b. Validação ponta a ponta pendente — 2–4 h

Ninguém confirmou a análise de petição funcionando no site após os fixes de
CSRF/CORS. Validar (assim que produção voltar): chat, CRM "Analisar",
agendamento, RAG/upload, onboarding.

---

## Estado de cada funcionalidade (auditoria de 14/08)

Método: cruzamento de rotas × chamadas do frontend, tasks × beat × filas do
Celery, execução da suíte de testes e leitura dos caminhos críticos.
Como produção está fora do ar, **nenhum item pôde ser validado em runtime real** —
o que segue é análise estática + testes.

| Funcionalidade | Estado | Observação |
|---|---|---|
| Atendimento WhatsApp (Clara) | Provável OK | Orquestrador com fallback por keywords se o LLM falhar; webhook e templates testados |
| Hub do Advogado — chat | Provável OK | Fluxo síncrono, histórico e memória de conversa cobertos por testes |
| Hub — análise de petição | **Corrigido, não validado** | Parse JSON + `max_tokens` corrigidos nesta sessão; falta confirmar no site |
| Hub — classificação de intenção | OK (degrada bem) | Se o JSON vier inválido, cai em `duvida_juridica` — não quebra |
| **Escalações** | **QUEBRADO** | 500 em toda listagem — ver P0.4 |
| CRM — análise de cliente | Parcialmente correto | Classificação funciona (parse tolerante), mas contagem de escalações sempre zero (bug irmão do P0.4) |
| CRM — analisar escritório | Risco alto | Depende de Celery; se worker/beat não sobem, retorna `job_id` e nada acontece — e o rate-limit de 4 h é consumido mesmo assim |
| Monitoramento de processos | Depende do beat | Task correta e roteada; sem beat não roda (P0.3) |
| Mensagens de relacionamento | Depende do beat | Aniversários/datas/sem-contato agendados; idem |
| Agendamento inteligente | Provável OK | 97 testes no fluxo; `dispatcher_agendadas` idempotente |
| RAG / base de conhecimento | Provável OK | Ingestão, busca e dedup cobertos; usa Voyage + pgvector |
| Analytics / painel | Métrica trocada | Passou de NPS para score CRM; **9 testes desatualizados** ainda esperam `nps_medio` |
| Prospecção / captação | Degradado por dependência | Clientes LinkedIn/Explorium entram em "modo degradado" sem chave; DataJud não traz partes (ver troca de API) |
| Billing / Stripe | A aposentar | Degrada sem chave; telas precisam sumir no modelo sob demanda |

### Achados transversais (bons)

- **Fiação frontend ↔ backend íntegra**: 60 caminhos chamados pelo frontend, **100 % com rota correspondente** entre as 76 do backend. Nenhuma chamada órfã.
- **Celery consistente**: toda task do `beat_schedule` existe registrada; toda rota de fila aponta para task real; nenhuma fila roteada fora do worker (exceto `dead_letter`, que é intencional).
- **Parse de LLM**: os classificadores (`intent`, `hub_advogado_classifier`, `crm/analyzer`) já toleram falha — extraem JSON entre chaves ou caem em fallback. O parse frágil que derrubou a petição era o único do tipo.

### Achados transversais (atenção)

- **Tasks sem rota de fila**: `enviar_boas_vindas_escritorio` e `processar_resposta_advogado` são disparadas pelo webhook do WhatsApp mas **não têm entrada em `task_routes`** ⇒ caem na fila default `celery`, que **o worker não consome**. Ficam enfileiradas para sempre: o e-mail de boas-vindas do escritório e a resposta do advogado via WhatsApp nunca são processados. (As tasks `vendas.*` idem, mas o módulo está desabilitado.)
- **Testes de integração não rodam localmente** (exigem Postgres/Redis) — a validação real depende do ambiente de integração ou de produção de volta.

---

## Gaps entre as funcionalidades

As 4 features dependem de pontes entre módulos que hoje não existem.

### Gap A — Atribuição de responsabilidade (o mais estrutural) — +8–16 h

`Processo.advogado_responsavel_id` existe no modelo mas **só o seed preenche**
(import CSV e cadastro real não gravam). `Cliente` não tem advogado responsável.
Sem isso, a agenda diária não sabe para quem mandar e o alerta de risco não sabe
quem avisar.

- [ ] Preencher `advogado_responsavel_id` no import CSV e na UI
- [ ] Responsável em `Cliente` (coluna ou derivado do processo mais recente)
- [ ] Tela simples de atribuição

### Gap B — CRM não emite eventos

`crm_nivel`/`crm_score` são gravados e ninguém consome. Feature 4 precisa de
gatilho pós-análise + estado anti-spam (ex.: `crm_alertado_em`).

### Gap C — Não há serviço unificado "notificar advogado"

Notificação a clientes finais é madura; a advogados só existe dentro da
escalação (via `Usuario.whatsapp_numero`). Features 2 e 4 precisam de um serviço
único com preferências (horário, opt-out) — construir uma vez.

### Gap D — Não há motor de composição de relatório

Exportador atual só gera CSV. Feature 1 precisa de template WhatsApp e/ou PDF
(PDF ⇒ dependência nova, ex. WeasyPrint). **Decidir formato antes de começar.**

### Gap E — Sumarização não existe

Nenhum serviço resume conversas. Feature 3 cria; features 1 e 2 reutilizam
(resumo no relatório; "o que aconteceu ontem" no digest).

### Gap F — Preferências por feature sem lugar no modelo

Horário do digest, frequência de relatório, limiar de alerta — resolver junto
com as feature flags do pivô (JSONB em `Escritorio`/`Usuario`).

### Infra existente para REUTILIZAR (não reconstruir)

- `dispatcher_agendadas` + tabela `mensagens_agendadas` (idempotente, retry)
- `CRMDataAggregator` (consolida por cliente tudo que o relatório precisa)
- Envio WhatsApp via Evolution + templates
- RedBeat + `Escritorio.timezone` (agendamento por fuso do cliente)

### Ordem de construção imposta pelos gaps

```
Gap A → Gap C → Feature 4 (alerta de risco; valida A+C com a feature mais barata)
Feature 3 (resumo — cria o serviço de sumarização, Gap E)
Feature 2 (agenda diária — usa A + C + E)
Feature 1 (relatório — usa A + D + E; decidir formato antes)
```

---

## Mudança planejada — trocar a API de processos (DataJud → provedor comercial)

**Decisão anotada:** migrar a fonte de dados processuais para uma API comercial
mais completa e mais imediata. O DataJud (CNJ) é gratuito, porém:

- **Não retorna as partes** do processo (foi o que pausou a captação/prospecção);
- Atualiza **em lote, com dias de defasagem** — ruim para a agenda diária e para
  o monitoramento "em tempo real" que o cliente corporativo espera;
- Sem push/webhook (só polling) e cobertura irregular entre tribunais.

**Candidatos** (avaliar custo × cobertura na semana 1–2):

| Provedor | Pontos fortes | Atenção |
|---|---|---|
| **Escavador** (já anotado como plano p/ captação) | Partes, OAB, CNPJ; monitoramento com callback; boa cobertura | Custo por consulta/monitoramento |
| **Judit.io** | Webhooks de andamento; API moderna | Verificar cobertura de tribunais do cliente |
| **Jusbrasil/Digesto** | Cobertura ampla | Custo mais alto; contrato enterprise |
| **Predictus** | Dados estruturados p/ análise | Menos focado em monitoramento push |

**Como implementar sem reescrever** — a superfície atual do `DataJudClient` é
pequena (`consultar_processo`, `buscar_dados_completos`, `buscar_novos_andamentos`,
`buscar_andamentos_async`), usada em 8 arquivos (monitor, prospecção,
orchestrator/chat, rota de processos, ingestão). Plano:

1. Extrair interface `ProcessoDataProvider` com esses 4 métodos (+ `buscar_partes`);
2. Implementar o provedor novo atrás da interface; **DataJud vira fallback**;
3. Seleção por env/config da instância (`PROCESSO_PROVIDER=escavador|datajud`) —
   encaixa no modelo sob demanda: o custo da API premium entra no COGS/mensalidade
   do cliente que a usa;
4. Se o provedor tiver webhook, criar rota de recepção e reduzir o polling do beat.

**Esforço:** 16–32 h (interface + provedor + config; webhook opcional na ponta alta).
**Efeitos colaterais positivos:** destrava a captação/prospecção pausada e melhora
a qualidade da agenda diária (feature 2) e das notificações de andamento.
**Custo recorrente:** somar a assinatura do provedor ao COGS da instância
(reprecificar franquia se necessário).

---

## P1 — Antes do go-live do cliente

### 5. Aplicar o pivô no código — 8–16 h

- [ ] Fechar `POST /onboarding/register` (público hoje) — remover, proteger por
      token admin ou flag `REGISTRO_ABERTO=false`
- [ ] Stripe: não configurar `STRIPE_SECRET_KEY` na instância do cliente (código
      já degrada) e **ocultar telas de plano/trial no frontend**
- [ ] Feature flags por escritório (colunas ou JSONB em `Escritorio`) + esconder
      abas correspondentes no frontend — junto com Gap F

### 6. Runbook de provisionamento de instância dedicada — 8–12 h

Documentar (e testar ao subir a instância deste cliente): serviços Railway
(web + worker + beat + Postgres + Redis), todas as env vars (`ANTHROPIC_API_KEY`,
`MODELO_ESCALACAO`, `CORS_ALLOWED_ORIGINS`, `SENTRY_DSN`, `EVOLUTION_API_*`,
chave Voyage, futura `PROCESSO_PROVIDER`), integração do número WhatsApp na
Evolution, build do frontend com `VITE_API_URL` do cliente, domínio, seed do
escritório. A instância deste cliente vira o gabarito.

### 7. Limites e configuração do cliente — 2–4 h

- [ ] `max_processos` (default 100) e `max_clientes` (default 200) → valores do contrato
- [ ] `quota_tokens_mes` → definir a franquia prometida na proposta + comportamento
      ao estourar (avisar/bloquear/cobrar)
- [ ] Conferir `MODELO_ESCALACAO` no Railway (default novo: `claude-opus-4-8`)
- [ ] `escalacao_habilitada` — decidir por cliente

### 8. Base operacional para o SLA prometido — 4–8 h

A proposta promete 99% uptime, resposta 4 h úteis, monitoramento 24/7. Hoje:

- [ ] Confirmar `SENTRY_DSN` configurado em produção (código já integra)
- [ ] Monitor de uptime externo no `/health` (UptimeRobot/BetterStack)
- [ ] Alerta de worker/beat parado (foi exatamente o modo de falha da petição)

---

## P2 — Dívida técnica e riscos (agendar, não bloqueia)

- **Pin do FastAPI é bomba armada**: prod usa `fastapi==0.109.0`; local está em
  0.139, onde o `prometheus-fastapi-instrumentator` quebra **toda** requisição
  (`'_IncludedRouter' object has no attribute 'path'`). Alinhar venv local aos
  pins; tratar upgrade como tarefa própria com teste.
- **Código morto do fluxo antigo de petição**: `/hub/analisar-peticao` (PDF+Celery),
  `/hub/jobs/{id}`, `hub_worker.py`; `pesquisar_jurisprudencia()` sem uso.
- **LGPD/backup**: dump diário vai para artifact do GitHub (90 dias), S3 opcional
  não confirmado. Para dados jurídicos: definir destino, criptografia e retenção
  formal; refletir no contrato.
- Coluna legada `Interacao.satisfacao` (mantida de propósito — documentado).
- 11 TODOs/FIXMEs no código, nenhum crítico.

---

## O que já está bem (não mexer)

- Multi-tenant sólido (isolamento por `escritorio_id` em ~80 arquivos)
- Migrations em dia + `release: alembic upgrade head` no deploy
- CI completo (ruff, black, mypy, pytest) — só precisa voltar ao verde
- Backup diário automatizado (falta formalizar destino)
- Sentry + Prometheus + logs estruturados integrados
- JWT + CSRF cross-site correto + rate limit + guard admin + antiinjeção de prompt

---

## Cronograma sugerido (4–6 semanas da proposta)

| Semana | Entregas |
|---|---|
| **1** | P0 completo (testes verdes, beat/worker no ar, E2E, causa do 500) + fechar registro público + quotas. Iniciar avaliação dos provedores de API de processos. |
| **2–4** | Gaps A/C → Feature 4 → Feature 3 → Feature 2 → Feature 1. Runbook escrito ao subir a instância do cliente. Decidir e contratar provedor de processos. |
| **4–5** | Feature flags + ocultar billing; observabilidade/SLA; integração do provedor novo (se contratado); homologação com dados reais. |
| **5–6** | Treinamento, go-live, período assistido. |

**Regra de decisão:** os itens P0.1 e P0.3 custam meio dia cada e destravam todo
o resto — fazer primeiro, sempre.
