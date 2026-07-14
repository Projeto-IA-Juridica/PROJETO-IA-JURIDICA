# Máquina de Vendas — Concierge Jurídico

> Playbook operacional do funil: como achamos o lead, como filtramos, como abordamos, como a Clara trata, quando o lead quente passa para Gabriel ou a sócia, e como fechamos. Versão 1 — 13/07/2026.

---

## O funil em uma tela

```
  DESCOBERTA        40 alvos/semana (4 fontes)
      │ filtragem ICP (score A/B/C)
  FILTRADOS         ~25 aprovados          ── C não é abordado
      │ 3 plays de abordagem (5/dia, personalizado)
  ABORDADOS         ~20
      │ taxa de resposta esperada 25–30%
  RESPONDERAM       ~6
      │ CTA único: conversar com a Clara no número-vitrine
  CONVERSA CLARA    ~4  ← qualificação automática (3 perguntas)
      │ critérios de lead quente
  HANDOFF HUMANO    ~2  → Gabriel ou sócia, SLA 15 min
      │ call de 20 min (Profissional+) ou self-service (Essencial)
  TRIAL 7 DIAS      1–2  ← nurturing D+1 / D+3 / D+6
      │ conversão de trial ~50–60%
  PAGANTE           ~1/semana no início
```

Regra de ouro da máquina: **cada etapa só é automatizada depois que a versão manual provar conversão.** A Clara e o agendamento já são automáticos porque são o produto; o resto começa manual e instrumentado.

---

## Etapa 0 — Infraestrutura (pré-requisito de tudo)

Nada de abordagem antes destas 3 peças estarem no ar:

### 0.1 Número-vitrine (tenant de demo)
- Escritório fictício no sistema, persona **Clara**, chip dedicado + instância Evolution separada da produção.
- **Três trilhas de teste** que o advogado pode viver na conversa:
  1. **Processo real** — o advogado manda um número de processo (dele ou de cliente) e vê a IA buscar a movimentação pública e traduzir para linguagem de cliente. É o "uau" principal.
  2. **Agendamento** — pede reunião e recebe 3 horários; vê confirmação e lembrete funcionando.
  3. **Conhecimento jurídico** — pergunta um termo ou dúvida processual e vê a resposta em linguagem simples, com a escalação disparando quando pede parecer (mostra o compliance OAB na prática).
- **Gancho de vendas no prompt:** após algumas trocas, a Clara se revela — *"tudo que você viveu aqui é o que seus clientes teriam"* — e oferece o trial de 7 dias com link de cadastro.

### 0.2 Landing page simples (`frontend/landing`)
- Headline de dor ("Seu cliente perguntou 'tem novidade?' de novo?"), calculadora da dor, botão **wa.me do vitrine com texto pré-preenchido** e form de contato.
- Cada canal usa um texto pré-preenchido diferente → a origem se identifica sozinha:
  - Landing: `"Olá Clara, vim pelo site"`
  - Currículo: `"Olá Clara, recebi seu currículo"`
  - Calculadora: `"Olá Clara, fiz a conta do meu escritório"`
  - Indicação: `"Olá Clara, o contador me indicou"`

### 0.3 Rastreamento
- Planilha de alvos (fase manual) com colunas: escritório, cidade, área, nº advogados, fonte, score, WhatsApp, processo encontrado, toques 1/2/3, resposta, status.
- Campo `origem` no cadastro de trial. Sem dado, a retrospectiva de sexta não existe.

---

## Etapa 1 — Descoberta: como achamos o lead

Quatro fontes, em ordem de temperatura:

| # | Fonte | Como garimpar | Sinal de dor | Play de abordagem |
|---|-------|--------------|--------------|-------------------|
| 1 | **Vagas de secretária/recepcionista/atendimento em escritórios de 5–15 advogados** | Indeed, Catho, InfoJobs, LinkedIn Jobs, grupos de vagas jurídicas da cidade — busca semanal (30 min) | Máximo — problema declarado + orçamento aprovado | **Currículo da Clara** |
| 2 | **Escritórios que anunciam online** | Biblioteca de anúncios da Meta + buscar "advogado trabalhista/previdenciário [cidade]" no Google e anotar quem paga anúncio | Alto — paga pelo clique e perde o lead fora do horário | **Mensagem-espelho** com ângulo "lead que esfria" |
| 3 | **Indicações quentes** (pai contador + rede) | Mensagem encaminhável pronta no WhatsApp dele; pedir 2–3 apresentações pontuais | Variável — mas confiança emprestada | Apresentação direta → vitrine |
| 4 | **Inbound da landing** (calculadora, QR, conteúdo) | Passivo — cresce com o tempo | Auto-selecionado | Resposta < 5 min → vitrine |

Futuro (Fase 3 da automação): CNPJs novos de CNAE 6911-7 (Receita) alimentando a lista toda semana.

---

## Etapa 2 — Filtragem: quem merece abordagem

Nem todo escritório vale os 15 minutos de personalização. Score antes de abordar:

**Pontuação (ICP):**

