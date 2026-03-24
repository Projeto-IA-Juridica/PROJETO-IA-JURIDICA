# TASKS — Feature 3: Prospecção Inteligente

> **Escopo:** motor de captação de clientes para advogados. O DNA do escritório guia o tipo de lead gerado — empresas (B2B) para escritórios corporativos/trabalhistas, pessoas físicas (B2C) para família/consumidor/previdência.
> **Acesso:** exclusivo para `advogado` e `admin`.
> **Referência:** [README.md](README.md) — seção "Feature 3 — Prospecção Inteligente"

---

## O que a Feature 3 entrega

| Entrega | Descrição |
|---|---|
| **DNA do Advogado** | Analisa o histórico de processos do escritório e classifica as especialidades, setores de atuação e o tipo de lead ideal (empresa ou pessoa). |
| **Descoberta via DataJud** | Usa DataJud como motor principal: busca quem está litigando nos tipos de ação que o escritório domina. Leads descobertos já têm demanda jurídica comprovada. |
| **Enriquecimento** | Empresas → Receita Federal (porte, setor, sócios) + LinkedIn opcional. Pessoas → apenas dados do processo público (nome, polo, fase). |
| **Matching & Score** | Claude cruza o DNA com os dados do lead e gera score 0–100 + motivo + abordagem personalizada. |
| **Pipeline de Prospecção** | Lista ranqueada de leads com status gerenciável (novo → contatado → qualificado → descartado). Suporta os dois tipos no mesmo pipeline. |

---

## Compliance — LGPD e OAB

Esta seção deve ser lida antes de qualquer implementação. Viola esses limites = risco de suspensão de OAB.

### OAB — Captação Indevida de Clientela (Provimento 205/2021)

| Regra | Como aplicamos |
|---|---|
| Proibido contatar pessoa física de forma não solicitada usando dados de litígio | Leads B2C **nunca** mostram telefone, email ou dado de contato — só nome e contexto processual. O advogado aborda pela via processual, não por cold call. |
| Proibido usar processo judicial para captação mercantil explícita | O score e o motivo gerados pelo Claude **nunca** afirmam "esse cliente vai perder" ou "você tem chance nesse caso" — só descrevem o contexto. |
| Material de prospecção não pode prometer resultado | `SYSTEM_PROMPT_MATCH_SCORE` e `SYSTEM_PROMPT_DNA_ADVOGADO` têm restrição explícita de nunca prever resultado. |
| Proibição de abordagem direta em corredores de fóruns e similares | Fora do escopo do sistema — responsabilidade do advogado no uso. |

### LGPD — Lei 13.709/2018

| Dado | Tipo | Base legal | Limite |
|---|---|---|---|
| CNPJ, razão social, sócios | Dados de empresa (não são dados pessoais pela LGPD) | N/A | Sem restrição — são públicos |
| Nome de pessoa física em processo público | Dado pessoal | Legítimo interesse + dado publicizado pelo titular (art. 7º, IX) | Só nome e contexto processual. **Nunca CPF, telefone, endereço.** |
| Nome de sócio via Receita Federal | Dado pessoal publicizado | Legítimo interesse | Só nome e qualificação (sócio-administrador, etc.) |
| Contato LinkedIn | Dado pessoal | Requer consentimento ou legítimo interesse específico | Só disponível se LinkedIn aprovado; nunca armazenar email |

**Regra prática implementada no código:**
- Lead do tipo `pessoa`: campos `cpf`, `telefone`, `email` **não existem** no modelo — impedido por design, não só por regra
- Lead do tipo `empresa`: sócios armazenados apenas com nome + qualificação (sem CPF dos sócios)
- Nenhum dado de pessoa física vai para o Redis em texto plano

---

## Fontes de dados

