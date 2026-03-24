# Feature 3 — Prospecção Inteligente

> **Acesso:** exclusivo para `advogado` e `admin`
> **Plano:** profissional e enterprise

---

## O problema que resolve

O advogado precisa de novos clientes, mas enfrenta barreiras concretas:

| Problema | Impacto |
|---|---|
| Não sabe quem está precisando de advogado agora | Prospecção ineficiente, muito tempo gasto |
| Cold call é proibido pela OAB (Provimento 205/2021) | Risco disciplinar em abordagens diretas |
| LinkedIn manual leva horas por lead | Custo operacional alto, baixa escala |
| Não sabe quais setores combinam com seu perfil | Leads fora do nicho = tempo perdido |
| Qualificação manual de leads | Energia gasta em prospects sem fit |

---

## Como a feature resolve

### Passo 1 — DNA do Escritório

O sistema lê o histórico de processos do escritório e monta um perfil de especialização automaticamente.

```
banco de processos
┌─────────────────────┐
│ 47 × trabalhista    │ ──┐
│ 18 × consumidor     │ ──┤  Claude Haiku analisa
│  9 × tributário     │ ──┤  (~$0.001 por geração)
│  3 × família        │ ──┘
└─────────────────────┘
           │
           ▼
┌──────────────────────────────────────────┐
│  DNA do Escritório                       │
│  especialidades: ["trabalhista",         │
│                   "consumidor"]          │
│  tipo_lead: "empresa"                    │  ← escritório atua vs empresas
│  setores_alvo: ["varejo", "logística"]   │
│  diferenciais: ["histórico TRT2"]        │
│  perfil_cliente_ideal: "empresas médias  │
│    do setor varejista com recorrência    │
│    de processos trabalhistas"            │
└──────────────────────────────────────────┘
                   cached Redis 6h / persistido em escritorios.dna_prospeccao
```

O DNA determina automaticamente se o escritório deve prospectar **empresas (B2B)** ou **pessoas físicas (B2C)** com base nas especialidades identificadas:

| Especialidades detectadas | `tipo_lead_predominante` |
|---|---|
| Trabalhista, tributário, societário, contratos | `empresa` |
| Família, divórcio, inventário, previdência, consumidor | `pessoa` |
| Mistura de ambos | `ambos` |

---

### Passo 2 — DataJud como motor de descoberta

O advogado (ou o sistema automaticamente) dispara uma busca. Em vez de o advogado ir atrás do cliente, o sistema encontra **quem já está em litígio** na área de especialidade do escritório.

```
Busca: "reclamação trabalhista"

┌─────────────────────────────────────────────────────┐
│  TRT2 (SP)  ──┐                                     │
│  TRT4 (RS)  ──┤  5 buscas em paralelo               │
│  TRT3 (MG)  ──┤  asyncio.gather                     │
│  TRT1 (RJ)  ──┤  ~2 segundos de espera              │
│  TRT9 (PR)  ──┘                                     │
└─────────────────────────────────────────────────────┘
                    │
                    ▼
          300 processos retornados
          → extrai todas as partes (nome, polo, tipo)
          → deduplica por nome
          → ordena por: sem advogado primeiro → mais processos
```

> **Por que isso é poderoso:** esses leads já têm **demanda jurídica comprovada**. Não é um lead frio — é alguém que está ativamente em litígio na especialidade do escritório, muitas vezes sem representação. O advogado chega na conversa sabendo exatamente o contexto.

---

### Passo 3 — Enriquecimento por tipo de lead

```
B2B (pessoa jurídica)                    B2C (pessoa física)
─────────────────────                    ───────────────────
EMPRESA X LTDA                           Maria Oliveira
        │                                        │
        ├─ Receita Federal (grátis)              └─ apenas dados do processo
        │   razão social, porte,                    nome, polo, fase, tribunal
        │   CNAE, situação, sócios                  ← NADA ALÉM DISSO (LGPD)
        │   (sócios: nome + qualificação
        │    — nunca CPF)
        │
        └─ LinkedIn (opcional, Partner Program)
            decisores, cargos, URLs de perfil
```

