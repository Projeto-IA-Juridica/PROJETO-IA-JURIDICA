# Concierge Jurídico Digital

> Plataforma B2B SaaS de IA conversacional para escritórios de advocacia — monitoramento de processos, comunicação proativa com clientes, agendamento inteligente de reuniões, prospecção de leads e hub de análise jurídica para advogados.

![Python](https://img.shields.io/badge/python-3.12+-blue) 
![FastAPI](https://img.shields.io/badge/FastAPI-0.109-green)
![Deploy](https://img.shields.io/badge/deploy-Railway-purple)
![Cobertura](https://img.shields.io/badge/cobertura-70%25%20mínimo-brightgreen)

--- 

## O Problema 

Escritórios de advocacia perdem clientes por falta de comunicação — não por falta de competência. O cliente não sabe o que está acontecendo com seu processo, precisa ligar para obter uma atualização básica, e o advogado gasta horas por semana respondendo perguntas repetitivas no WhatsApp como _"tem novidade?"_ e _"o que significa esse termo?"_.

Ao mesmo tempo, captar novos clientes é artesanal: esperar indicação, pagar por anúncios genéricos ou garimpar manualmente no Jusbrasil sem critério.

---

## A Solução

O **Concierge Jurídico Digital** é um assistente de IA que o escritório implanta em seu WhatsApp em minutos. A partir daí:

- **Clientes recebem atualizações proativas** assim que há movimentação processual, em linguagem simples — sem precisar perguntar
- **Perguntas frequentes são respondidas em segundos** pela IA, com a persona e o tom do escritório
- **Reuniões são marcadas pela própria IA** — o cliente pede "preciso falar com o doutor", a IA propõe 3 horários livres (respeitando prazos processuais e o Google Calendar do escritório) e o advogado só confirma com um toque
- **O advogado é acionado apenas quando necessário** — pareceres, estratégias, situações fora de escopo
- **Novos clientes são descobertos automaticamente** com base nas especialidades reais do escritório (motor pronto; descoberta aguarda integração Escavador)

O resultado: mais clientes atendidos, menos tempo operacional, relacionamento mais próximo e captação sistematizada.

---

## Pitch

> *"Imagine um assistente que conhece todos os seus processos, fala com seus clientes no WhatsApp 24h por dia no seu tom, marca reuniões sozinho respeitando seus prazos e sua agenda do Google, nunca erra um prazo e ainda te indica quem está litigando na sua área de atuação e ainda não tem advogado. É isso que entregamos."*

**Para o advogado:** menos tempo respondendo WhatsApp, mais tempo faturando.
**Para o cliente:** transparência e proximidade que fideliza.
**Para o escritório:** crescimento sem contratar mais assistentes.

---

## Público-Alvo

| Segmento | Perfil | Dor Principal |
|----------|--------|---------------|
| **Escritórios boutique** (2–15 advogados) | Cível, trabalhista, família, previdenciário | Sem estrutura para atendimento proativo; todo cliente precisa ligar para saber novidades |
| **Escritórios em crescimento** (15–50 advogados) | Mais de uma área de atuação | Escalar atendimento sem contratar proporcionalmente |
| **Advogados autônomos** com carteira estabelecida | Qualquer área | Parecer de disponibilidade 24h sem custo fixo de funcionário |

**Fora do escopo atual:** escritórios enterprise com sistemas legados complexos (Projuris, SAJ) — endereçados nas Features 2 e 6 do roadmap.

---

## Como Geramos Valor

### Para o escritório

| Métrica | Impacto |
|---------|---------|
| **Redução de chamadas/WhatsApp manual** | IA responde ~70–80% das perguntas rotineiras sem escalação |
| **Tempo do advogado** | Estimativa de 3–5h/semana economizadas por advogado em atendimento repetitivo |
| **Agendamento sem secretária** | IA negocia horário com o cliente no WhatsApp, evita prazos processuais e sincroniza com o Google Calendar — o advogado só confirma |
| **Fidelização de clientes** | CRM automático identifica clientes em risco de churn antes de perderem o contato |
| **Captação de leads qualificados** | Prospecção baseada em demanda jurídica comprovada, não em cold lead (motor pronto; descoberta aguarda Escavador) |
| **Análise de petições** | Hub do Advogado analisa documentos jurídicos com Claude Opus em segundos |
| **Cobrança self-service** | Assinatura via Stripe com trial de 7 dias, upgrade/downgrade e portal de billing sem intervenção manual |

### Para o cliente final

- Sabe o que está acontecendo com seu processo sem precisar ligar
- Recebe explicações em linguagem simples, não jurídica
- Tem um canal de atendimento disponível a qualquer hora

### Modelo de negócio (SaaS B2B)

Cobrança mensal por escritório com 4 planos. Receita recorrente e baixo churn estrutural — dados, personas e base RAG ficam no sistema, tornando a troca de produto extremamente custosa para o cliente.

#### Planos e funcionalidades (tabela comercial v2)

Assinatura self-service via **Stripe** (checkout, portal de billing e webhooks) com **trial gratuito de 7 dias** em qualquer plano — durante o trial as quotas ficam em ~20% do plano contratado, o suficiente para avaliar sem risco de abuso. Preços fixos publicados; o plano anual dá **20% de desconto**.

| | **Essencial** (`basico`) | **Profissional** | **Escritório** | **Enterprise** |
|---|---|---|---|---|
| **Preço mensal** | R$ 997/mês | R$ 1.997/mês | R$ 4.997/mês | sob consulta |
| **Plano anual (–20%)** | R$ 797/mês | R$ 1.597/mês | R$ 3.997/mês | contratual |
| **Trial 7 dias** | ✅ | ✅ | ✅ | contrato manual |
| **Advogados** | 1 | até 5 | até 15 | ilimitado |
| **Processos monitorados** | 50 | 300 | 500 | ilimitado |
| **Clientes** | 100 | 500 | 10.000 | ilimitado |
| **Tokens Claude Sonnet/mês** | 750K | 2M | 5M | ilimitado |
| **IA WhatsApp 24h + atualizações proativas** | ✅ | ✅ | ✅ | ✅ |
| **Agendamento Inteligente + Google Calendar** | ✅ | ✅ | ✅ | ✅ |
| **Monitoramento de processos** | ✅ | ✅ | ✅ | ✅ |
| **RAG — base de conhecimento** | até 20 documentos | ilimitado | ilimitado | ilimitado |
| **Analytics** | dashboard básico (horas economizadas, % autônomo) | completo + exportação | completo + exportação | completo |
| **CRM Inteligente** | ❌ | ✅ | ✅ | ✅ |
| **Hub do Advogado (Claude Opus)** | ❌ | ✅ 300K tokens/mês | ✅ 1M tokens/mês | ✅ ilimitado |
| **Implantação & suporte** | self-service, email | prioritário | implantação dedicada + SLA | SLA contratual |

Racional da estrutura: o RAG limitado no Essencial garante que **todo** cliente acumula o moat (base de conhecimento própria) desde o dia 1, e o analytics básico fica no plano de entrada porque a métrica "horas economizadas" é o que sustenta a renovação. A escada de preço (2x → 2,5x) torna cada upgrade natural.

Quotas de trial (7 dias): Essencial 150K tokens / 10 processos / 20 clientes · Profissional 400K / 60 / 100 · Escritório 1M / 100 / 500. Ao converter, os limites do plano cheio são aplicados automaticamente pelo webhook do Stripe.

> **Prospecção Inteligente (F3)** está fora da tabela comercial enquanto a descoberta de leads estiver bloqueada (aguarda API Escavador). Quando ativada, entra como diferencial dos planos Profissional+.

> **Implementação pendente da tabela v2:** criar os novos Price IDs no Stripe (mensais e anuais), atualizar `QUOTAS_POR_PLANO`/`LIMITES_POR_PLANO` em `stripe_service.py` (Essencial: 750K tokens, 50 processos, 100 clientes) e o array `PLANOS` do frontend (`billing.ts` — display "Essencial"). O id interno `basico` permanece; clientes existentes no preço antigo (R$ 497) são grandfathered.

#### Valor entregue vs. preço cobrado

O preço de cada plano representa aproximadamente **2–4,5% do valor econômico mensal entregue** ao escritório — calculado sobre economia de tempo dos advogados, secretariado eliminado pelo agendamento, churn evitado e análise de petições.

| Plano | Valor econômico entregue/mês¹ | Preço | % do valor |
|---|---|---|---|
| Essencial | ~R$ 23.000 | R$ 997 | 4,3% |
| Profissional | ~R$ 96.000 | R$ 1.997 | 2,1% |
| Escritório | ~R$ 210.000 | R$ 4.997 | 2,4% |

> ¹ Estimativa para perfil típico de cada plano: inclui tempo de advogado recuperado (3–5h/semana/advogado × R$ 180/h), tempo de secretariado eliminado pelo Agendamento Inteligente (negociação de horários, lembretes e remarcações automatizados), churn evitado pelo CRM (~17% de redução, ~R$ 7.150/cliente/ano), nova receita gerada pela prospecção inteligente (6 novos clientes/mês × R$ 5.500 ticket médio no plano Profissional) e análise de petições via Hub do Advogado (2h economizadas/petição × R$ 180/h).

#### Margens por plano (modelo com sócios como equipe)

Custos variáveis por cliente: Claude API (com prompt caching ativo) + infra Railway pro-rata + Stripe 2,5%. DataJud CNJ como fonte de dados primária (gratuito). Impostos ~15% (Simples Nacional).

| | Essencial | Profissional | Escritório |
|---|---|---|---|
| Receita | R$ 997 | R$ 1.997 | R$ 4.997 |
| Claude Sonnet (com caching, 750K tokens) | R$ 22 | R$ 58 | R$ 145 |
| Claude Opus — Hub | — | R$ 77 | R$ 255 |
| Infra Railway pro-rata | R$ 25 | R$ 50 | R$ 100 |
| Enriquecimento CNPJ | — | R$ 25 | R$ 60 |
| Whisper (áudio) | R$ 2 | R$ 5 | R$ 12 |
| Stripe 2,5% | R$ 25 | R$ 50 | R$ 125 |
| Impostos ~15% | R$ 150 | R$ 300 | R$ 750 |
| **Lucro líquido/cliente** | **R$ 773** | **R$ 1.432** | **R$ 3.550** |
| **Margem líquida** | **78%** | **72%** | **71%** |

> No plano anual (–20%) a margem líquida cai ~2 p.p. — compensada pelo caixa antecipado de 12 meses e pelo churn estruturalmente menor do contrato anual.

#### Plano de 12 meses (jul/2026 → jul/2027) — com lucro líquido por sócio

**Premissas:** 3 sócios como equipe (sem folha fixa até o T3; lucro = distribuição integral); lucro líquido por cliente conforme tabela de margens acima; 10 primeiros clientes como design partners com **30% de desconto até dez/2026** (nunca de graça — grátis não valida nada); verba de aquisição de ~8% do MRR a partir do T2; 1 pessoa de CS/suporte (~R$ 5k/mês) a partir de ~50 clientes; churn já embutido nas metas (números líquidos). E = Essencial, P = Profissional, Esc = Escritório.

| Trimestre | Foco do trimestre | Clientes (mix) | MRR | Lucro líquido/mês | **Por sócio/mês** |
|---|---|---|---|---|---|
| **T1** — set/2026 | **Provar valor real:** 10 design partners pagantes; iniciar migração p/ WhatsApp Cloud API oficial (risco existencial do Evolution); staging + migrations validadas; métrica "horas economizadas" no dashboard do cliente | 10 (7E + 3P) | ~R$ 9k | ~R$ 5,5k | **~R$ 1,8k** |
| **T2** — dez/2026 | **Destravar a captação:** implementar `EscavadorClient` e reativar a F3; 2–3 cases escritos com números reais; onboarding 100% self-service (cadastro → 1ª conversa < 30 min) | 28 (16E + 10P + 2Esc) | ~R$ 43k | ~R$ 29k | **~R$ 9,7k** |
| **T3** — mar/2027 | **Motor de distribuição:** referral incentivado (advogado indica advogado), parcerias OAB/ESA e contadores; contratar 1 CS; iniciar ML de prazos (F4) com a base acumulada | 55 (30E + 20P + 5Esc) | ~R$ 92k | ~R$ 55k | **~R$ 18k** |
| **T4** — jun/2027 | **Decisão de trajetória:** bootstrapped lucrativo × seed para acelerar antes dos incumbentes (Aurum/Projuris) colarem IA nos produtos deles; avaliar integração Astrea/Projuris (F6) como camada de atendimento | 90 (48E + 32P + 10Esc) | ~R$ 155k | ~R$ 95k | **~R$ 32k** |

**Run-rate ao fim do ano 1:** ARR ~**R$ 1,9M** · lucro anualizado ~**R$ 1,1M** (~R$ 380k/sócio/ano) · churn-alvo < 2,5%/mês · ≥ 40% dos novos clientes por indicação · CAC recuperado em < 4 meses.

> Break-even operacional continua no **cliente 1** (sem folha fixa até o T3). A janela competitiva estimada é de 12–24 meses antes dos incumbentes de gestão lançarem atendimento com IA — o ano 1 se decide em **distribuição e no risco Evolution API**, não em código.

**Sinais de alerta (agir imediatamente):**

| Sinal | Reação |
|---|---|
| Churn > 5%/mês sustentado | Parar de vender e corrigir produto — o valor prometido não está sendo entregue |
| Ban de número WhatsApp em cliente pagante | Acelerar migração para a Cloud API oficial a qualquer custo |
| Escavador não destravar a F3 | Reposicionar o pitch inteiro em retenção/atendimento e revisar o preço do Profissional |

---

## Status do Projeto — Julho/2026

```
MVP (Feature 1 + Infra + Sub-features):  ████████████████████  100%  ← em produção
Hub do Advogado (Claude Opus):            ███████████████████░   95%  ← funcional
Agendamento Inteligente:                  ████████████████████  100%  ← em produção (07/2026)
Billing — Stripe + trial:                 ████████████████████  100%  ← em produção
Feature 3 — Prospecção Inteligente:       ██████████████████░░   90%  ← PAUSADA (descoberta aguarda Escavador)
Refactor Orchestrator (nós LangGraph):    ████████████████████  100%  ← concluído
Features 2, 4–6 (backlog):               ░░░░░░░░░░░░░░░░░░░░    0%  ← não iniciadas
```

### Tabela de Features

| # | Feature | Status | Observações |
|---|---------|--------|-------------|
| **F1** | IA Personalizada (MVP) | **✅ 100%** | Em produção (Railway) |
| F1.1 | RAG — documentos do escritório | **✅ 100%** | pgvector + HNSW, dim 1024 |
| F1.2 | Score de Risco Processual | **✅ 100%** | 5 componentes, exclusivo para advogados |
| F1.3 | Resumo Inteligente com contexto | **✅ 100%** | Tracking de fase processual |
| F1.4 | Onboarding Wizard | **✅ 100%** | 6 etapas guiadas |
| F1.5 | Analytics & Dashboard | **✅ 100%** | NPS, custo/interação, exportação |
| F1.6 | Escalação para Advogado | **✅ ~95%** | Funcional; ver Problemas Conhecidos |
| F1.7 | CRM Inteligente | **✅ 100%** | Score + análise narrativa via Claude |
| F1.8 | Agendamento de mensagens | **✅ 100%** | Dispatcher Celery Beat a cada 5 min |
| F1.9 | Orquestrador refatorado em nós | **✅ 100%** | intent/data/generation/verification/delivery |
| F1.10 | Agendamento Inteligente de reuniões | **✅ 100%** | IA propõe horários no WhatsApp; SSE + Google Calendar |
| F1.11 | Billing — Stripe | **✅ 100%** | Checkout, portal, webhook, trial 7 dias com quotas reduzidas |
| F1.12 | Documentos do cliente | **✅ 100%** | Contratos, procurações e comprovantes por cliente (até 10 MB) |
| **Hub** | Hub do Advogado (Claude Opus) | **✅ ~95%** | Análise de petições + consultas com Claude Opus |
| **F2** | Controladoria (Projuris) | **❌ 0%** | Aguarda contrato Projuris |
| **F3** | Prospecção Inteligente | **⏸️ ~90% — pausada** | Motor completo; descoberta bloqueada (ver nota abaixo) |
| F3.1 | DNA do Advogado | **✅ 100%** | Claude Haiku + cache Redis 6h |
| F3.2 | DataJud — busca de litigantes | **⚠️ bloqueada** | DataJud público não retorna o campo `partes`; substituir por API Escavador |
| F3.3 | Receita Federal / CNPJ | **✅ 100%** | Enriquecimento B2B (porte, sócios, situação) |
| F3.4 | LinkedIn / Vibe Prospecting (B2B) | **⚠️ ~70%** | Estrutura + Explorium MCP prontos; Partner Program pendente |
| F3.5 | Matching & Score IA (B2B/B2C) | **✅ 100%** | Heurística + refinamento Claude; limiar 30 |
| F3.6 | Pipeline de leads | **✅ 100%** | CRUD + deduplicação por CNPJ/CNJ |
| F3.7 | Compliance LGPD/OAB (B2C) | **✅ 100%** | Sem CPF/telefone/email; aviso automático |
| **F4** | ML de Prazos | **❌ 0%** | Aguarda volume de dados históricos |
| **F5** | App Mobile (B2C) | **❌ 0%** | Não iniciada |
| **F6** | Integração nativa com CRMs | **❌ 0%** | Não iniciada |
| **Infra** | Docker, CI/CD, Monitoring | **✅ 100%** | GitHub Actions + Railway (PgBouncer-compatible) |

> **Nota sobre a F3 (Prospecção):** o motor completo está implementado e testado (DNA, matching, pipeline, compliance LGPD), mas a **descoberta de litigantes está bloqueada** — o DataJud público não retorna o campo `partes`, então a busca retorna 0 leads. A retomada planejada é substituir o `DataJudProspeccaoClient` pela **API Escavador**, mantendo a interface `buscar_litigantes(tipo_acao, tribunal)`.

---

## Funcionalidades Implementadas

### IA Conversacional via WhatsApp

O coração do produto. Um orquestrador LangGraph executa um pipeline de nós para cada mensagem recebida, com arquitetura totalmente decomposta em módulos independentes:

```
classificar_intencao → buscar_dados → gerar_resposta → avaliar_confianca
    → verificar_resposta (fact-check) → enviar_resposta
```

Intenções que requerem escalação obrigatória (`parecer_juridico`, `estrategia_processual`, `negociacao`, `decisao_judicial_impacto_alto`) são desviadas diretamente para Claude Opus via `EscalacaoClient`.

**Intenções detectadas:** `status`, `perspectivas`, `duvida_termo`, `duvida_geral`, `saudacao`, `reclamacao`, `desabafo`, `agendar_reuniao`, `parecer_juridico`, `estrategia_processual`, `negociacao`, `decisao_judicial_impacto_alto`, `outro`

A intenção `agendar_reuniao` tem threshold de confiança próprio — quando detectada com segurança, desvia o fluxo para o Agendamento Inteligente (a IA propõe horários reais em vez de responder genericamente); abaixo do threshold, a mensagem segue o fluxo normal.

**Confidence Router:** cada resposta é avaliada por um score ponderado (intenção 25% + RAG match 35% + tamanho da resposta 20% + contexto de processo 20%). Respostas abaixo do threshold configurado por escritório (padrão: 0.70) são automaticamente roteadas para Claude Opus.

**Anti-alucinação:** o fact-checker valida cada resposta do Claude contra os dados reais do banco antes de enviar ao cliente — se houver divergência, a resposta é corrigida ou descartada.

**Memória de conversa** por cliente armazenada no Redis — a IA lembra o contexto da sessão.

**Personas configuráveis** — cada escritório define nome, tom e especialidades da IA.

**Escrita humanizada** — as mensagens ao cliente não usam emojis nem travessão; o texto soa como uma pessoa da equipe escrevendo, não como um bot.

**Títulos de conversa automáticos** — a primeira mensagem de cada conversa gera um título curto via Claude Haiku (fire-and-forget, ~60× mais barato que Opus), facilitando a navegação do histórico no Hub.

**Tradutor jurídico** — termos técnicos são automaticamente convertidos para linguagem acessível.

**Canais suportados:**
- Texto (WhatsApp via Evolution API)
- Áudio — transcrição via OpenAI Whisper antes do processamento
- Imagens e documentos — recebidos e catalogados

**Robustez do canal WhatsApp:**
- Mensagens são marcadas como lidas e grupos são ignorados automaticamente (`marcarComoLida` / `ignoreGroups` na Evolution)
- Aceita variações do 9º dígito e números com 8 dígitos; extrai o telefone correto quando o `remoteJid` vem como LID
- Webhook validado por HMAC e configurado automaticamente na criação da instância durante o onboarding

**Controle de envio:**
- Respeita janela comercial configurada por cliente (ex: só enviar entre 8h e 18h)
- Rate limit de 5 mensagens proativas por dia por cliente
- Mensagens bloqueadas são salvas na tabela `mensagens_agendadas` e despachadas automaticamente pelo `dispatcher_agendadas` a cada 5 minutos via Celery Beat

**Quota de tokens:** cada plano tem limite mensal de tokens Claude (ver tabela de planos; em trial, ~20% do plano). Ao atingir a quota, o fluxo retorna mensagem de limite e não chama a API.

---

### Monitoramento de Processos

- Consulta Jusbrasil (primário) + DataJud CNJ (backup gratuito) a cada 6 horas por processo ativo
- Cache Redis 1h para evitar requisições duplicadas
- Tracking completo de fase processual: `conhecimento → instrução → saneamento → julgamento → recurso → execução → encerrado`
- Ao detectar movimentação, dispara notificação proativa para o cliente em linguagem simples

---

### RAG — Base de Conhecimento do Escritório

- Upload de PDFs (petições, jurisprudências, teses, modelos)
- Pipeline: extração PyMuPDF → chunks de 512 tokens (50 overlap) → embeddings 1024-dim (Voyage AI `voyage-law-2`, especializado em jurídico; fallback OpenAI `text-embedding-3-small`) → armazenamento pgvector
- Busca semântica com MMR re-ranking para diversidade de resultados
- Warm-up automático no startup: os 6 embeddings de queries mais comuns são pré-aquecidos no Redis (TTL 24h) para reduzir latência na primeira requisição
- O conteúdo relevante é injetado automaticamente no system prompt de cada resposta
- Isolado por `escritorio_id` — um escritório nunca acessa os documentos de outro

---

### Score de Risco Processual

Pontuação 0–100 por processo, calculada com 5 componentes:

| Componente | Peso |
|-----------|------|
| Idade do processo | 20% |
| Perfil histórico do juiz | 25% |
| Tipo de ação | 20% |
| Prazos pendentes | 20% |
| Histórico do escritório no tribunal | 15% |

- **Nunca exibido para clientes** — compliance OAB Provimento 205/2021
- Atualizado automaticamente a cada 6 horas pelo worker de monitoramento

---

### CRM Inteligente

- Score de relacionamento por cliente (0–100) calculado com: frequência de interação, NPS, número de escalações, dias desde último contato
- Classificação automática: `excelente / satisfeito / neutro / em_risco / critico`
- Análise narrativa gerada pelo Claude com diagnóstico de satisfação e ação sugerida
- Debounce: máximo 1 análise por hora por cliente para não gerar custo desnecessário
- Alerta quando cliente está em risco de churn

---

### Analytics & Dashboard

- NPS com tendências de 7, 30 e 90 dias + gráfico semanal
- Taxa de resposta autônoma (percentual de conversas sem escalação)
- Custo por interação (calculado por tokens consumidos)
- Exportação CSV/Excel por mês para relatórios internos

---

### Escalação para Advogado

- Detecta automaticamente requisições fora de escopo: pedidos de parecer, análise de estratégia, situações emocionalmente sensíveis
- Dois caminhos de escalação: automática pelo Confidence Router ou forçada por intenção classificada
- Notifica o advogado responsável pelo processo via WhatsApp
- Registra timestamp de abertura, resposta e resolução
- Configurável por escritório: canal dedicado ou número compartilhado

---

### Agendamento Inteligente de Reuniões

A IA marca reuniões pelo WhatsApp de ponta a ponta — sem secretária, sem troca de 10 mensagens para achar um horário.

**Fluxo completo:**

```
Cliente: "preciso conversar com o doutor sobre meu processo"
   │
   ▼  IA detecta intenção agendar_reuniao
IA propõe 3 horários livres  ──► cliente escolhe (responde "1", "2" ou "3")
   │
   ▼  status: aguardando_advogado
Advogado aprova pelo Hub (card em tempo real) OU respondendo no WhatsApp
   │
   ▼  status: confirmado
Evento criado no Google Calendar + confirmação ao cliente
Lembrete 24h antes (cliente e advogado) + confirmação 3h antes (cliente)
```

**Máquina de estados:** `aguardando_cliente → aguardando_advogado → confirmado | cancelado | expirado` — propostas sem resposta expiram automaticamente em 48h.

**Busca de horários (AgendamentoDetector):**
- Disponibilidade configurável por dia da semana (seg–sáb, janelas de horário por escritório, na ConfigPage)
- Varre até 30 dias à frente, evitando conflito com reuniões já confirmadas ou aguardando aprovação
- **Evita dias de prazo processual** (e vésperas) — conflito de prazo avisa o advogado, mas nunca bloqueia a proposta
- **Respeita o Google Calendar** — horários ocupados fora do sistema (audiência marcada pela secretária, almoço) são filtrados via freeBusy

**Consciência de prazos processuais:**
- Prazos extraídos automaticamente dos andamentos do processo: datas explícitas ("contestação até 15/08") e **prazos relativos** ("prazo de 15 dias" = dias úteis, CPC art. 219)
- Calendário forense embutido: fins de semana, feriados nacionais (fixos + móveis via Páscoa) e recesso forense (CPC art. 220: 20/12–20/01)
- Linha vermelha de prazos da semana na aba Agenda do Hub
- Worker cruza reuniões confirmadas com novos prazos detectados e alerta o advogado

**Google Calendar (integração bidirecional):**
- OAuth2 por escritório; refresh token criptografado com Fernet no banco
- Reunião confirmada → evento criado; cancelamento/remarcação → evento removido
- Tudo best-effort: Google fora do ar nunca bloqueia uma confirmação
- REST puro com httpx — zero dependências novas

**Tempo real e robustez:**
- `GET /agendamentos/stream` — SSE via Redis pub/sub: o card de aprovação aparece/some no Hub em milissegundos (polling continua como fallback)
- "Primeiro canal ganha": lock Redis impede dupla confirmação simultânea Hub + WhatsApp
- Idempotência total: flags por mensagem enviada + dedup Redis nos lembretes — retries nunca duplicam mensagem ao cliente
- Persistência antes de notificação (at-least-once); regex barata antes de chamar Claude na interpretação de respostas
- Reproposta automática quando o slot escolhido já passou ou foi ocupado

**Workers dedicados:** `expirar_propostas` (horário), `enviar_lembretes` (diário 8h), `enviar_confirmacao_pre_reuniao` (horário, janela de 3h antes), `verificar_conflitos_prazos` (7h30 + hook pós-andamento).

---

### Billing — Assinaturas via Stripe

Monetização self-service completa, sem intervenção manual:

- `POST /billing/checkout` — cria Checkout Session do Stripe para o plano escolhido
- `GET /billing/portal` — Billing Portal para o escritório trocar cartão, plano ou cancelar
- `POST /billing/webhook` — eventos do Stripe (assinatura criada, paga, inadimplente, cancelada) autenticados por HMAC; atualiza plano, quotas e limites do escritório automaticamente
- `GET /billing/status` — status da assinatura exibido no Hub (PlanoPage/PlanosPage)
- **Trial de 7 dias** com quotas reduzidas (~20% do plano) aplicadas automaticamente; conversão restaura os limites cheios
- Status rastreados: `trialing | active | past_due | canceled | unpaid | incomplete`
- Sem `STRIPE_SECRET_KEY`, o módulo opera em modo degradado sem quebrar o restante do sistema

---

### Documentos do Cliente

Além da base RAG (conhecimento do escritório), cada cliente tem seu próprio dossiê de arquivos:

- Contratos, procurações, identidade, petições, comprovantes e outros — até 10 MB por arquivo
- Vinculáveis a um processo específico
- Upload, listagem, download e remoção via API (`/clientes/{id}/documentos`)
- Não são vetorizados — são o arquivo morto organizado do cliente, isolado por escritório

---

### Onboarding Wizard

6 etapas guiadas para novos escritórios ficarem operacionais em menos de 30 minutos:

1. Dados do escritório (nome, OAB, especialidades)
2. Conexão WhatsApp via Evolution API
3. Importação de clientes (CSV ou Google Sheets)
4. Configuração de persona (nome da IA, tom, especialidades declaradas)
5. Aceite dos disclaimers OAB
6. Ativação e teste de envio

---

### Hub do Advogado

Interface exclusiva para advogados, sem as restrições do canal de cliente. Powered by Claude Opus (`claude-opus-4-8`).

**Endpoints:**
- `POST /hub/analisar-peticao` — upload de PDF (até 10 MB) + análise estruturada: pontos fortes, fracos, riscos processuais, sugestões de melhoria
- `POST /hub/consulta` — consulta jurídica livre em linguagem natural
- `GET /hub/sessoes` — histórico de sessões com tokens e custo estimado
- `GET /hub/metricas` — métricas agregadas de uso do Hub por escritório

**Classificação de intenção automática:**

| Intenção | O que faz |
|----------|-----------|
| `análise_petição` | Analisa documento jurídico linha a linha |
| `pesquisa_jurisprudência` | Busca jurisprudência relevante para o caso |
| `resumo_processo` | Gera resumo executivo do processo referenciado |
| `insight_cliente` | Análise do histórico de relacionamento com o cliente |
| `pergunta_jurídica` | Responde perguntas doutrinárias e procedimentais |

**Rastreabilidade:** cada sessão é salva em `sessoes_advogado` com modelo utilizado, tokens consumidos e custo estimado. Escalação pode ser desabilitada por escritório via `escalacao_habilitada` e tem quota própria de tokens (`escalacao_quota_tokens_mes`).

---

### Prospecção Inteligente (Feature 3) — ⏸️ pausada

Motor de captação de leads com demanda jurídica comprovada. **Status:** o motor completo (DNA, matching, pipeline, compliance) está implementado e testado, mas a descoberta está bloqueada — o DataJud público não retorna o campo `partes`, então a busca de litigantes retorna 0 leads. Retomada planejada com a **API Escavador** no lugar do `DataJudProspeccaoClient` (mesma interface pública).

**DNA do Advogado**
Analisa o histórico de processos do escritório e extrai: especialidades predominantes, setores-alvo, tipo de lead ideal (B2B ou B2C). Persistido em `escritorio.dna_prospeccao` (JSONB) + cache Redis 6h. Se o escritório tiver menos de 5 processos, retorna `dados_insuficientes=True` sem forçar classificação.

**Descoberta via DataJud**
Em vez de buscar um CNPJ específico, o sistema busca no DataJud CNJ por `tipo_acao` — retornando quem já está litigando nessa área. Prioriza partes sem advogado (`sem_advogado=True`). Resolve índice automaticamente por área: trabalhista → TRT, cível → TJ, federal → TRF.

**Enriquecimento B2B**
- Receita Federal via ReceitaWS: razão social, situação cadastral, porte, sócios (sem CPF — LGPD)
- LinkedIn: contatos com cargo e URL de perfil (estrutura pronta, Partner Program pendente)
- Vibe Prospecting via Explorium AgentSource (protocolo MCP): fallback para LinkedIn sem Partner Program. Busca decisores por CNPJ com cargos-alvo filtrados. Cache Redis 7 dias.
- Cache Redis 24h por CNPJ

**Enriquecimento B2C — LGPD by Design**
Apenas dados do processo público: nome, polo, tipo de ação, fase, tribunal. CPF, telefone, email e endereço são proibidos no nível do modelo — não existem os campos. `validar_compliance()` descarta automaticamente ações com dados sensíveis (internação compulsória, curatela, retificação de registro civil).

**Matching & Score IA**

| Critério B2B | Peso | Critério B2C | Peso |
|-------------|------|-------------|------|
| Especialidade match | +30 | Especialidade match | +35 |
| Setor CNAE | +20 | Polo compatível | +25 |
| Demanda ativa 3+ processos | +15 | Fase processual inicial | +20 |
| Contatos LinkedIn/Explorium | +15 | Alta recorrência no escritório | +20 |
| Porte MÉDIA/GRANDE | +10 | — | — |
| Situação ATIVA | +10 | — | — |

Score ≥ 30 → Claude refina, gera motivo e sugere abordagem. Score < 30 → retorna sem chamar o modelo.

**Pipeline de Leads**
CRUD completo com deduplicação automática (mesmo CNPJ ou mesmo CNJ → atualiza em vez de duplicar), filtros por tipo/status/score mínimo e paginação. `aviso_lgpd` injetado automaticamente quando o pipeline contém leads B2C.

---

### Painéis Web

**Admin Panel** (`/admin`) — React 19 + TypeScript + TailwindCSS v4 + TanStack Query v5 + React Router v7

| Página | Descrição |
|--------|-----------|
| `HubPage` | Lista de clientes com score CRM, nível e iniciais |
| `ClientDetailPage` | Detalhe completo do cliente: processos, score, histórico |
| `ProcessosPage` | CRUD de processos com badge de risco e vinculação a cliente |
| `CRMPage` | Score CRM detalhado com análise narrativa |
| `AnalyticsPage` | Dashboard com gráfico semanal, NPS, taxa de autonomia e exportação CSV |
| `OperationsPage` | Saúde do sistema + DNA + motor de prospecção + pipeline de leads |
| `RAGPage` | Upload e gerenciamento de documentos da base vetorial |
| `SettingsPage` | Configurações do escritório e persona da IA |
| `LoginPage` | Autenticação JWT |

**Hub React** (`/frontend/hub-react`) — React 19 + TypeScript + TailwindCSS v4 + Framer Motion v12

Interface rica para advogados, com animações (`PageTransition`, `DitherShader`), `FloatingDock` e componentes de UI avançados (`EncryptedText`, `PlaceholdersAndVanishInput`).

| Página | Descrição |
|--------|-----------|
| `LoginPage` | Autenticação JWT |
| `WelcomePage` | Tela de boas-vindas pós-login |
| `OnboardingPage` | Wizard de configuração inicial do escritório |
| `HubPage` | Dashboard principal do advogado |
| `HubIAPage` | Chat com o Hub do Advogado (tabs: Chat, Processos, Documentos, Score) |
| `CRMPage` | Visão CRM por cliente |
| `CaptacaoPage` | Motor de prospecção e pipeline de leads |
| `PainelPage` | Dashboard executivo + **Agenda**: agenda semanal, cards de aprovação de reunião em tempo real (SSE), próximas reuniões e linha de prazos |
| `DocumentosPage` | Base RAG — upload e busca |
| `CadastroCSVPage` | Importação de clientes via CSV |
| `WhatsappPage` | Conexão da instância WhatsApp (QR code Evolution) |
| `PlanosPage` | Escolha de plano + checkout Stripe (trial 7 dias) |
| `PlanoPage` | Assinatura atual, status e acesso ao Billing Portal |
| `AjudaPage` | Central de ajuda e contato |
| `ConfigPage` | Configurações do escritório, troca de senha, disponibilidade de agenda e conexão Google Calendar |
| `LoadingPage` | Tela de carregamento/transição |

**Frontends vanilla** (`/frontend/`) — HTML + CSS (amicus-design) + JavaScript puro para fluxos leves

| Pasta | Descrição |
|-------|-----------|
| `login/` | Página de login standalone (amicus-design) |
| `cadastro-onboarding/` | Wizard de cadastro e onboarding (HTML/JS/CSS) |
| `ajuda-contato/` | Central de ajuda e formulário de contato |

---

## Arquitetura

```
┌──────────────────────────────────────────────────────────┐
│                    WhatsApp (cliente)                    │
└───────────────────────────┬──────────────────────────────┘
                            │ webhook HMAC
                     Evolution API
                            │
┌───────────────────────────▼──────────────────────────────┐
│           FastAPI (feature_1_ia_personalizada)            │
│  ┌──────────────────────────────────────────────────┐    │
│  │     LangGraph Orchestrator — nós desacoplados    │    │
│  │  intent → data → generation → confidence_router  │    │
│  │        → verification (fact-check) → delivery    │    │
│  └───────────┬────────────────┬─────────────────────┘    │
│              │                │                           │
│        Claude API        Jusbrasil / DataJud              │
│   Sonnet (padrão)        (Redis cache 1h)                 │
│   Opus (escalação)                                        │
│        Haiku (DNA)            │                           │
│              │          pgvector RAG                      │
│              │          PostgreSQL (asyncpg)               │
│                                                           │
│  ┌──────────────────────────────────────────────────┐    │
│  │  Hub do Advogado (Claude Opus)                   │    │
│  │  /hub/* → Claude Opus → SessaoAdvogado           │    │
│  │  ConfidenceRouter (threshold por escritório)     │    │
│  └──────────────────────────────────────────────────┘    │
│                                                           │
│  ┌──────────────────────────────────────────────────┐    │
│  │  Agendamento Inteligente                         │    │
│  │  Detector → Proposta WhatsApp → Aprovação        │    │
│  │  Hub (SSE) / WhatsApp → Google Calendar sync     │    │
│  └──────────────────────────────────────────────────┘    │
│                                                           │
│  ┌──────────────────────────────────────────────────┐    │
│  │  Billing (Stripe)                                │    │
│  │  checkout / portal / webhook → plano + quotas    │    │
│  └──────────────────────────────────────────────────┘    │
│                                                           │
│  ┌──────────────────────────────────────────────────┐    │
│  │  Motor de Prospecção (F3 — pausada)              │    │
│  │  DNA → descoberta (Escavador, planejada) → Match │    │
│  └──────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────┘
                            │
               Celery Workers (Redis broker)
               ├── monitor_processos       (cron: cada 6h)
               ├── dispatcher_agendadas    (cron: cada 5min)
               ├── mensagens_relacionamento (cron: diário/semanal)
               ├── agendamento_worker      (crons: expirar 1h / lembretes 8h /
               │                            pré-reunião 1h / conflitos 7h30)
               ├── send_notifications      (on-demand)
               ├── crm_worker              (on-demand, debounce 1h)
               ├── hub_advogado            (on-demand)
               ├── ingest_documentos       (on-demand)
               └── dead_letter             (DLQ)
```

**Multi-tenancy:** isolamento por `escritorio_id` em todas as tabelas (row-level, sem schema separado).

---

## Stack Tecnológica

| Camada | Tecnologia |
|--------|-----------|
| API | FastAPI 0.109 + Uvicorn |
| IA / LLM | Claude Opus `claude-opus-4-8` (Hub + escalação) + Claude Sonnet `claude-sonnet-5` (orquestrador) + Claude Haiku 4.5 (DNA/matching/títulos) |
| Orquestração de IA | LangGraph 0.2 + LangChain 0.2 |
| Confidence Router | Score ponderado por intenção, RAG, contexto — sem dependência de LLM |
| Embeddings (RAG) | Voyage AI `voyage-law-2` (1024D, jurídico) — fallback OpenAI `text-embedding-3-small` (dimensions=1024) |
| Transcrição de áudio | OpenAI Whisper |
| Banco de dados | PostgreSQL 13 + asyncpg 0.29 (prepared statements desativados — compatível com PgBouncer/Railway) |
| Billing | Stripe (Checkout + Billing Portal + webhooks HMAC) |
| Agenda | Google Calendar API (OAuth2 por escritório, REST puro via httpx) + SSE (Redis pub/sub) |
| Vetores (RAG) | pgvector 0.3 — dim 1024, índice HNSW |
| Cache | Redis 5 (TTL 1h–7d por contexto) |
| Filas | Celery 5.3 + Redis broker + RedBeat scheduler |
| Monitoramento de processos | Jusbrasil API + DataJud CNJ |
| WhatsApp | Evolution API (self-hosted) |
| Enriquecimento B2B | ReceitaWS (CNPJ) + Explorium AgentSource MCP + LinkedIn API (Partner Program pendente) |
| Google Sheets | google-api-python-client |
| Segurança | JWT (python-jose) + bcrypt + Fernet AES-256 |
| Métricas | Prometheus + Grafana Cloud |
| Logs | structlog (JSON) + Sentry (0.1 traces + 0.1 profiles) |
| CI/CD | GitHub Actions |
| Deploy | Railway |
| Admin Panel | React 19 + TypeScript + TailwindCSS v4 + TanStack Query v5 + React Router v7 |
| Hub Frontend | React 19 + TypeScript + Framer Motion + TailwindCSS v4 |
| Testes | pytest + pytest-asyncio + factory-boy |
| Qualidade | Ruff + Black + mypy + mutmut |

---

## Estrutura de Pastas

```
PROJETO-IA-JURIDICA-5/
│
├── shared/                          # Core compartilhado
│   ├── models/                      # SQLAlchemy ORM (13 models)
│   │   ├── base.py                  ✅ TenantMixin, TimestampMixin
│   │   ├── escritorio.py            ✅ Tenant raiz + quotas + Stripe + Google Calendar
│   │   ├── cliente.py               ✅ Cliente final
│   │   ├── processo.py              ✅ Processo judicial (score, fase)
│   │   ├── usuario.py               ✅ Advogados/assistentes
│   │   ├── interacao.py             ✅ Log de conversas IA-cliente
│   │   ├── documento_rag.py         ✅ Documentos vetorizados
│   │   ├── documento_cliente.py     ✅ Arquivos por cliente (contratos, procurações)
│   │   ├── lead_prospeccao.py       ✅ Pipeline de prospecção (F3)
│   │   ├── sessao_advogado.py       ✅ Sessões do Hub do Advogado
│   │   ├── agendamento.py           ✅ Máquina de estados de reuniões
│   │   ├── disponibilidade_advogado.py ✅ Janelas de atendimento (seg–sáb)
│   │   └── mensagem_agendada.py     ✅ Fila de mensagens fora da janela comercial
│   ├── schemas/                     ✅ Pydantic v2 (request/response)
│   ├── database/                    ✅ AsyncEngine + sessionmaker
│   ├── security/                    ✅ JWT + AES-256
│   ├── utils/                       ✅ LGPD, formatadores, validadores
│   ├── tests/                       ✅ 4 arquivos (encryption, schemas, utils, validators)
│   └── config/                      ✅ Pydantic Settings + constantes
│
├── feature_1_ia_personalizada/
│   ├── api/
│   │   ├── app.py                   ✅ FastAPI app + lifespan + warmup RAG
│   │   ├── routes/
│   │   │   ├── auth.py              ✅ Login + registro JWT
│   │   │   ├── webhook_whatsapp.py  ✅ Receiver Evolution API
│   │   │   ├── processos.py         ✅ CRUD processos
│   │   │   ├── clientes.py          ✅ CRUD clientes + exportação LGPD
│   │   │   ├── chat.py              ✅ Histórico + NPS + analytics
│   │   │   ├── rag.py               ✅ Upload/busca de documentos
│   │   │   ├── crm.py               ✅ Score CRM por cliente
│   │   │   ├── onboarding.py        ✅ Wizard 6 etapas
│   │   │   ├── admin_import.py      ✅ CSV/Google Sheets
│   │   │   ├── escalacoes.py        ✅ CRUD escalações para advogado
│   │   │   ├── escritorios.py       ✅ Configurações de escritório
│   │   │   ├── health.py            ✅ /health, /health/ready
│   │   │   ├── metrics.py           ✅ /metrics (Prometheus)
│   │   │   ├── prospeccao.py        ✅ /prospeccao/* (DNA, pipeline, leads)
│   │   │   ├── agenda.py            ✅ /agenda/* (disponibilidade, slots, eventos)
│   │   │   ├── agendamentos.py      ✅ /agendamentos/* (stream SSE, confirmar/sugerir/cancelar)
│   │   │   ├── google_calendar.py   ✅ /google-calendar/* (OAuth2, status, disconnect)
│   │   │   ├── billing.py           ✅ /billing/* (checkout, portal, webhook, status)
│   │   │   └── hub_advogado.py      ✅ /hub/* (Claude Opus + métricas)
│   │   └── middleware/              ✅ Auth JWT, rate limit, CSRF, logging
│   │
│   ├── services/
│   │   ├── ai/
│   │   │   ├── orchestrator.py      ✅ LangGraph — monta o grafo de nós
│   │   │   ├── state.py             ✅ ConversationState, NodeDeps, QuotaExcedidaError
│   │   │   ├── nodes/
│   │   │   │   ├── intent.py        ✅ classificar_intencao, avaliar_escalacao
│   │   │   │   ├── data.py          ✅ buscar_dados (Jusbrasil + DataJud + RAG)
│   │   │   │   ├── generation.py    ✅ gerar_resposta + gerar_resposta_escalacao
│   │   │   │   ├── verification.py  ✅ verificar_resposta (fact-check)
│   │   │   │   ├── delivery.py      ✅ enviar_resposta + tratar_erro
│   │   │   │   └── _helpers.py      ✅ obter_escritorio_cliente, salvar_interacao
│   │   │   ├── claude_client.py     ✅ Wrapper Claude com retries + quota
│   │   │   ├── confidence_router.py ✅ Score ponderado (0.0–1.0) por intenção/RAG/contexto
│   │   │   ├── escalation_client.py ✅ Claude Opus (Hub + escalação premium)
│   │   │   ├── hub_advogado_classifier.py ✅ Classificação de intenção para o Hub
│   │   │   ├── fact_checker.py      ✅ Anti-alucinação
│   │   │   ├── memory.py            ✅ Memória Redis por cliente
│   │   │   ├── juridical_translator.py ✅ Tradução jurídico→leigo
│   │   │   ├── processo_state.py    ✅ Tracking de fase processual
│   │   │   ├── translator.py        ✅ Tradutor estruturado
│   │   │   └── prompts.py           ✅ System prompts tipados
│   │   ├── messaging/               ✅ Evolution API + templates + fila de mensagens
│   │   ├── agendamento/             ✅ detector (slots) + prazos (calendário forense)
│   │   │                               + notifier (WhatsApp) + eventos (SSE) + google_calendar
│   │   ├── billing/                 ✅ stripe_service (planos, quotas, trial)
│   │   ├── legal_data/              ✅ Jusbrasil + DataJud + cache
│   │   ├── rag/                     ✅ Ingestão + embeddings + retriever
│   │   ├── analytics/               ✅ NPS + métricas + exportação
│   │   ├── crm/                     ✅ Score + análise Claude
│   │   ├── escalacao/               ✅ Escalação para advogados
│   │   ├── integrations/            ✅ Google Sheets
│   │   └── prospeccao/
│   │       ├── dna_advogado.py      ✅ DNA do escritório
│   │       ├── datajud_prospeccao.py ✅ Busca litigantes por tipo de ação
│   │       ├── empresa_intelligence.py ✅ Enriquecimento B2B
│   │       ├── pessoa_intelligence.py  ✅ Enriquecimento B2C (LGPD)
│   │       ├── matching.py          ✅ Heurística + refinamento Claude
│   │       ├── receita_federal_client.py ✅ CNPJ e sócios
│   │       ├── vibe_prospecting_client.py ✅ Explorium MCP (fallback LinkedIn)
│   │       └── linkedin_client.py   ⚠️ Estrutura pronta; Partner Program pendente
│   │
│   ├── workers/
│   │   ├── celery_app.py            ✅ Filas + RedBeat scheduler
│   │   ├── monitor_processos.py     ✅ Polling Jusbrasil (cada 6h)
│   │   ├── send_notifications.py    ✅ Notificações on-demand
│   │   ├── agendamento_worker.py    ✅ Expiração, lembretes, pré-reunião, conflitos de prazo
│   │   ├── dispatcher_agendadas.py  ✅ Despacha mensagens agendadas (cada 5min)
│   │   ├── crm_worker.py            ✅ Análise CRM (debounce 1h)
│   │   ├── hub_advogado.py          ✅ Tasks Celery do Hub (interface)
│   │   ├── hub_worker.py            ✅ Processamento assíncrono do Hub (implementação)
│   │   ├── ingest_documentos.py     ✅ Pipeline RAG
│   │   ├── mensagens_relacionamento.py ✅ Aniversários, datas comemorativas
│   │   └── dead_letter.py           ✅ Dead Letter Queue
│   │
│   └── tests/
│       ├── unit/                    ✅ 43 arquivos
│       └── integration/             ✅ 17 arquivos
│
├── admin/                           ✅ Admin Panel (React 19 + Vite + TailwindCSS v4)
│   └── src/pages/                   ✅ Hub, CRM, Analytics, Operations, Processos, RAG, Settings, Login
│
├── frontend/
│   ├── hub-react/                   ✅ Hub do Advogado (React 19 + Framer Motion)
│   │   └── src/pages/               ✅ HubIA, Hub, CRM, Captação, Painel (+ Agenda), Documentos,
│   │                                    Config, Planos, Plano, Whatsapp, Login, Onboarding,
│   │                                    Welcome, CadastroCSV, Ajuda, Loading
│   ├── login/                       ✅ Login page (HTML/CSS/JS — amicus-design)
│   ├── cadastro-onboarding/         ✅ Onboarding wizard vanilla (HTML/CSS/JS)
│   └── ajuda-contato/               ✅ Central de ajuda e contato (HTML/CSS/JS)
│
├── tests/
│   ├── unit/                        ✅ test_hub_advogado.py
│   └── load/                        ✅ Locust — testes de carga (config + locustfile)
│
├── alembic/versions/                ✅ 31 migrations
├── infrastructure/docker/           ✅ Dockerfile + docker-compose (dev + prod)
├── monitoring/                      ✅ Prometheus + Grafana + Loki + Promtail
├── docs/                            ✅ Roadmap, guias de dev e produção
├── scripts/setup/                   ✅ init_db.py, seed_data.py, create_admin.py
├── scripts/monitoring/              ✅ health_check.py
├── Makefile                         ✅ 40+ targets
└── pyproject.toml                   ✅ Ruff + Black + mypy + pytest + mutmut
```

---

## Setup Local

**Pré-requisitos:** Python 3.12+, Docker + Docker Compose, ffmpeg

```bash
# 1. Clonar e configurar ambiente
git clone <repo>
cd PROJETO-IA-JURIDICA-5
make setup              # cria .venv, instala deps, copia .env.example → .env

# 2. Editar .env com as chaves necessárias (ver seção abaixo)

# 3. Subir infraestrutura
docker compose -f infrastructure/docker/docker-compose.yml up -d

# 4. Banco de dados
make migrate            # alembic upgrade head
make seed               # dados de desenvolvimento
make create-admin       # criar primeiro usuário admin

# 5. Rodar
make dev                # FastAPI em :8000
make worker             # Celery worker (outro terminal)
make beat               # Celery Beat — dispatcher + todos os crons
make flower             # Monitor Celery em :5555 (opcional)

# 6. Frontends (opcional)
cd admin && npm install && npm run dev        # Admin panel em :5173
cd frontend/hub-react && npm install && npm run dev  # Hub advogado em :5174

# 7. Qualidade
make test               # pytest (cobertura mínima 70%)
make lint               # Ruff + Black check
make type-check         # mypy
```

---

## Endpoints

| Método | Rota | Descrição | Auth |
|--------|------|-----------|------|
| `POST` | `/webhook/whatsapp` | Receiver Evolution API | API Key |
| `POST` | `/auth/login` | Gera token JWT | Email/senha |
| `POST` | `/auth/register` | Cadastro de escritório | — |
| `POST` | `/auth/refresh` | Renova o token JWT | JWT |
| `POST` | `/auth/change-password` | Altera a senha do usuário autenticado | JWT |
| `GET` | `/processos` | Lista processos do escritório | JWT |
| `GET` | `/processos/{id}` | Detalhes + score de risco | JWT |
| `POST` | `/rag/upload` | Upload de documento PDF | JWT |
| `DELETE` | `/rag/{id}` | Remove documento do RAG | JWT |
| `POST` | `/crm/analise` | Dispara análise CRM de cliente | JWT |
| `GET` | `/crm/cliente/{id}` | Score + diagnóstico CRM | JWT |
| `GET` | `/escalacoes` | Lista escalações do escritório | JWT |
| `PATCH` | `/escalacoes/{id}` | Atualiza status de uma escalação | JWT (advogado) |
| `GET` | `/escritorios/me` | Dados e configurações do escritório | JWT |
| `PATCH` | `/escritorios/me` | Atualiza configurações do escritório | JWT (admin) |
| `POST` | `/onboarding/etapa` | Avança etapa do wizard | JWT |
| `GET` | `/chat/historico` | Histórico de conversas | JWT |
| `GET` | `/health` | Health check (DB, Redis, Claude) | — |
| `GET` | `/metrics` | Métricas Prometheus | — |
| `POST` | `/hub/analisar-peticao` | Analisa petição PDF com Claude Opus | JWT (advogado) |
| `POST` | `/hub/consulta` | Consulta jurídica livre no Hub | JWT (advogado) |
| `GET` | `/hub/sessoes` | Histórico de sessões do advogado | JWT (advogado) |
| `GET` | `/hub/metricas` | Métricas agregadas do Hub por escritório | JWT (advogado) |
| `GET` | `/prospeccao/dna` | DNA atual do escritório | JWT (advogado) |
| `POST` | `/prospeccao/dna/atualizar` | Regenera DNA via Claude | JWT (advogado) |
| `POST` | `/prospeccao/descobrir` | Executa motor de prospecção | JWT (advogado) |
| `GET` | `/prospeccao/pipeline` | Lista leads com filtros e paginação | JWT (advogado) |
| `PATCH` | `/prospeccao/{id}/status` | Atualiza status e notas de um lead | JWT (advogado) |
| `DELETE` | `/prospeccao/{id}` | Remove um lead do pipeline | JWT (advogado) |
| `GET` | `/clientes/{id}/exportar` | Exporta dados pessoais do cliente (LGPD Art. 18, V) | JWT (advogado) |
| `DELETE` | `/clientes/{id}` | Anonimiza dados pessoais do cliente (LGPD Art. 18, IV) | JWT (advogado) |
| `GET/POST` | `/clientes/{id}/documentos` | Lista/envia documentos do cliente (até 10 MB) | JWT |
| `GET` | `/clientes/{id}/documentos/{doc_id}/download` | Download de documento do cliente | JWT |
| `GET/PUT` | `/agenda/disponibilidade` | Janelas de atendimento por dia da semana | JWT (advogado) |
| `GET` | `/agenda/slots` | Próximos horários livres (detector) | JWT |
| `GET` | `/agenda/eventos` | Reuniões + prazos da semana (aba Agenda) | JWT |
| `GET` | `/agendamentos` | Lista agendamentos com filtro por status | JWT |
| `GET` | `/agendamentos/stream` | SSE — atualizações em tempo real | JWT |
| `POST` | `/agendamentos/{id}/confirmar` | Advogado confirma a reunião | JWT (advogado) |
| `POST` | `/agendamentos/{id}/sugerir` | Advogado sugere novos horários | JWT (advogado) |
| `POST` | `/agendamentos/{id}/cancelar` | Cancela a reunião (evento Google removido) | JWT |
| `GET` | `/google-calendar/auth-url` | Inicia OAuth2 com o Google Calendar | JWT |
| `GET` | `/google-calendar/status` | Status da conexão com o Google | JWT |
| `POST` | `/google-calendar/disconnect` | Remove a conexão com o Google | JWT |
| `POST` | `/billing/checkout` | Cria Checkout Session no Stripe | JWT (admin) |
| `GET` | `/billing/portal` | URL do Billing Portal do Stripe | JWT (admin) |
| `GET` | `/billing/status` | Status da assinatura do escritório | JWT |
| `POST` | `/billing/webhook` | Eventos do Stripe (HMAC `stripe-signature`) | HMAC |

---

## Compliance

### OAB (Provimento 205/2021)
- IA nunca emite pareceres jurídicos nem prevê resultado de processos
- Disclaimer obrigatório na primeira interação de cada cliente
- Score de risco visível apenas para advogados
- Escalação automática para humano em situações fora de escopo (`parecer_juridico`, `estrategia_processual`, `negociacao`, `decisao_judicial_impacto_alto`)
- Prospecção B2C restrita a canais processuais — sem cold call com dados de litígio

### LGPD (Lei 13.709/2018)
- Criptografia AES-256 em repouso para CPF e dados sensíveis
- TLS 1.3 em trânsito
- Logs de acesso rastreáveis por usuário e timestamp
- Mascaramento: CPF → `***.***.***-XX`, telefone → `(**)****-XXXX`
- Isolamento de dados por `escritorio_id` (row-level multi-tenancy)
- Retenção: dados de processos arquivados removidos após 5 anos
- Lead B2C: campos `cpf`, `telefone`, `email` **não existem no modelo** — proibido por design
- Endpoints de portabilidade e anonimização: `GET /clientes/{id}/exportar` (Art. 18, V) e `DELETE /clientes/{id}` (Art. 18, IV)
- Sentry com `send_default_pii=False` — nenhum dado pessoal enviado ao rastreador de erros

---

## Moats Estratégicos — Vantagens Competitivas Defensáveis

A defensibilidade do Concierge não está no código — está nos dados, na rede e no switching cost acumulado. Cada escritório que entra alimenta múltiplos moats simultaneamente.

### Moats ativos (já operando)

| Moat | Tipo | Como funciona | Replicabilidade |
|------|------|---------------|-----------------|
| **Base RAG proprietária** | Dados | Petições, teses e jurisprudências do escritório alimentam a IA. Quanto mais documentos, melhor a resposta. Efeito composto irreplicável de fora. | ⬛⬛⬛⬛⬛ Quase impossível |
| **Dados de prospecção acumulados** | Dados | DNA do advogado + histórico de leads + taxa de conversão por perfil. O matching score se calibra com feedback real — concorrente começa com heurística genérica. | ⬛⬛⬛⬛⬜ Muito difícil |

### Moats em construção (próximos 6 meses)

| Moat | Tipo | Como funciona | Replicabilidade |
|------|------|---------------|-----------------|
| **Persona treinada por uso** | Switching cost | Cada correção do advogado refina a IA via few-shot acumulado. Após meses de uso, a persona é insubstituível — trocar de produto significa recomeçar do zero. | ⬛⬛⬛⬛⬛ Quase impossível |
| **Dados de experiência jurídica** | Dados | NPS, tempo de resposta, satisfação por fase processual — dados cross-escritório anonimizados que ninguém mais coleta. | ⬛⬛⬛⬛⬜ Muito difícil |
| **Rede processual própria** | Escala | Cada escritório traz processos monitorados. Com 50 escritórios = milhares de processos com contexto que a Jusbrasil não tem. | ⬛⬛⬛⬛⬜ Muito difícil |
| **Inteligência preditiva por vara/juiz** | Tecnologia | ML de prazos que melhora com cada processo concluído na plataforma. | ⬛⬛⬛⬛⬜ Muito difícil |

### Tese de defensibilidade

```
Fase 1 (agora):      Dados proprietários por escritório (RAG + prospecção)
                      → Lock-in individual: cada escritório acumula inteligência própria

Fase 2 (6 meses):    Dados cross-escritório + persona treinável + rede processual
                      → Lock-in de plataforma: valor cresce com a base instalada

Fase 3 (12+ meses):  Efeito de rede + marca + dados vendáveis
                      → Lock-in de ecossistema: trocar não é perder uma ferramenta,
                        é perder acesso a uma rede e a uma posição de mercado
```

---

## Variáveis de Ambiente

```bash
# IA
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...           # Whisper + fallback de embeddings
VOYAGE_API_KEY=pa-...           # Embeddings RAG (voyage-law-2); sem ela, usa o fallback OpenAI

# Banco
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/juridico
REDIS_URL=redis://localhost:6379

# WhatsApp
EVOLUTION_API_URL=http://localhost:8080
EVOLUTION_API_KEY=...
EVOLUTION_WEBHOOK_SECRET=...    # HMAC validation

# Judicial
JUSBRASIL_API_KEY=...
DATAJUD_API_KEY=...             # Gratuito — CNJ

# Prospecção B2B (opcional)
EXPLORIUM_API_KEY=...           # Vibe Prospecting — fallback LinkedIn

# Billing — Stripe (sem SECRET_KEY o módulo opera em modo degradado)
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_ID_BASICO=price_...        # Essencial — R$ 997/mês (id interno `basico`)
STRIPE_PRICE_ID_PROFISSIONAL=price_...  # R$ 1.997/mês
STRIPE_PRICE_ID_ESCRITORIO=price_...    # R$ 4.997/mês
STRIPE_TRIAL_DAYS=7             # 0 = sem trial

# Google Calendar — Agendamento Inteligente (opcional; sem as 3 envs a integração desliga limpa)
GOOGLE_CALENDAR_CLIENT_ID=...
GOOGLE_CALENDAR_CLIENT_SECRET=...
GOOGLE_CALENDAR_REDIRECT_URI=https://api.meudominio.com/google-calendar/callback

# Google Sheets (opcional)
GOOGLE_SHEETS_CREDENTIALS=...

# Segurança
SECRET_KEY=...                  # JWT signing (mínimo 32 chars)
ENCRYPTION_KEY=...              # Fernet AES-256 (44 chars base64url)

# Observabilidade (opcional em dev)
SENTRY_DSN=...
GRAFANA_CLOUD_API_KEY=...
CORS_ALLOWED_ORIGINS=https://meudominio.com,https://admin.meudominio.com
```

---

## Testes

```bash
make test               # todos os testes
make test-unit          # apenas unitários
make test-integration   # apenas integração
make coverage           # relatório HTML de cobertura
make mutation           # testes de mutação com mutmut

# Testes de carga (requer Locust)
cd tests/load && locust -f locustfile.py   # painel em :8089
```

- **43 arquivos unitários** (`feature_1_ia_personalizada/tests/unit/`) **+ 17 de integração** (`feature_1_ia_personalizada/tests/integration/`)
- Adicionalmente: **4 testes em `shared/tests/`** (encryption, schemas, utils, validators) e testes de load com **Locust** em `tests/load/`
- Cobertura mínima: **70%** (enforçado no CI com falha de build)
- Banco de testes: SQLite in-memory via `aiosqlite` — sem PostgreSQL necessário em dev
- Feature 3: 89 testes dedicados (heurística de matching componente a componente, LGPD, rotas)
- Integração: `test_confidence_router.py`, `test_analise_peticao.py`, `test_hub_resumos_insights.py`, `test_whatsapp_flow.py`, `test_e2e_celery_orchestrator.py`, entre outros

---

## O Que Falta para Production Ready

### Bloqueadores (obrigatório antes de lançar para clientes reais)

| Item | Por que é bloqueador | Estimativa |
|------|---------------------|------------|
| **Validação de produção do banco** | `alembic upgrade head` precisa ser testado em ambiente de staging com dados reais antes do primeiro deploy | Processo, não código |

### Importante (não bloqueia o lançamento, mas afeta qualidade)

| Item | Impacto |
|------|---------|
| **Descoberta de leads (Escavador)** | F3 pausada: DataJud público não retorna `partes`. Criar conta Escavador (tem trial) e implementar `EscavadorClient` mantendo a interface `buscar_litigantes(tipo_acao, tribunal)` |
| **LinkedIn API real** (Partner Program) | Enriquecimento B2B retorna dados via Explorium/mock de contato; o campo de contatos existe, mas dados reais LinkedIn dependem da aprovação |
| **Explorium API Key** | `EXPLORIUM_API_KEY` sem valor desativa o Vibe Prospecting silenciosamente (fallback gracioso já implementado) |
| **Documentação de API** | `docs/api/` vazia — sem Postman collection nem snapshot OpenAPI para integrações externas |

### Roadmap (não bloqueia, mas são features de valor)

| Feature | Desbloqueio |
|---------|-------------|
| **Feature 2 — Controladoria (Projuris)** | Contrato de API com a Projuris |
| **Feature 4 — ML de Prazos** | ~1.000 processos concluídos para treinar o modelo |
| **Feature 5 — App Mobile B2C** | Decisão de produto e time de frontend |
| **Feature 6 — Integração nativa com CRMs** | Parcerias com Projuris / Astrea / SAJ ADV |

---

## Problemas Conhecidos

| # | Problema | Status |
|---|----------|--------|
| 1 | Migration `004` com `down_revision` errado | ✅ **Corrigido** |
| 2 | Dois arquivos com prefixo `008_` | ✅ **Sem conflito** — cadeia sequencial sem branches paralelas |
| 3 | `ScoreRiscoCalculator` acoplada ao módulo `vitoria_preditor.py` | ✅ **Corrigido** — movida para `score_risco.py` |
| 4 | RAG usa `vector(1024)` e HNSW (spec pedia 1536 + IVFFlat) | ℹ️ **Intencional** — HNSW funciona em tabela vazia e mantém recall estável com inserts incrementais |
| 5 | Orchestrator como monolito único | ✅ **Corrigido** — decomposto em `nodes/intent.py`, `data.py`, `generation.py`, `verification.py`, `delivery.py` |
| 6 | asyncpg × PgBouncer no Railway (`prepared statement does not exist`) | ✅ **Corrigido** — prepared statements desativados via `prepared_statement_name_func` + `statement_cache_size=0` |
| 7 | Workers Celery com `asyncio.run` + engine pooled (`Future attached to a different loop`) | ✅ **Corrigido** — `worker_session_factory` global com NullPool para todos os workers |
| 8 | DataJud público sem campo `partes` | ⏸️ **Bloqueia a F3** — descoberta de leads retorna 0; substituir por API Escavador |

---

## Links

- **Base de conhecimento (visão completa do projeto, pronta para RAG):** [docs/base_conhecimento/](docs/base_conhecimento/00_INDICE.md)
- **Tasks e sub-features:** [TASKS.md](TASKS.md)
- **Guia de desenvolvimento:** [docs/guides/development.md](docs/guides/development.md)
- **Checklist de produção:** [docs/guides/production-readiness.md](docs/guides/production-readiness.md)
- **Gestão de secrets:** [docs/guides/secrets.md](docs/guides/secrets.md)
- **Documentação do banco:** [bancodedados_api.md](bancodedados_api.md)
- **Agendamento Inteligente (produto):** [docs/FEATURE_AGENDAMENTO_INTELIGENTE.md](docs/FEATURE_AGENDAMENTO_INTELIGENTE.md)
- **Agendamento Inteligente (técnica):** [docs/FEATURE_AGENDAMENTO_INTELIGENTE_TECNICA.md](docs/FEATURE_AGENDAMENTO_INTELIGENTE_TECNICA.md)
- **Monitoramento:** [GRAFANA-SETUP.md](GRAFANA-SETUP.md)