| Dado | Origem | Tipo de lead | Custo / Acesso | Status |
|---|---|---|---|---|
| Histórico de processos do escritório | `processos` table | Ambos | Zero | ✅ Disponível |
| Empresas/pessoas litigando por tipo de ação | DataJud CNJ | Ambos | Gratuito | ✅ Disponível |
| Dados cadastrais + sócios de empresa | ReceitaWS | Empresa | Gratuito, rate limit moderado | ✅ Implementado |
| Funcionários e cargos | LinkedIn API | Empresa | Requer Partner Program | ✅ Implementado com fallback |
| Análise de DNA e scoring | Claude Haiku | Ambos | ~$0.001 por lead | ✅ Disponível |

> **DataJud como motor de descoberta:** em vez de o advogado buscar um CNPJ específico, o sistema busca no DataJud por `tipo_acao` — retornando quem já está em litígio nessa área. Essa inversão é o diferencial: os leads chegam com necessidade jurídica comprovada.

---

## Controle de acesso

```
cliente       → 403 Forbidden
estagiario    → 403 Forbidden
assistente    → 403 Forbidden
advogado      → acesso total (ver e criar leads do próprio escritório)
admin         → acesso total
```

---

## Modelo de Dados

### Atualização na tabela `leads_prospeccao` (já criada na 3.4)

A migration 011 precisa de um campo `tipo_lead` e a remoção do que não se aplica a pessoas:

```sql
-- Adicionar à migration 011 ou criar 011b
ALTER TABLE leads_prospeccao
    ADD COLUMN tipo_lead VARCHAR(10) NOT NULL DEFAULT 'empresa';
    -- 'empresa' | 'pessoa'

-- Para leads do tipo 'pessoa':
-- empresa_nome armazena o nome da pessoa
-- cnpj armazena o número CNJ do processo (não um CNPJ real)
-- socios permanece vazio []
-- contatos_linkedin permanece vazio []
-- processos_publicos contém o processo que originou o lead
-- NUNCA armazenar CPF, telefone ou email de pessoa física
```

### Campo `dna_prospeccao` no `escritorios`

```sql
ALTER TABLE escritorios
    ADD COLUMN dna_prospeccao JSONB DEFAULT NULL;
-- Estrutura: {especialidades, setores_alvo, tipo_lead_predominante,
--             perfil_cliente_ideal, diferenciais, gerado_em}
```

---

## Status Geral

| Subtarefa | Status |
|---|---|
| 3.1 — Role guard (`require_advogado`) | ✅ Concluída |
| 3.2 — `ReceitaFederalClient` | ✅ Concluída |
| 3.3 — `LinkedInClient` (com fallback) | ✅ Concluída |
| 3.4 — Migration `leads_prospeccao` + modelo SQLAlchemy | ✅ Concluída (precisa de `tipo_lead`) |
| 3.4b — Atualizar migration: `tipo_lead` + `dna_prospeccao` em escritorios | ⬜ Pendente |
| 3.5 — `DNAAdvogadoService` | ⬜ Pendente |
| 3.6 — `DataJudProspeccaoClient` (busca por tipo_acao, não por CNJ) | ⬜ Pendente |
| 3.7 — `EmpresaIntelligenceService` (B2B) | ⬜ Pendente |
| 3.8 — `PessoaIntelligenceService` (B2C) | ⬜ Pendente |
| 3.9 — `MatchingService` (suporta empresa e pessoa) | ⬜ Pendente |
| 3.10 — Prompts para DNA e Matching | ⬜ Pendente |
| 3.11 — Schemas Pydantic | ⬜ Pendente |
| 3.12 — Rotas `/prospeccao/*` | ⬜ Pendente |
| 3.13 — Testes unitários | ⬜ Pendente |
| 3.14 — Testes de integração | ⬜ Pendente |

---

## 3.1 — Role guard ✅ (feito)

`require_advogado`, `get_escritorio_id_advogado`, `get_advogado_id` em `api/middleware/auth.py`.

---

## 3.2 — `ReceitaFederalClient` ✅ (feito)