Se o LinkedIn não estiver configurado, o fluxo continua normalmente com Receita + DataJud. A ausência do LinkedIn não bloqueia nenhuma funcionalidade.

---

### Passo 4 — Score de matching

Cada lead recebe um score de 0 a 100 calculado em duas etapas:

**Etapa 1 — Heurística rápida (sem IA):**

| Critério | Pontos B2B | Pontos B2C |
|---|---|---|
| Tipo de ação = especialidade do escritório | +30 | +35 |
| Setor CNAE ∈ setores-alvo do DNA | +20 | — |
| Polo compatível com perfil típico do cliente | — | +25 |
| Fase processual inicial (ainda pode não ter advogado) | — | +20 |
| Empresa com 3+ processos (demanda ativa) | +15 | — |
| Tipo de ação com alta recorrência no escritório (>30%) | — | +20 |
| Contatos LinkedIn encontrados | +15 | — |
| Porte MÉDIA ou GRANDE | +10 | — |
| Situação ATIVA | +10 | — |

- **Score < 30** → descartado silenciosamente, sem custo de IA
- **Score ≥ 30** → refinado pelo Claude Haiku

**Etapa 2 — Refinamento com Claude Haiku (~$0.001–0.003/lead):**

```
Input:  DNA do escritório (JSON) + dados do lead (JSON) + score bruto
Output: score_refinado (0–100) + motivo (texto) + abordagem_sugerida (texto)

Restrições no prompt:
  B2B → abordagem pode mencionar o contato (sócio, perfil LinkedIn)
  B2C → abordagem nunca menciona cold call nem dados pessoais
  Ambos → nunca prever resultado do processo, nunca citar OAB como barreira
```

---

### Passo 5 — Pipeline na tela do advogado

```
┌──────────────────────────────────────────────────────────────────────────┐
│  LEADS DESCOBERTOS — reclamação trabalhista                              │
├───────────────────────┬───────┬──────────────────────────────────────────┤
│  Lead                 │ Score │  Abordagem sugerida (Claude)             │
├───────────────────────┼───────┼──────────────────────────────────────────┤
│  Varejista X Ltda     │  87   │  "4 processos ativos no TRT2. Contato    │
│  ● 4 processos        │  ████ │  sugerido: João Silva (Dir. RH) via      │
│  ● sem advogado       │       │  LinkedIn. Abordagem: gestão preventiva."│
├───────────────────────┼───────┼──────────────────────────────────────────┤
│  Logística Y S.A.     │  71   │  "2 reclamações recentes, empresa em     │
│  ● 2 processos        │  ███  │  expansão (EPP→ME). Fase inicial —       │
│  ● enriquecimento ✓   │       │  sem advogado listado."                  │
├───────────────────────┼───────┼──────────────────────────────────────────┤
│  Maria Oliveira       │  65   │  "Parte ativa em reclamação trabalhista, │
│  ● pessoa física      │  ███  │  fase de contestação. Verificar via      │
│  ● sem advogado       │       │  processo nº CNJ para contato formal."   │
└───────────────────────┴───────┴──────────────────────────────────────────┘

Status gerenciável por lead:
  novo → contatado → qualificado → descartado

Notas do advogado salvas por lead (campo livre)
```

---

## Arquitetura técnica

```
feature_1_ia_personalizada/
└── services/prospeccao/
    ├── dna_advogado.py              ← lê histórico, gera DNA via Claude
    ├── datajud_prospeccao.py        ← busca litigantes por tipo_acao
    ├── receita_federal_client.py    ← enriquecimento CNPJ (ReceitaWS, grátis)
    ├── linkedin_client.py           ← decisores (modo degradado sem credenciais)
    ├── empresa_intelligence.py      ← agrega B2B (Receita + LinkedIn + DataJud)
    ├── pessoa_intelligence.py       ← agrega B2C (só DataJud, LGPD-safe)
    └── matching.py                  ← heurística + Claude score

feature_1_ia_personalizada/api/routes/
└── prospeccao.py                    ← endpoints /prospeccao/*

shared/
├── models/lead_prospeccao.py        ← tabela leads_prospeccao
├── models/escritorio.py             ← + coluna dna_prospeccao (JSONB)
└── schemas/prospeccao.py            ← Pydantic I/O
```