| Critério | Pontos |
|---|---|
| 5–15 advogados | +3 |
| 2–4 advogados | +2 |
| Área cível / trabalhista / previdenciário / família | +2 |
| **Vaga aberta** de secretária/atendimento | +3 |
| **Anuncia online** (Google/Meta) | +3 |
| Instagram ativo (posta 1x/semana+) | +1 |
| WhatsApp publicado no site/Instagram | +1 |

**Classificação:**
- **A (≥ 6 pontos)** → abordagem premium: currículo da Clara (se tem vaga) ou mensagem-espelho com processo pesquisado. Até 5/dia.
- **B (3–5 pontos)** → mensagem-espelho padrão. Entra na fila depois dos A.
- **C (< 3 pontos)** → **não abordar.** Fica na lista para inbound/indicação futura.

**Desqualificação automática (nem pontuar):**
- Escritório enterprise com sistema legado (Projuris/SAJ) — fora do escopo atual
- Advogado solo sem carteira ativa (sem processos = sem dor de comunicação)
- Contencioso de massa/volume extremo (bancos, telefonia) — perfil errado de atendimento
- Fora das áreas atendidas pela IA hoje

---

## Etapa 3 — Abordagem: os 3 plays

Regras fixas: **máx. 5–10 abordagens/dia**, envio entre **8h30–10h**, número comercial próprio (nunca a infra Evolution dos clientes), identificação na primeira linha, processo citado sempre público, opt-out eterno.

### Play 1 — Mensagem-espelho (alvos A/B frios)
Pesquisa: 1 processo real do escritório com movimentação recente (consulta pública por OAB / Jusbrasil). Gerar a notificação que o cliente final teria recebido usando a própria IA.

> **Toque 1 (D0):** "Doutor(a) [nome], boa tarde. Meu nome é Gabriel. Na [dia] passada, o processo [nº] do seu escritório teve [movimentação]. Se o senhor usasse nossa plataforma, seu cliente teria recebido isto no WhatsApp, automaticamente, 5 minutos depois: *'[mensagem gerada pela IA em linguagem simples]'*. Quem escreveu foi a IA, sozinha, a partir do andamento real. Ela também responde dúvidas 24h no tom do escritório e marca reuniões na sua agenda. Quer conversar com ela como se você fosse seu próprio cliente? Manda um oi aqui: [wa.me vitrine]"
>
> **Toque 2 (D+3, se silêncio):** "Doutor, sem insistir — só uma conta para escritórios de ~[X] advogados: responder 'tem novidade?' consome ~14h/mês por advogado. A R$ 180/h, são ~R$ 2.500/mês em tempo que a IA devolve por R$ 997. A conta com os números do seu escritório: [calculadora]"
>
> **Toque 3 (D+7, despedida):** "Última mensagem, prometo. A assistente de demonstração fica ativa até sexta: [wa.me vitrine]. Se não fizer sentido agora, guarde o contato — e sucesso com a banca!"

Parou de responder no toque 3 = parou para sempre.

### Play 2 — Currículo da Clara (alvos A com vaga aberta)
- Peça A4 formato currículo: *Nome: Clara · Experiência: nunca deixei um "tem novidade?" sem resposta · Disponibilidade: 24h, sem férias, sem INSS · Pretensão salarial: R$ 997/mês · Entrevista: aponte a câmera →* [QR do vitrine com texto "recebi seu currículo"].
- **Físico:** envelope nominal escrito à mão ("A/C Dr. Fulano"), correio ou entrega em mãos. ~R$ 15–20/unidade.
- **Digital:** PDF respondendo à vaga no canal onde foi publicada.
- **Follow-up obrigatório (D+3):** "Doutor, sou o Gabriel — fui eu que mandei o currículo da Clara. Chegou aí? Ela continua disponível para a entrevista." (A ligação deixou de ser fria.)

### Play 3 — Inbound e indicação
- Toda resposta de landing/calculadora/indicação tem **SLA de 5 minutos** em horário comercial — velocidade de resposta É o produto.
- CTA único e universal: conversar com a Clara no vitrine. Sem PDF institucional, sem "agenda uma call" antes da experiência.

---

## Etapa 4 — Tratamento: a Clara trabalha o lead

O advogado entrou no vitrine. A partir daqui o produto faz o trabalho:

1. **Experiência guiada** — a Clara sugere as 3 trilhas: *"quer testar com um processo seu de verdade? me manda o número"* / agendamento / dúvida jurídica.
2. **Qualificação conversacional** — 3 perguntas naturais ao longo da conversa (nunca formulário):
   - "Quantos advogados são no escritório?"
   - "Qual a principal área de vocês?"
   - "Hoje quem responde os clientes no WhatsApp — vocês mesmos ou tem secretária?"
   As respostas ficam gravadas no perfil do lead (CRM do tenant de vendas).
3. **Gancho** — a Clara se revela e oferece o trial com link direto do cadastro.
4. **Cadência de reengajamento** (automática, via `mensagens_agendadas`): lead conversou e sumiu → D+2 lembrete leve ("ficou alguma dúvida? posso te mostrar o agendamento"), D+5 último toque com case/número. Respondeu → sai da cadência na hora.