`services/prospeccao/receita_federal_client.py` — busca CNPJ com cache Redis 24h, retry, rate limit gracioso.

---

## 3.3 — `LinkedInClient` ✅ (feito)

`services/prospeccao/linkedin_client.py` — modo degradado sem credenciais, filtro de cargos por substring (intencionalmente permissivo), cache 7 dias.

---

## 3.4 — Migration + modelo ✅ (feito, precisa de complemento em 3.4b)

`alembic/versions/011_add_leads_prospeccao.py` + `shared/models/lead_prospeccao.py`.

---

## 3.4b — Atualizar modelo e migration: `tipo_lead` + `dna_prospeccao`

**Objetivo:** adicionar `tipo_lead` na tabela `leads_prospeccao` e `dna_prospeccao` na tabela `escritorios`.

**Arquivo a criar:** `alembic/versions/012_add_tipo_lead_e_dna.py`

- [ ] `upgrade()`:
  ```sql
  ALTER TABLE leads_prospeccao
      ADD COLUMN tipo_lead VARCHAR(10) NOT NULL DEFAULT 'empresa';

  CREATE INDEX ix_leads_tipo ON leads_prospeccao (escritorio_id, tipo_lead);

  ALTER TABLE escritorios
      ADD COLUMN dna_prospeccao JSONB DEFAULT NULL;
  ```
- [ ] `downgrade()`: DROP COLUMN em ambas

**Arquivo a tocar:** `shared/models/lead_prospeccao.py`
- [ ] Adicionar `tipo_lead: Mapped[str] = mapped_column(String(10), server_default="empresa", nullable=False)`

**Arquivo a tocar:** `shared/models/escritorio.py`
- [ ] Adicionar `dna_prospeccao: Mapped[dict | None] = mapped_column(JSONB, nullable=True)`

**Critério de aceite:** `alembic upgrade head` passa; modelo reflete os campos; `downgrade -1` reverte.

---

## 3.5 — `DNAAdvogadoService`

**Objetivo:** ler o histórico de processos do escritório e gerar o perfil de especialização — incluindo qual tipo de lead faz sentido (empresa ou pessoa).

**Arquivo a criar:** `feature_1_ia_personalizada/services/prospeccao/dna_advogado.py`

- [ ] Classe `DNAAdvogadoService`
- [ ] Método `async gerar_dna(escritorio_id: int, db: AsyncSession) -> DNAEscritorio`:
  1. Query em `processos` por `escritorio_id`:
     - `COUNT(*) GROUP BY tipo_acao ORDER BY COUNT DESC LIMIT 10`
     - Distribuição de `polo_cliente` (autor/réu)
     - Distribuição de `fase_processual`
  2. Com < 5 processos → retorna `DNAEscritorio(dados_insuficientes=True)` sem Claude
  3. Com ≥ 5 processos → chama Claude com `SYSTEM_PROMPT_DNA_ADVOGADO`:
     - `especialidades: list[str]` — áreas do direito
     - `setores_alvo: list[str]` — setores de empresa (para B2B) ou perfis de pessoa (para B2C)
     - `tipo_lead_predominante: "empresa" | "pessoa" | "ambos"`
     - `perfil_cliente_ideal: str`
     - `diferenciais: list[str]`
  4. Persiste em `escritorio.dna_prospeccao` (JSONB)
  5. Cacheia no Redis: `dna:{escritorio_id}`, TTL 6h
- [ ] Método `async obter_dna(escritorio_id: int, db: AsyncSession) -> DNAEscritorio`:
  - Redis → banco (`escritorio.dna_prospeccao`) → `gerar_dna()`
- [ ] Dataclass `DNAEscritorio`:
  ```python
  escritorio_id: int
  especialidades: list[str]
  setores_alvo: list[str]
  tipo_lead_predominante: str   # 'empresa' | 'pessoa' | 'ambos'
  perfil_cliente_ideal: str
  diferenciais: list[str]
  top_tipos_acao: list[dict]    # [{tipo, contagem, percentual}]
  dados_insuficientes: bool
  gerado_em: datetime
  ```