### Fontes de dados

| Dado | Origem | Custo | Fallback |
|---|---|---|---|
| Histórico de processos do escritório | `processos` (banco interno) | Zero | N/A |
| Litigantes por tipo de ação | DataJud CNJ (ElasticSearch público) | Gratuito | Lista vazia |
| Dados cadastrais + sócios | ReceitaWS | Gratuito (rate limit 3 req/min) | Lead sem enriquecimento |
| Decisores e cargos | LinkedIn API | Requer Partner Program | `[]` silencioso |
| DNA e scoring | Claude Haiku | ~$0.001–0.005 por operação | Heurística sem IA |

### Cache (Redis)

| Dado | Chave | TTL |
|---|---|---|
| DNA do escritório | `dna:{escritorio_id}` | 6h |
| Resultado de busca DataJud | `datajud_prosp:{tipo_acao}:{tribunal}` | 6h |
| Dados Receita Federal | `receita:{cnpj}` | 24h |
| Inteligência de empresa | `empresa_intel:{cnpj}` | 6h |
| Funcionários LinkedIn | `linkedin:{nome_empresa}` | 7 dias |
| Token LinkedIn OAuth | `linkedin:access_token` | 23h |

---

## Compliance embutido

A conformidade com OAB e LGPD está implementada por design — o advogado não precisa saber nada disso.

### OAB — Provimento 205/2021 (Captação Indevida de Clientela)

| Regra | Como está implementado |
|---|---|
| Proibido contatar pessoa física com dados de litígio | Leads B2C **nunca** exibem telefone, email ou endereço — não existem como campos no modelo |
| Proibido usar processo para captação mercantil explícita | Claude nunca afirma "você tem chance neste caso" — restrito no system prompt |
| Material de prospecção não pode prometer resultado | `SYSTEM_PROMPT_MATCH_SCORE` proíbe predição de resultado |
| Proibição de cold call | `abordagem_sugerida` B2C nunca menciona cold call — restrito no prompt |
| Aviso ao advogado quando pipeline contém B2C | Campo `aviso_lgpd` no response `PipelineResponse` preenchido automaticamente |

### LGPD — Lei 13.709/2018

| Dado | Tratamento |
|---|---|
| CNPJ, razão social, sócios (PJ) | Dados públicos — sem restrição |
| Nome de pessoa física em processo público | Só nome + contexto processual. Base: legítimo interesse + dado publicizado (art. 7º, IX) |
| Nome de sócio (Receita Federal) | Só nome + qualificação. Campos CPF/telefone ignorados na normalização |
| Contato LinkedIn | Só nome, cargo e URL pública. Email nunca armazenado |
| **CPF, telefone, email de PF** | **Não existem como colunas no modelo** — impedido por design, não por regra |

---

## Custo estimado por escritório/mês

| Operação | Custo unitário | Volume estimado | Custo mensal |
|---|---|---|---|
| Gerar/atualizar DNA | ~$0.001 | 4×/mês | ~$0.004 |
| Score Claude por lead | ~$0.002 | 100 leads/mês | ~$0.20 |
| Enriquecimento Receita | Grátis | 100 CNPJs/mês | $0 |
| **Total estimado** | | | **~$0.20/escritório** |

---

## Endpoints

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/prospeccao/dna` | Retorna DNA atual ou `dados_insuficientes=true` |
| `POST` | `/prospeccao/dna/atualizar` | Força regeneração do DNA |
| `POST` | `/prospeccao/descobrir` | Motor principal: busca → enriquece → score → salva leads |
| `GET` | `/prospeccao/pipeline` | Lista leads salvos com filtros (status, tipo, score_min) |
| `PATCH` | `/prospeccao/{id}/status` | Atualiza status + notas do advogado |
| `DELETE` | `/prospeccao/{id}` | Remove lead do pipeline |

Todos os endpoints exigem role `advogado` ou `admin`. Isolamento multi-tenant garantido por `escritorio_id` em cada query.