---

## Etapa 5 — Handoff: lead quente vai para humano

**Critérios de lead quente (qualquer um dispara):**
- Pediu **preço, trial, proposta ou reunião**
- Escritório com **5+ advogados** (perfil Profissional/Escritório — ticket justifica call)
- Respondeu as 3 perguntas de qualificação e segue engajado
- Score CRM do lead em nível "excelente/satisfeito" com 3+ interações

**Mecânica do handoff:**
- A Clara **agenda a call de 20 min direto na agenda de Gabriel ou da sócia** usando o Agendamento Inteligente (disponibilidade de cada um configurada no sistema — o mesmo motor do produto).
- Divisão: alternância simples por semana, com exceção fixa — leads de indicação do pai vão para Gabriel; ajustar por área/afinidade conforme o padrão aparecer.
- Notificação por WhatsApp na hora (mesmo mecanismo de escalação do produto). **SLA: primeiro contato humano em até 15 min** em horário comercial.
- Antes da call, quem atende recebe o **resumo da conversa do lead com a Clara** (histórico + qualificação) — ninguém pergunta o que o lead já respondeu.

**Roteiro da call de 20 min:**
1. (5 min) Dor — deixar o advogado falar de como atende hoje
2. (10 min) Demo dirigida — com processos DELE (demo pré-carregada quando possível)
3. (5 min) Plano recomendado + trial + próximo passo com data

---

## Etapa 6 — Fechamento e ativação

- **Essencial** → self-service: link de checkout Stripe (trial 7 dias) na própria conversa. Sem call obrigatória.
- **Profissional/Escritório** → call + onboarding assistido (wizard de 6 etapas junto, na tela).
- **Nurturing do trial** (automático):
  - D+1: "Conectou o WhatsApp? É 1 QR code."
  - D+3: "Suba 5 petições no RAG — a IA fica visivelmente melhor."
  - D+6: "Seu trial termina amanhã. A Clara atendeu X mensagens e economizou ~Y horas."
- **Alerta de trial travado:** cadastrou e não conectou WhatsApp em 48h → notificação interna → contato humano.
- **Pós-venda que realimenta o funil:** NPS ≥ 9 → a própria IA convida a indicar um colega (mês grátis para ambos). Cliente com 90 dias de resposta < 1 min ganha o selo "Escritório que Responde".

---

## Métricas e metas

**Por etapa (revisão toda sexta):**

| Métrica | Meta inicial |
|---|---|
| Alvos levantados/semana | 40 |
| Aprovados no filtro (A+B) | ~25 |
| Abordagens enviadas | 15–20 |
| Taxa de resposta | ≥ 25% |
| Conversas na Clara | ≥ 4 |
| Handoffs (leads quentes) | ≥ 2 |
| Trials iniciados | 1–2 |
| Conversão trial → pagante | ≥ 50% |
| SLA lead quente | < 15 min |

**Sinais de ajuste:** resposta < 15% em 20 abordagens → trocar mensagem/alvo antes de escalar; conversa na Clara sem virar quente → revisar as trilhas e o gancho; trial sem conectar WhatsApp → problema de onboarding, não de vendas.

---

## O que já existe × o que falta construir

| Peça | Status | Onde |
|---|---|---|
| Atendimento/qualificação do lead (Clara) | ✅ existe — é o orquestrador | `feature_1_ia_personalizada/services/ai/` |
| Agendamento da call na agenda dos sócios | ✅ existe | Agendamento Inteligente |
| Cadência de follow-up | ✅ existe o motor | `mensagens_agendadas` + dispatcher |
| Lead scoring / análise do lead | ✅ existe | CRM Inteligente (tenant de vendas) |
| Trial + checkout | ✅ existe | Billing Stripe |
| Tenant de vendas + persona Clara | 🔨 construir (seed) | `feature_vendas/seeds/tenant_vendas.py` |
| Campo `origem` + wa.me pré-preenchido | 🔨 construir (pequeno) | cadastro + landing |
| Relatório de funil | 🔨 construir | `feature_vendas/services/funil.py` |
| Gerador de mensagem-espelho | 🔨 construir (Fase 2) | `feature_vendas/services/espelho_gerador.py` |
| Arte do currículo da Clara | 🔨 construir | `feature_vendas/assets/curriculo_clara.html` |
| Calculadora da dor | 🔨 construir (Fase 2) | `frontend/landing` |
| Motor de listas (CNAE, vagas) | ⏳ Fase 3 — só após funil manual converter | `feature_vendas/services/listas/` |

## Cronograma

- **Semana 1 (13–17/07):** infra (vitrine + landing com wa.me + planilha) → 15 abordagens manuais (Play 1) → retro com números na sexta.
- **Semana 2 (20–24/07):** follow-ups D+3/D+7 · lote piloto de 10 currículos (Play 2) · campo `origem` + funil básico no código.
- **Semanas 3–4:** calculadora + gerador de espelho + cadência automática — **se** os números das semanas 1–2 confirmarem.
- **Agosto:** máquina completa (Fases 2–3) rodando antes do T2 do plano anual.