**Critério de aceite:** < 5 processos → sem Claude; ≥ 5 → DNA completo com `tipo_lead_predominante` inferido corretamente (trabalhista → empresa; família → pessoa).

---

## 3.6 — `DataJudProspeccaoClient`

**Objetivo:** extensão do `datajud_client.py` existente para buscar leads por tipo de ação — o motor de descoberta da feature.

> Diferente do uso atual (busca por CNJ), aqui buscamos *quem está litigando* em determinado tipo de ação.

**Arquivo a criar:** `feature_1_ia_personalizada/services/prospeccao/datajud_prospeccao.py`

- [ ] Classe `DataJudProspeccaoClient`
- [ ] Método `async buscar_litigantes(tipo_acao: str, tribunal: str | None, limite: int = 20) -> list[LitiganteEncontrado]`:
  - Query ElasticSearch no DataJud filtrando por `classe.nome` ou `assunto.nome` contendo o tipo de ação
  - Retorna partes do processo: nome, tipo (pessoa física ou jurídica), polo, número CNJ
  - Deduplicação por nome — mesmo litigante em múltiplos processos conta uma vez (mas acumula contagem)
  - Cache Redis: `datajud_prosp:{tipo_acao}:{tribunal}`, TTL 6h
- [ ] Dataclass `LitiganteEncontrado`:
  ```python
  nome: str
  tipo: str                  # 'pessoa_juridica' | 'pessoa_fisica'
  polo: str                  # 'ativo' | 'passivo'
  processos_count: int       # quantas vezes aparece nos resultados
  numero_cnj_exemplo: str    # um CNJ representativo para contexto
  tipo_acao: str
  tribunal: str
  ```
- [ ] Método `async identificar_cnpj(nome_empresa: str) -> str | None`:
  - Busca CNPJ pelo nome na Receita Federal (helper para quando o DataJud retorna nome sem CNPJ)
  - Usa `ReceitaFederalClient.buscar_por_nome()` quando disponível

**Arquivo a tocar:** não toca no `datajud_client.py` existente — cliente separado para não quebrar o monitoramento de processos.

**Critério de aceite:** busca por "reclamação trabalhista" retorna empresas com processos ativos; busca por "divórcio" retorna pessoas físicas; deduplicação funciona.

---

## 3.7 — `EmpresaIntelligenceService` (B2B)

**Objetivo:** dado um litigante identificado como pessoa jurídica, agregar dados de todas as fontes e preparar para o matching.

**Arquivo a criar:** `feature_1_ia_personalizada/services/prospeccao/empresa_intelligence.py`

- [ ] Classe `EmpresaIntelligenceService`
- [ ] Método `async enriquecer(litigante: LitiganteEncontrado, escritorio_id: int) -> EmpresaInteligencia | None`:
  1. Identificar CNPJ: via `litigante.cnpj` (se disponível) ou `DataJudProspeccaoClient.identificar_cnpj(nome)`
  2. Se CNPJ não encontrado: tenta criar lead só com nome + dados DataJud (sem Receita Federal)
  3. `asyncio.gather`:
     - `ReceitaFederalClient.buscar_cnpj(cnpj)` → cadastro + sócios
     - `LinkedInClient.buscar_funcionarios(nome)` → contatos ([] se indisponível)
  4. Monta `EmpresaInteligencia`
  5. Cache Redis: `empresa_intel:{cnpj}`, TTL 6h
- [ ] Dataclass `EmpresaInteligencia`:
  ```python
  cnpj: str | None            # None se não identificado
  razao_social: str
  situacao: str
  porte: str
  setor_cnae: str
  socios: list[dict]          # só nome + qualificacao (sem CPF — LGPD)
  processos_count: int
  tipos_acao_envolvida: list[str]
  contatos_linkedin: list[dict]
  linkedin_disponivel: bool
  ```

---

## 3.8 — `PessoaIntelligenceService` (B2C)

**Objetivo:** dado um litigante identificado como pessoa física, coletar apenas dados do processo público — sem nenhum dado pessoal adicional.

**Compliance:** este serviço é o mais sensível da feature. Qualquer dado coletado além do processo público viola LGPD ou OAB.

**Arquivo a criar:** `feature_1_ia_personalizada/services/prospeccao/pessoa_intelligence.py`

- [ ] Classe `PessoaIntelligenceService`
- [ ] Método `async enriquecer(litigante: LitiganteEncontrado) -> PessoaInteligencia`:
  - **NÃO busca CPF** — proibido por design
  - **NÃO busca telefone ou email** — proibido por design
  - Usa apenas o que o DataJud já retornou: nome, polo, tipo de ação, tribunal, fase
  - Verifica se a pessoa é a parte que *provavelmente* precisa de advogado:
    - Trabalhista: polo ativo (empregado sem representação) → lead válido
    - Consumidor: polo ativo → lead válido
    - Família: ambos os polos podem precisar de advogado
- [ ] Dataclass `PessoaInteligencia`:
  ```python
  nome: str                   # nome público do processo
  polo: str                   # 'ativo' | 'passivo'
  tipo_acao: str
  tribunal: str
  fase_processual: str
  numero_cnj_exemplo: str     # para o advogado verificar no sistema do tribunal
  # SEM: cpf, telefone, email, endereço
  ```
- [ ] Método estático `validar_compliance(litigante: LitiganteEncontrado) -> bool`:
  - Retorna `False` (descarta o lead) se o tipo de ação envolver dados especialmente sensíveis: saúde, orientação sexual, religião (art. 11 LGPD)
  - Ex: "internação compulsória", "curatela por doença mental" → não prospectar

**Critério de aceite:** nenhum campo CPF/telefone/email no dataclass; `validar_compliance` descarta ações com dados sensíveis; código revisável por um DPO sem mudanças.

---

## 3.9 — `MatchingService`

**Objetivo:** cruzar DNA do advogado com os dados do lead (empresa ou pessoa) e gerar score + abordagem. Suporta os dois tipos com lógicas separadas.

**Arquivo a criar:** `feature_1_ia_personalizada/services/prospeccao/matching.py`

- [ ] Classe `MatchingService`
- [ ] Método `async calcular_score(dna: DNAEscritorio, inteligencia: EmpresaInteligencia | PessoaInteligencia) -> ResultadoMatch`:
  - Detecta o tipo pelo `isinstance` e delega para método privado
- [ ] Método `_score_heuristico_empresa(dna, empresa) -> int`:
  - +30: processos da empresa em tipos de ação = especialidades do escritório
  - +20: setor CNAE em `dna.setores_alvo`
  - +15: empresa com 3+ processos (demanda ativa)
  - +15: contatos LinkedIn encontrados
  - +10: porte MÉDIA ou GRANDE
  - +10: situação ATIVA
- [ ] Método `_score_heuristico_pessoa(dna, pessoa) -> int`:
  - +35: tipo de ação = especialidade do escritório (peso maior pois é o único sinal forte)
  - +25: polo compatível com o perfil típico do cliente do escritório
  - +20: fase processual inicial (pessoa pode ainda não ter advogado)
  - +20: tipo de ação com alta recorrência no escritório (> 30% dos processos)
- [ ] Se score < 30: retorna sem Claude (`gerado_por_ia=False`)
- [ ] Se score ≥ 30: chama Claude com `SYSTEM_PROMPT_MATCH_SCORE`:
  - Refina score, gera `motivo` e `abordagem_sugerida`
  - Para B2C: `abordagem_sugerida` não pode mencionar dados pessoais nem cold call — só via processo
- [ ] Dataclass `ResultadoMatch`:
  ```python
  score: int
  motivo: str
  abordagem_sugerida: str
  gerado_por_ia: bool
  tipo_lead: str              # 'empresa' | 'pessoa'
  componentes: dict
  ```

---

## 3.10 — Prompts

**Arquivo a tocar:** `feature_1_ia_personalizada/services/ai/prompts.py`

- [ ] `SYSTEM_PROMPT_DNA_ADVOGADO`:
  - Input: `{nome_escritorio}`, `{top_tipos_acao}` (JSON), `{total_processos}`, `{distribuicao_polo}`
  - Output JSON: `{especialidades, setores_alvo, tipo_lead_predominante, perfil_cliente_ideal, diferenciais}`
  - Restrição: `tipo_lead_predominante` deve ser inferido das especialidades:
    - trabalhista/tributário/contratos/societário → `"empresa"`
    - família/divórcio/inventário/previdência/consumidor → `"pessoa"`
    - mistura de ambos → `"ambos"`

- [ ] `SYSTEM_PROMPT_MATCH_SCORE`:
  - Input: `{dna_escritorio}` (JSON), `{dados_lead}` (JSON), `{tipo_lead}`, `{score_heuristico}`
  - Output JSON: `{score_refinado, motivo, abordagem_sugerida}`
  - Restrições por tipo:
    - B2B: abordagem pode mencionar o contato (sócio, LinkedIn)
    - B2C: abordagem **nunca** menciona cold call, dados pessoais ou "vi que você tem um processo"
    - Ambos: nunca prever resultado, nunca citar OAB como barreira

---

## 3.11 — Schemas Pydantic

**Arquivo a criar:** `shared/schemas/prospeccao.py`

- [ ] `LeadProspeccaoResponse` — campos comuns a empresa e pessoa:
  ```python
  id: int
  tipo_lead: Literal["empresa", "pessoa"]
  nome: str                       # razao_social ou nome da pessoa
  score_match: int | None
  score_motivo: str | None
  abordagem_sugerida: str | None
  status: str
  notas_advogado: str | None
  fonte_descoberta: str | None
  criado_em: datetime
  # Campos exclusivos empresa (None para pessoa)
  cnpj: str | None
  empresa_setor: str | None
  empresa_porte: str | None
  socios: list[dict]
  contatos_linkedin: list[dict]
  linkedin_disponivel: bool
  # Campos exclusivos pessoa (None para empresa)
  polo_processo: str | None
  tipo_acao_origem: str | None
  numero_cnj_exemplo: str | None
  # Sempre presente
  processos_publicos_count: int
  ```
- [ ] `DescobertaRequest`:
  ```python
  tipo_lead: Literal["empresa", "pessoa", "auto"]  # auto = usa DNA
  tipo_acao: str          # ex: "reclamação trabalhista"
  tribunal: str | None    # ex: "TRT15" — None = todos
  limite: int = 20
  score_minimo: int = 40
  ```
- [ ] `LeadStatusUpdate`:
  ```python
  status: Literal["novo", "contatado", "qualificado", "descartado"]
  notas_advogado: str | None = None
  ```
- [ ] `PipelineResponse`:
  ```python
  total: int
  leads: list[LeadProspeccaoResponse]
  dna_disponivel: bool
  linkedin_disponivel: bool
  aviso_lgpd: str | None    # preenchido quando pipeline contém leads B2C
  ```
- [ ] `DNAEscritorioResponse`
- [ ] Exportar em `shared/schemas/__init__.py`

---

## 3.12 — Rotas `/prospeccao/*`

**Arquivo a criar:** `feature_1_ia_personalizada/api/routes/prospeccao.py`

- [ ] `GET /prospeccao/dna` — retorna DNA atual ou `dados_insuficientes=True`
- [ ] `POST /prospeccao/dna/atualizar` — força regeneração do DNA
- [ ] `POST /prospeccao/descobrir` — motor principal:
  - Body: `DescobertaRequest`
  - Fluxo: DataJud busca litigantes → filtra pelo tipo → enriquece (empresa ou pessoa) → calcula score → salva leads com score ≥ `score_minimo`
  - Retorna: `PipelineResponse` com leads recém-descobertos
  - Para leads B2C: injeta `aviso_lgpd` no response com disclaimer OAB
- [ ] `GET /prospeccao/pipeline` — lista leads salvos com filtros
- [ ] `PATCH /prospeccao/{id}/status` — atualiza status + notas
- [ ] `DELETE /prospeccao/{id}` — remove lead

---

## 3.13 — Testes unitários

- [ ] `test_dna_advogado.py` — especialidades trabalhistas → `tipo_lead_predominante = "empresa"`; família → `"pessoa"`
- [ ] `test_datajud_prospeccao.py` — busca por tipo_acao retorna litigantes; deduplicação funciona
- [ ] `test_empresa_intelligence.py` — Receita + DataJud + LinkedIn (mock); sem CNPJ → lead parcial
- [ ] `test_pessoa_intelligence.py` — sem CPF/telefone/email no dataclass; `validar_compliance` descarta ações sensíveis
- [ ] `test_matching_empresa.py` — heurística ponto a ponto; score < 30 não chama Claude
- [ ] `test_matching_pessoa.py` — heurística B2C; abordagem_sugerida não contém cold call

---

## 3.14 — Testes de integração

- [ ] `test_prospeccao_routes.py`:
  - Role guard: cliente → 403, advogado → 200
  - `POST /prospeccao/descobrir` com mock DataJud → leads salvos no banco
  - Pipeline B2C: `aviso_lgpd` presente no response
  - Lead de outro escritório → 403 no PATCH
  - Deduplicação: mesmo CNPJ pesquisado duas vezes → atualiza, não duplica

---

## Arquivos criados até agora

```
✅ feature_1_ia_personalizada/api/middleware/auth.py          (+require_advogado)
✅ feature_1_ia_personalizada/services/prospeccao/__init__.py
✅ feature_1_ia_personalizada/services/prospeccao/receita_federal_client.py
✅ feature_1_ia_personalizada/services/prospeccao/linkedin_client.py
✅ shared/models/lead_prospeccao.py
✅ alembic/versions/011_add_leads_prospeccao.py
```

## Arquivos a criar

```
feature_1_ia_personalizada/services/prospeccao/
├── dna_advogado.py               # 3.5
├── datajud_prospeccao.py         # 3.6
├── empresa_intelligence.py       # 3.7
├── pessoa_intelligence.py        # 3.8
└── matching.py                   # 3.9

feature_1_ia_personalizada/api/routes/
└── prospeccao.py                 # 3.12

shared/schemas/
└── prospeccao.py                 # 3.11

alembic/versions/
└── 012_add_tipo_lead_e_dna.py    # 3.4b
```

## Arquivos existentes a modificar

```
shared/models/lead_prospeccao.py     → + tipo_lead
shared/models/escritorio.py          → + dna_prospeccao JSONB
shared/schemas/__init__.py           → + exports de prospeccao.py
feature_1_ia_personalizada/api/app.py → + include_router(prospeccao_router)
feature_1_ia_personalizada/services/ai/prompts.py → + 2 prompts
shared/config/settings.py            → ✅ LinkedIn vars já adicionadas
```

---

## Ordem de implementação

```
3.4b (tipo_lead + dna_prospeccao)
  → 3.5 (DNAAdvogadoService)
    → 3.6 (DataJudProspeccaoClient)  ← pode ser paralelo com 3.7 e 3.8
    → 3.7 (EmpresaIntelligenceService)
    → 3.8 (PessoaIntelligenceService)
      → 3.9 (MatchingService)
        → 3.10 (Prompts)     ← pode ser paralelo com 3.11
        → 3.11 (Schemas)
          → 3.12 (Rotas)
            → 3.13 (Testes unit)
              → 3.14 (Testes integração)
```
