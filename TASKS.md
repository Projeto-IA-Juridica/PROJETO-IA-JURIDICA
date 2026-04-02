# TASKS — Feature 3: Prospecção Inteligente

> **Escopo:** motor de captação de clientes para advogados. O DNA do escritório guia o tipo de lead gerado — empresas (B2B) para escritórios corporativos/trabalhistas, pessoas físicas (B2C) para família/consumidor/previdência.
> **Acesso:** exclusivo para `advogado` e `admin`.
> **Referência:** [README.md](README.md) — seção "Feature 3 — Prospecção Inteligente"

---

## O que a Feature 3 entrega

<<<<<<< HEAD
| Entrega | Descrição |
|---|---|
| **DNA do Advogado** | Analisa o histórico de processos do escritório e classifica as especialidades, setores de atuação e o tipo de lead ideal (empresa ou pessoa). |
| **Descoberta via DataJud** | Usa DataJud como motor principal: busca quem está litigando nos tipos de ação que o escritório domina. Leads descobertos já têm demanda jurídica comprovada. |
| **Enriquecimento** | Empresas → Receita Federal (porte, setor, sócios) + LinkedIn opcional. Pessoas → apenas dados do processo público (nome, polo, fase). |
| **Matching & Score** | Claude cruza o DNA com os dados do lead e gera score 0–100 + motivo + abordagem personalizada. |
| **Pipeline de Prospecção** | Lista ranqueada de leads com status gerenciável (novo → contatado → qualificado → descartado). Suporta os dois tipos no mesmo pipeline. |
=======
| Feature | Status | Observações |
|---------|--------|-------------|
| Feature 7 — CRM Inteligente | **100% ✅** | Totalmente implementada e testada |
| Feature 3 — Resumo Inteligente | **100% ✅** | Totalmente implementada e testada |
| Feature 2 — Score de Risco | **100% ✅** | Implementada dentro de `vitoria_preditor.py`; ver nota 2.2 |
| Feature 5 — Analytics | **100% ✅** | Totalmente implementada e testada |
| Feature 6 — Escalação | **100% ✅** | Funcional; arquitetura consolidada no manager; ver nota 6.1 |
| Feature 1 — RAG | **100% ✅** | Totalmente implementada; divergências intencionais do spec (ver notas) |
| Feature 4 — Onboarding | **100% ✅** | Totalmente implementada e testada |
| P1 — Paralelismo Orquestrador | **100% ✅** | `asyncio.gather` em DataJud + RAG com timeout 15s |
| P2 — Prefetch Worker | **100% ✅** | `ThreadPoolExecutor` paralela `update_andamento` + `_atualizar_score` |
| P3 — Cache contexto escritório | **100% ✅** | Embeddings em batch com Redis; escritorio carregado por request |
| P4 — Warm-up embeddings | **100% ✅** | `_warmup_embeddings()` no lifespan de `app.py`; falha silenciosa |

### Problemas Conhecidos / Resolvidos
1. ~~**Migration 004 com down_revision errado**~~ — **✅ CORRIGIDO** `down_revision` atualizado de `"003_add_processo_state"` para `"e4bcb5d405fa"`. Migration agora segue a cadeia correta após o merge node.
2. **Dois arquivos `008_*`** — `008_add_analytics_indexes.py` e `008_add_onboarding_fields.py` ambos dependem de `e4bcb5d405fa`. Alembic trata como branches paralelas; ok enquanto não interferirem.
3. **ScoreRiscoCalculator em `vitoria_preditor.py`** — implementado no arquivo legado em vez do `score_risco.py` separado especificado no task. Funcional, mas acoplado ao arquivo antigo.
4. **RAG usa `vector(1024)` e índice HNSW** — spec pedia `vector(1536)` e IVFFlat. Decisão intencional: HNSW funciona em tabela vazia e tem recall estável com inserts incrementais.
>>>>>>> 7ee32f2 (config inicial ts/react)

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
| 3.4 — Migration `leads_prospeccao` + modelo SQLAlchemy | ✅ Concluída |
| 3.4b — Atualizar migration: `tipo_lead` + `dna_prospeccao` em escritorios | ✅ Concluída |
| 3.5 — `DNAAdvogadoService` | ✅ Concluída |
| 3.6 — `DataJudProspeccaoClient` (busca por tipo_acao, não por CNJ) | ✅ Concluída |
| 3.7 — `EmpresaIntelligenceService` (B2B) | ✅ Concluída |
| 3.8 — `PessoaIntelligenceService` (B2C) | ✅ Concluída |
| 3.9 — `MatchingService` (suporta empresa e pessoa) | ✅ Concluída |
| 3.10 — Prompts para DNA e Matching | ✅ Concluída |
| 3.11 — Schemas Pydantic | ✅ Concluída |
| 3.12 — Rotas `/prospeccao/*` | ✅ Concluída |
| 3.13 — Testes unitários | ✅ Concluída |
| 3.14 — Testes de integração | ✅ Concluída |

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

## 3.13 — Testes unitários ✅

- [x] `test_dna_advogado.py` — especialidades trabalhistas → `tipo_lead_predominante = "empresa"`; família → `"pessoa"`
- [x] `test_datajud_prospeccao.py` — busca por tipo_acao retorna litigantes; deduplicação funciona
- [x] `test_empresa_intelligence.py` — Receita + DataJud + LinkedIn (mock); sem CNPJ → lead parcial
- [x] `test_pessoa_intelligence.py` — sem CPF/telefone/email no dataclass; `validar_compliance` descarta ações sensíveis
- [x] `test_matching_empresa.py` — heurística ponto a ponto; score < 30 não chama Claude
- [x] `test_matching_pessoa.py` — heurística B2C; abordagem_sugerida não contém cold call

---

## 3.14 — Testes de integração ✅

- [x] `test_prospeccao_routes.py`:
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

---

---

# TASKS — Feature Harvey: Hub do Advogado

> **Conceito:** Ecossistema de IA dual — cliente usa Claude (fluido), advogado usa Harvey AI (raciocínio jurídico pesado) via WhatsApp dedicado. Um Roteador de Confiança decide quando Claude delega para Harvey no fluxo do cliente.
> **Acesso:** Hub do Advogado restrito a `advogado` e `admin`. Roteador opera transparentemente no fluxo do cliente.
> **Referência:** [docs/FEATURE_HARVEY_HUB_ADVOGADO.md](docs/FEATURE_HARVEY_HUB_ADVOGADO.md)

---

## Status Geral

| Fase | Descrição | Status |
|------|-----------|--------|
| Fase 1 | Fundação Harvey (client + settings + feature flag) | ❌ Não iniciada |
| Fase 2 | Roteador de Confiança Claude → Harvey | ❌ Não iniciada |
| Fase 3 | Hub do Advogado via WhatsApp | ❌ Não iniciada |
| Fase 4 | Análise de Petições (PDF → Harvey) | ❌ Não iniciada |
| Fase 5 | Resumo de Processos e Insights CRM | ❌ Não iniciada |

---

## Pré-requisito: Confirmar com equipe Harvey antes de iniciar

- [ ] Confirmar formato do endpoint de chat (`POST /v1/chat/completions` ou formato próprio)
- [ ] Confirmar existência de endpoint dedicado para análise de PDFs
- [ ] Confirmar latência aceitável do Brasil (Harvey é US-based)
- [ ] Confirmar modelo de pricing (por token? por request? por documento?)
- [ ] Confirmar rate limits (requests/minuto por API key)
- [ ] Confirmar suporte nativo ao português brasileiro (ou necessita prompt em inglês)
- [ ] Confirmar acesso à base de jurisprudência brasileira (STJ/STF/TJs)
- [ ] Obter `HARVEY_API_KEY` de produção e staging

---

## FASE 1 — Fundação Harvey (2–3 dias)

> Objetivo: Harvey funcionando isoladamente, sem impacto algum no fluxo existente do cliente.
> Critério de aceite: `HarveyClient.gerar_resposta()` retorna resposta válida num teste de integração.

---

### 1.1 — `HarveyClient` (`services/ai/harvey_client.py`) — arquivo NOVO

- [ ] Criar arquivo `feature_1_ia_personalizada/services/ai/harvey_client.py`
- [ ] Criar enum `TipoAnaliseHarvey` com valores:
  - `ANALISE_COMPLETA = "analise_completa"`
  - `PONTOS_FRACOS = "pontos_fracos"`
  - `JURISPRUDENCIA_RELACIONADA = "jurisprudencia_relacionada"`
  - `RESUMO_EXECUTIVO = "resumo_executivo"`
  - `CONTRA_ARGUMENTOS = "contra_argumentos"`
- [ ] Criar dataclass `HarveyResponse` com campos:
  - `conteudo: str`
  - `tokens_input: int`
  - `tokens_output: int`
  - `custo_estimado: Decimal`
  - `modelo: str`
  - `latencia_ms: int`
- [ ] Criar dataclass `AnaliseHarveyResponse` com campos:
  - `tipo_peca: str`
  - `pontos_fortes: list[str]`
  - `vulnerabilidades: list[str]`
  - `argumentos_ausentes: list[str]`
  - `precedentes_relevantes: list[str]`
  - `sugestoes: list[str]`
  - `score_qualidade: int` (0–100)
  - `recomendacao_final: str`
  - `tokens_input: int`
  - `tokens_output: int`
  - `custo_estimado: Decimal`
- [ ] Criar dataclass `Jurisprudencia` com campos:
  - `ementa: str`
  - `tribunal: str`
  - `numero_processo: str`
  - `data_julgamento: str`
  - `aplicabilidade: str` — `"FAVORAVEL" | "DESFAVORAVEL" | "NEUTRO"`
  - `relevancia_score: float`
- [ ] Criar classe `HarveyClient` com constantes:
  - `MODELO_HARVEY = "harvey-v3"` (confirmar com documentação Harvey)
  - `MAX_TOKENS = 2048`
  - `TIMEOUT = 45` (Harvey mais lento — raciocínio denso)
  - `MAX_RETRIES = 3`
- [ ] Implementar `__init__` com:
  - Leitura de `settings.HARVEY_API_KEY` e `settings.HARVEY_API_URL`
  - Circuit breaker via `pybreaker` (padrão já usado no DataJud)
  - Client HTTP async (`httpx.AsyncClient` com timeout configurável)
- [ ] Implementar método `async gerar_resposta(system_prompt, mensagem_usuario, contexto_rag, escritorio_id) -> HarveyResponse`:
  - Retry com backoff exponencial (3 tentativas)
  - Circuit breaker abre após 3 falhas consecutivas
  - Log estruturado com `structlog` (latência, tokens, custo)
  - Retornar `HarveyResponse` tipado com tokens consumidos + custo
- [ ] Implementar método `async analisar_peticao(conteudo_peticao, tipo_analise, contexto_processo) -> AnaliseHarveyResponse`:
  - Usar endpoint dedicado Harvey para documentos jurídicos (se disponível)
  - Chunking do conteúdo se PDF muito grande (reusar lógica de `ingestion.py`)
  - Parsear resposta para `AnaliseHarveyResponse` estruturado
- [ ] Implementar método `async pesquisar_jurisprudencia(query, tribunal, periodo) -> list[Jurisprudencia]`:
  - Usar base de dados jurídica Harvey
  - Ordenar do mais recente para o mais antigo
  - Parsear para lista de `Jurisprudencia`
- [ ] Implementar fallback: se Harvey indisponível (circuit breaker aberto), levantar `HarveyUnavailableError` para o chamador tratar com Claude

---

### 1.2 — Variáveis de ambiente (`shared/config/settings.py`) — arquivo EXISTENTE

- [ ] Adicionar em `shared/config/settings.py`:
  ```python
  HARVEY_API_KEY: str = ""
  HARVEY_API_URL: str = "https://api.harvey.ai/v1"
  HARVEY_MODELO: str = "harvey-v3"
  HARVEY_TIMEOUT: int = 45
  HARVEY_HABILITADO: bool = False
  ```
- [ ] Adicionar `HARVEY_API_KEY` no `.env.example` com comentário explicativo
- [ ] Documentar no `.env.example` que `HARVEY_HABILITADO=False` por padrão (feature flag global; controle por escritório é via banco)

---

### 1.3 — Feature flag por escritório (`shared/models/escritorio.py`) — arquivo EXISTENTE

- [ ] Adicionar campos ao modelo `Escritorio`:
  ```python
  harvey_habilitado: Mapped[bool] = mapped_column(default=False)
  harvey_canal_advogado_numero: Mapped[str | None] = mapped_column(String(20), nullable=True)
  harvey_quota_tokens_mes: Mapped[int] = mapped_column(default=500_000)
  harvey_tokens_usados_mes: Mapped[int] = mapped_column(default=0)
  harvey_confidence_threshold: Mapped[float] = mapped_column(default=0.70)
  ```
- [ ] `harvey_canal_advogado_numero`: se `None`, usa o mesmo número do cliente distinguindo por role do remetente

---

### 1.4 — Migration Alembic: campos Harvey em `escritorios` — arquivo NOVO

- [ ] Criar `alembic/versions/016_add_harvey_fields_to_escritorios.py`
- [ ] `upgrade()`:
  ```sql
  ALTER TABLE escritorios ADD COLUMN harvey_habilitado BOOLEAN DEFAULT FALSE;
  ALTER TABLE escritorios ADD COLUMN harvey_canal_advogado_numero VARCHAR(20);
  ALTER TABLE escritorios ADD COLUMN harvey_quota_tokens_mes INTEGER DEFAULT 500000;
  ALTER TABLE escritorios ADD COLUMN harvey_tokens_usados_mes INTEGER DEFAULT 0;
  ALTER TABLE escritorios ADD COLUMN harvey_confidence_threshold FLOAT DEFAULT 0.70;
  ```
- [ ] `downgrade()`: `DROP COLUMN` em todos os 5 campos
- [ ] Validar: `alembic upgrade head` + `alembic downgrade -1` passam sem erro

---

### 1.5 — Testes unitários `HarveyClient` — arquivo NOVO

- [ ] Criar `tests/unit/test_harvey_client.py`
- [ ] Teste: `gerar_resposta()` com mock HTTP retorna `HarveyResponse` tipado corretamente
- [ ] Teste: retry dispara em falha HTTP 500 (3 tentativas, depois levanta exceção)
- [ ] Teste: circuit breaker abre após 3 falhas e não tenta nova chamada
- [ ] Teste: `analisar_peticao()` parseia resposta estruturada de análise
- [ ] Teste: `pesquisar_jurisprudencia()` retorna lista de `Jurisprudencia` ordenada por data
- [ ] Teste: `HarveyUnavailableError` é levantado quando circuit breaker está aberto

---

## FASE 2 — Roteador de Confiança (2–3 dias)

> Objetivo: Claude delega automaticamente para Harvey quando confiança na resposta está abaixo do threshold.
> Critério de aceite: pergunta jurídica complexa → score < 0.70 → Harvey responde. Pergunta de status → Claude responde.

---

### 2.1 — `ConfidenceRouter` (`services/ai/confidence_router.py`) — arquivo NOVO

- [ ] Criar arquivo `feature_1_ia_personalizada/services/ai/confidence_router.py`
- [ ] Criar dataclass `ConfidenceScore`:
  ```python
  valor: float                    # 0.0 → 1.0
  componentes: dict               # breakdown por dimensão
  deve_escalar_harvey: bool       # True se valor < threshold
  motivo: str                     # log interno
  ```
- [ ] Criar classe `ConfidenceRouter` com constante `THRESHOLD = 0.70`
- [ ] Implementar método `async avaliar(mensagem, resposta_claude, tipo_intencao, rag_docs, fact_check_result, historico_cliente, escritorio_id) -> ConfidenceScore`
  - **score_cobertura_rag** (peso 35%): `max(similaridade_coseno)` dos docs recuperados; se RAG retornou 0 docs → score = 0.0
  - **score_fact_checker** (peso 25%): reutilizar resultado de `fact_checker.py` diretamente (já existe, sem chamada extra)
  - **score_intencao** (peso 25%): mapeamento determinístico por `tipo_intencao`:
    - `saudacao` → 1.0
    - `status_processo` → 0.90
    - `reclamacao` → 0.75
    - `pergunta_juridica` → 0.45
    - `perspectiva_caso` → 0.30
  - **score_historico_cliente** (peso 15%): razão entre respostas com NPS ≥ 4 nas últimas 20 interações do cliente
  - Fórmula: `0.35 × rag + 0.25 × fact + 0.25 × intencao + 0.15 × historico`
  - Condições de roteamento forçado para Harvey (score ignorado):
    - `tipo_intencao == "jurídica_complexa"` → sempre Harvey
    - `fact_check_result["hallucination_score"] > 0.30` → Harvey
    - Número de tentativas de geração > 1 → Harvey
    - Mensagem contém termos: "CPC art", "STJ", "STF", "Súmula", "CLT art" → Harvey
- [ ] Implementar método `async rotear(state, score) -> str`:
  - Retorna `"claude"` ou `"harvey"`
  - Verificar `escritorio.harvey_habilitado` antes de rotear para Harvey
  - Verificar quota: se `harvey_tokens_usados_mes >= harvey_quota_tokens_mes` → forçar `"claude"` com log de aviso
  - Usar `escritorio.harvey_confidence_threshold` em vez do `THRESHOLD` fixo (ajustável por escritório)

---

### 2.2 — Campo `modelo_ia` em `Interacao` (`shared/models/interacao.py`) — arquivo EXISTENTE

- [ ] Adicionar campo ao modelo `Interacao`:
  ```python
  modelo_ia: Mapped[str] = mapped_column(String(50), server_default="claude")
  # Valores: 'claude', 'harvey', 'claude_harvey_fallback'
  ```

---

### 2.3 — Migration Alembic: `modelo_ia` em `interacoes` — arquivo NOVO

- [ ] Criar `alembic/versions/017_add_modelo_ia_to_interacoes.py`
- [ ] `upgrade()`:
  ```sql
  ALTER TABLE interacoes ADD COLUMN modelo_ia VARCHAR(50) DEFAULT 'claude';
  ```
- [ ] `downgrade()`: `DROP COLUMN modelo_ia`
- [ ] Validar: `alembic upgrade head` + `alembic downgrade -1` passam

---

### 2.4 — Dois novos nós no LangGraph Orchestrator (`services/ai/orchestrator.py`) — arquivo EXISTENTE

- [ ] Adicionar nó `avaliar_confianca` no grafo LangGraph entre `gerar_resposta` e `verificar_resposta`:
  - Instanciar `ConfidenceRouter`
  - Chamar `confidence_router.avaliar(...)` com dados já presentes no `state`
  - Guardar `ConfidenceScore` no `ConversationState`
  - Retornar edge condicional: `score.valor >= threshold` → `"verificar_resposta"`, senão → `"gerar_resposta_harvey"`
- [ ] Adicionar nó `gerar_resposta_harvey`:
  - Chamar `HarveyClient.gerar_resposta()` com o mesmo contexto RAG + system prompt
  - Em caso de `HarveyUnavailableError` (circuit breaker): fallback para resposta Claude existente no state, setar `modelo_ia = "claude_harvey_fallback"`, logar aviso
  - Setar `modelo_ia = "harvey"` no state
  - Atualizar `harvey_tokens_usados_mes` no escritório (incrementar atomicamente)
  - Continuar para `verificar_resposta` → `enviar_resposta` (caminho normal)
- [ ] Adicionar verificações de feature flag no orchestrator:
  ```python
  if not escritorio.harvey_habilitado:
      # Pular nó avaliar_confianca, ir direto para verificar_resposta
  if escritorio.harvey_tokens_usados_mes >= escritorio.harvey_quota_tokens_mes:
      # Logar harvey_quota_esgotada e forçar Claude
  ```
- [ ] Grafo final resultante:
  ```
  classificar_intencao → buscar_dados → gerar_resposta(Claude)
    → [NOVO] avaliar_confianca
      → score≥threshold: verificar_resposta → enviar_resposta
      → score<threshold: [NOVO] gerar_resposta_harvey → verificar_resposta → enviar_resposta
  ```

---

### 2.5 — Prompts Harvey para canal do cliente (`services/ai/prompts.py`) — arquivo EXISTENTE

- [ ] Adicionar seção `# === PROMPTS HARVEY — CANAL DO CLIENTE ===`
- [ ] Criar `SYSTEM_PROMPT_HARVEY_CLIENTE_BASE`:
  - Tom técnico-jurídico mas ainda acessível ao cliente leigo
  - Escritório: `{nome_escritorio}`, Persona IA: `{nome_ia}`
  - Restrições: nunca prever resultado, nunca dar conselho jurídico, nunca citar OAB como barreira
  - Contexto RAG injetado: `{contexto_documentos}`
- [ ] Criar `SYSTEM_PROMPT_HARVEY_PERGUNTA_JURIDICA`:
  - Responde com precisão técnica mas linguagem acessível
  - Citar artigos de lei e súmulas apenas quando tiver alta certeza
  - Redirecionar para o advogado responsável ao final da resposta

---

### 2.6 — Métricas Harvey em `api/routes/metrics.py` — arquivo EXISTENTE

- [ ] Adicionar contadores Prometheus:
  - `harvey_requests_total` — counter com labels `escritorio_id`, `resultado` (`"sucesso"`, `"fallback_claude"`, `"circuit_breaker"`)
  - `harvey_roteamentos_total` — counter de quantas msgs de cliente foram roteadas para Harvey
  - `harvey_tokens_total` — counter de tokens Harvey consumidos por escritório
  - `harvey_latencia_segundos` — histogram de latência das chamadas Harvey
- [ ] Expor métricas no endpoint `/metrics` (Prometheus scrape)

---

### 2.7 — Testes de integração do Roteador — arquivo NOVO

- [ ] Criar `tests/integration/test_confidence_router.py`
- [ ] Teste: `tipo_intencao="status_processo"` → score ≥ 0.90 → Claude responde
- [ ] Teste: `tipo_intencao="perspectiva_caso"` → score ≤ 0.30 → Harvey roteado
- [ ] Teste: mensagem com "STJ" explícito → forçar Harvey independente de score
- [ ] Teste: `fact_check_result["hallucination_score"] = 0.40` → forçar Harvey
- [ ] Teste: `harvey_habilitado=False` → score ignorado, Claude sempre responde
- [ ] Teste: quota Harvey esgotada → fallback Claude com log de aviso
- [ ] Teste end-to-end (mock Harvey): mensagem jurídica complexa entra no orchestrator → Harvey responde → `modelo_ia="harvey"` gravado na `Interacao`

---

## FASE 3 — Hub do Advogado via WhatsApp (3–4 dias)

> Objetivo: Advogado consegue fazer perguntas jurídicas via WhatsApp e receber respostas Harvey em < 30s.
> Critério de aceite: Advogado envia "Dúvida sobre CPC art. 485" → Harvey responde via WhatsApp em < 30 segundos.

---

### 3.1 — Roteamento por role no Webhook (`api/routes/webhook_whatsapp.py`) — arquivo EXISTENTE

- [ ] Dentro do handler de `messages.upsert`, antes do fluxo existente do cliente, adicionar lógica:
  ```python
  usuario = await db.query(Usuario).filter(
      Usuario.whatsapp_numero == telefone_remetente,
      Usuario.escritorio_id == escritorio_id,
      Usuario.role.in_(["advogado", "admin"]),
      Usuario.ativo == True,
  ).first()

  if usuario:
      processar_mensagem_advogado.apply_async(
          args=[payload_dict, usuario.id],
          queue="hub_advogado"
      )
  else:
      processar_mensagem_recebida.apply_async(...)  # fluxo existente inalterado
  ```
- [ ] Verificar que o fluxo existente do cliente **não é alterado** — apenas adiciona `if/else`
- [ ] Verificar que `Usuario.whatsapp_numero` existe no modelo (adicionar campo se não existir — ver 3.2)

---

### 3.2 — Campo `whatsapp_numero` em `Usuario` (se não existir) — arquivo EXISTENTE

- [ ] Verificar se `shared/models/usuario.py` já tem `whatsapp_numero`
- [ ] Se não existir: adicionar `whatsapp_numero: Mapped[str | None] = mapped_column(String(20), nullable=True)`
- [ ] Se campo não existir: criar migration `018_add_whatsapp_numero_to_usuarios.py`

---

### 3.3 — Modelo `SessaoAdvogado` (`shared/models/sessao_advogado.py`) — arquivo NOVO

- [ ] Criar arquivo `shared/models/sessao_advogado.py`
- [ ] Criar modelo `SessaoAdvogado(Base, TimestampMixin, TenantMixin)`:
  ```python
  __tablename__ = "sessoes_advogado"

  id: Mapped[int] = mapped_column(primary_key=True)
  usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), nullable=False)
  mensagem_advogado: Mapped[str] = mapped_column(Text)
  resposta_hub: Mapped[str] = mapped_column(Text)
  intencao: Mapped[str] = mapped_column(String(50))
  modelo_ia: Mapped[str] = mapped_column(String(50))  # 'harvey', 'claude', 'harvey_claude'
  tokens_input: Mapped[int] = mapped_column(default=0)
  tokens_output: Mapped[int] = mapped_column(default=0)
  custo_estimado: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=0)
  cliente_referenciado_id: Mapped[int | None] = mapped_column(ForeignKey("clientes.id"), nullable=True)
  processo_referenciado_id: Mapped[int | None] = mapped_column(ForeignKey("processos.id"), nullable=True)
  metadata_json: Mapped[dict] = mapped_column(JSONB, default={})
  ```
- [ ] Exportar `SessaoAdvogado` em `shared/models/__init__.py`

---

### 3.4 — Migration Alembic: `sessoes_advogado` — arquivo NOVO

- [ ] Criar `alembic/versions/019_add_sessoes_advogado.py`
- [ ] `upgrade()`: `CREATE TABLE sessoes_advogado` com todos os campos + FKs + índices:
  ```sql
  CREATE INDEX ix_sessoes_advogado_usuario ON sessoes_advogado (usuario_id, escritorio_id);
  CREATE INDEX ix_sessoes_advogado_created ON sessoes_advogado (created_at DESC);
  ```
- [ ] `downgrade()`: `DROP TABLE sessoes_advogado`
- [ ] Validar: `alembic upgrade head` + `alembic downgrade -1`

---

### 3.5 — Classificador de intenção do advogado (`services/ai/hub_advogado_classifier.py`) — arquivo NOVO

- [ ] Criar arquivo `feature_1_ia_personalizada/services/ai/hub_advogado_classifier.py`
- [ ] Criar enum `IntencaoAdvogado`:
  - `RESUMO_PROCESSO = "resumo_processo"`
  - `ANALISE_PETICAO = "analise_peticao"` (detectado por presença de documento PDF)
  - `PESQUISA_JURISPRUDENCIA = "pesquisa_jurisprudencia"`
  - `INSIGHT_CLIENTE = "insight_cliente"`
  - `DUVIDA_JURIDICA = "duvida_juridica"`
  - `STATUS_ESCRITORIO = "status_escritorio"`
  - `RASCUNHO_MENSAGEM = "rascunho_mensagem"`
- [ ] Criar classe `HubAdvogadoClassificador`
- [ ] Implementar `async classificar(mensagem, tipo_media) -> IntencaoAdvogado`:
  - Se `tipo_media == "document"` → retornar `ANALISE_PETICAO` diretamente (sem Claude)
  - Se mensagem contiver "status", "dashboard" → `STATUS_ESCRITORIO` (heurística rápida, sem Claude)
  - Caso contrário: chamar Claude Haiku com prompt de classificação (rápido, barato)
  - Timeout 5s — se exceder: fallback para `DUVIDA_JURIDICA`
- [ ] Criar `SYSTEM_PROMPT_CLASSIFICADOR_ADVOGADO` em `prompts.py`:
  - Input: mensagem do advogado
  - Output JSON: `{"intencao": "<valor>", "entidades": {"cliente_nome": ..., "processo_cnj": ..., "query_juris": ...}}`
  - Classificar nas 7 intenções suportadas

---

### 3.6 — Task Celery do Hub (`workers/hub_advogado.py`) — arquivo NOVO

- [ ] Criar arquivo `feature_1_ia_personalizada/workers/hub_advogado.py`
- [ ] Criar task `processar_mensagem_advogado`:
  ```python
  @celery_app.task(
      name="processar_mensagem_advogado",
      queue="hub_advogado",
      max_retries=3,
      default_retry_delay=5,
      soft_time_limit=120,
      time_limit=150,
  )
  ```
- [ ] Fluxo da task:
  1. Buscar `Usuario` pelo `usuario_id` (validar que ainda é ativo e tem role advogado/admin)
  2. Verificar que `escritorio.harvey_habilitado` é True (se False: responder "Hub não ativo para este escritório")
  3. Extrair texto/tipo de mídia do payload Evolution API
  4. Chamar `HubAdvogadoClassificador.classificar()` → `IntencaoAdvogado`
  5. Despachar para handler correto:
     - `ANALISE_PETICAO` → `_handler_analise_peticao()`
     - `RESUMO_PROCESSO` → `_handler_resumo_processo()`
     - `INSIGHT_CLIENTE` → `_handler_insight_cliente()`
     - `PESQUISA_JURISPRUDENCIA` → `_handler_pesquisa_jurisprudencia()`
     - `STATUS_ESCRITORIO` → `_handler_status_escritorio()`
     - `RASCUNHO_MENSAGEM` → `_handler_rascunho_mensagem()`
     - `DUVIDA_JURIDICA` (default) → `_handler_duvida_juridica()`
  6. Formatar resposta para WhatsApp (markdown: `*negrito*`, `_itálico_`)
  7. Enviar resposta via `WhatsAppService.enviar()` para o número do advogado
  8. Salvar `SessaoAdvogado` no banco com tokens + custo + intenção + modelo_ia
  9. Incrementar `harvey_tokens_usados_mes` no `Escritorio`
- [ ] Implementar `_handler_duvida_juridica(mensagem, usuario, escritorio, db)`:
  - Montar contexto: últimas 5 sessões do advogado (memória conversacional)
  - Buscar RAG docs relevantes do escritório
  - Chamar `HarveyClient.gerar_resposta()` com `SYSTEM_PROMPT_HUB_ADVOGADO_BASE`
  - Fallback: se Harvey indisponível → Claude com aviso explícito na resposta
- [ ] Implementar `_handler_status_escritorio(usuario, escritorio, db)`:
  - Agregar: total de atendimentos hoje, processos com prazo próximo (próximos 7 dias), leads novos, NPS médio do mês
  - Formatar como dashboard WhatsApp sem chamar Harvey (dados estruturados)
- [ ] Implementar `_handler_rascunho_mensagem(mensagem, usuario, escritorio, db)`:
  - Identificar cliente alvo na mensagem (nome ou ID)
  - Buscar dados CRM do cliente
  - Chamar Harvey para gerar rascunho de mensagem empática e profissional
  - Retornar rascunho para o advogado revisar e enviar manualmente

---

### 3.7 — Fila Celery `hub_advogado` (`workers/celery_app.py`) — arquivo EXISTENTE

- [ ] Adicionar ao `CELERY_TASK_ROUTES`:
  ```python
  "feature_1_ia_personalizada.workers.hub_advogado.*": {"queue": "hub_advogado"},
  ```
- [ ] Adicionar `hub_advogado` à lista de queues no comando de inicialização do worker:
  ```
  celery -A ... worker -Q monitoramento,notificacoes,ia,relacionamento,hub_advogado
  ```
- [ ] Atualizar `infrastructure/docker/docker-compose.yml` para incluir `hub_advogado` nas queues do container worker
- [ ] Atualizar `railway.worker.json` para incluir a nova fila na configuração de produção

---

### 3.8 — Prompts do Hub do Advogado (`services/ai/prompts.py`) — arquivo EXISTENTE

- [ ] Adicionar seção `# === PROMPTS DO HUB DO ADVOGADO ===` ao final do arquivo
- [ ] Criar `SYSTEM_PROMPT_HUB_ADVOGADO_BASE`:
  - Input: `{nome_escritorio}`, `{nome_usuario}`, `{oab}`
  - Tom técnico-jurídico (interlocutor é profissional jurídico)
  - Citar artigos de lei, súmulas e jurisprudências com precisão
  - Não usar linguagem simplificada; ser objetivo e denso
- [ ] Criar `SYSTEM_PROMPT_ANALISE_PETICAO`:
  - Estrutura obrigatória da análise: IDENTIFICAÇÃO → PONTOS FORTES → VULNERABILIDADES → JURISPRUDÊNCIA RELEVANTE → SUGESTÕES → AVALIAÇÃO GERAL (score 0-100)
  - Input: `{data_hoje}` para referência de direito vigente
- [ ] Criar `SYSTEM_PROMPT_PESQUISA_JURISPRUDENCIA`:
  - Input: `{query}`, `{tribunais}`, `{periodo}`
  - Output obrigatório: ementa (2-3 linhas), data + tribunal + número, aplicabilidade (FAVORÁVEL/DESFAVORÁVEL/NEUTRO), tendência atual
  - Ordenar do mais recente para o mais antigo
- [ ] Criar `SYSTEM_PROMPT_INSIGHT_CLIENTE`:
  - Input: `{nome_cliente}`, `{crm_score}`, `{resumo_interacoes}`, `{resumo_processos}`, `{ultima_acao_crm}`
  - Output obrigatório: situação atual (3-4 linhas), pontos de atenção imediata, próxima ação recomendada (específica e acionável), risco de abandono (BAIXO/MÉDIO/ALTO)
- [ ] Criar `SYSTEM_PROMPT_CLASSIFICADOR_ADVOGADO` (para `HubAdvogadoClassificador`)

---

### 3.9 — Testes unitários do Hub do Advogado — arquivo NOVO

- [ ] Criar `tests/unit/test_hub_advogado.py`
- [ ] Teste: `HubAdvogadoClassificador` classifica "Resumo do processo 123" → `RESUMO_PROCESSO`
- [ ] Teste: payload com `type="document"` → `ANALISE_PETICAO` sem chamar Claude
- [ ] Teste: "Status" ou "Dashboard" → `STATUS_ESCRITORIO` (heurística, sem Claude)
- [ ] Teste: remetente não é advogado → task retorna sem processar (não envia mensagem)
- [ ] Teste: `harvey_habilitado=False` → resposta de hub não ativo enviada
- [ ] Teste: Harvey indisponível → fallback Claude com aviso na resposta
- [ ] Teste: `SessaoAdvogado` é salva com campos corretos após processamento

---

## FASE 4 — Análise de Petições PDF (2–3 dias)

> Objetivo: Advogado envia PDF no WhatsApp → Harvey analisa e responde com insights estruturados.
> Critério de aceite: Advogado envia PDF de petição → recebe análise estruturada em < 60 segundos.

---

### 4.1 — Handler de análise de petição na task Celery (`workers/hub_advogado.py`) — arquivo EXISTENTE (Fase 3)

- [ ] Implementar `_handler_analise_peticao(payload, usuario, escritorio, db)`:
  1. Baixar PDF via `evolution_client.download_media()` (já existe para áudios — reutilizar)
  2. Extrair texto via `DocumentoIngester._extrair_texto_pdf()` (já em `ingestion.py`)
  3. Limpar artefatos OCR via `data_cleaner.py` (já existe)
  4. Se PDF muito grande: chunking antes de enviar (reutilizar lógica de `ingestion.py`)
  5. Enviar mensagem imediata de confirmação "Analisando petição... aguarde até 60 segundos" ao advogado
  6. Chamar `HarveyClient.analisar_peticao(conteudo, TipoAnaliseHarvey.ANALISE_COMPLETA, contexto_processo)`
  7. Formatar `AnaliseHarveyResponse` em markdown WhatsApp estruturado:
     - `*IDENTIFICAÇÃO*`, `*PONTOS FORTES*`, `*VULNERABILIDADES*`, `*JURISPRUDÊNCIA*`, `*SUGESTÕES*`, `*AVALIAÇÃO: X/100*`
  8. Enviar resposta formatada
  9. Salvar `SessaoAdvogado` com `intencao="analise_peticao"`, `modelo_ia="harvey"`

---

### 4.2 — Endpoint REST de análise de petição (`api/routes/hub_advogado.py`) — arquivo NOVO (parcial)

- [ ] Criar arquivo `feature_1_ia_personalizada/api/routes/hub_advogado.py`
- [ ] Criar `POST /api/v1/hub/analisar-peticao`:
  - Body: `FormData` com campo `arquivo` (PDF)
  - Validação: tipo MIME deve ser `application/pdf`
  - Tamanho máximo: 10MB (configurável)
  - Role: `advogado`, `admin`
  - Chamar `HarveyClient.analisar_peticao()` diretamente (sem WhatsApp)
  - Retornar `AnaliseHarveyResponse` como JSON
  - Salvar `SessaoAdvogado`
- [ ] Criar `POST /api/v1/hub/consultar`:
  - Body: `{ pergunta: str, cliente_id?: int, processo_id?: int }`
  - Role: `advogado`, `admin`
  - Montar contexto com dados do cliente/processo se fornecidos
  - Chamar `HarveyClient.gerar_resposta()` diretamente (sem WhatsApp)
  - Retornar resposta Harvey como JSON
  - Salvar `SessaoAdvogado`
- [ ] Registrar router em `feature_1_ia_personalizada/api/app.py`:
  ```python
  app.include_router(hub_advogado_router, prefix="/api/v1/hub", tags=["Hub do Advogado"])
  ```

---

### 4.3 — Testes de integração de análise de petição — arquivo NOVO

- [ ] Criar `tests/integration/test_analise_peticao.py`
- [ ] Teste: upload PDF → `HarveyClient.analisar_peticao()` chamado com texto extraído (mock Harvey)
- [ ] Teste: PDF inválido (não-PDF) → HTTP 422
- [ ] Teste: PDF muito grande → chunking aplicado antes de chamar Harvey
- [ ] Teste: `POST /hub/analisar-peticao` com role `cliente` → HTTP 403
- [ ] Teste: `POST /hub/consultar` retorna resposta Harvey + salva `SessaoAdvogado`

---

## FASE 5 — Resumos de Processos e Insights CRM (2 dias)

> Objetivo: Harvey cruza dados jurídicos + CRM para insights acionáveis ao advogado.
> Critério de aceite: "Me dá um resumo do João Silva" → Harvey retorna resumo com dados reais + recomendação CRM.

---

### 5.1 — Handler de resumo de processo (`workers/hub_advogado.py`) — arquivo EXISTENTE (Fase 3)

- [ ] Implementar `_handler_resumo_processo(mensagem, usuario, escritorio, db)`:
  1. Extrair identificador: nome do cliente OU número CNJ do processo (via entidades do classificador)
  2. Buscar processo no banco via `worker_queries.py` (já existe — reutilizar)
  3. Buscar últimas movimentações via Jusbrasil (`jusbrasil_client.py`) + DataJud (`datajud_client.py`)
  4. Buscar documentos RAG do processo (petições, contestações já ingeridas)
  5. Buscar dados CRM do cliente (score, histórico de NPS)
  6. Montar contexto completo para Harvey
  7. Chamar `HarveyClient.gerar_resposta()` com `SYSTEM_PROMPT_HUB_ADVOGADO_BASE` + dados estruturados
  8. Formatar resposta no padrão definido na seção 7 da doc (📋 com processo, cliente, movimentações, análise Harvey, score de risco, próxima audiência)
  9. Salvar `SessaoAdvogado` com `processo_referenciado_id`

---

### 5.2 — Handler de insight de cliente (`workers/hub_advogado.py`) — arquivo EXISTENTE (Fase 3)

- [ ] Implementar `_handler_insight_cliente(mensagem, usuario, escritorio, db)`:
  1. Extrair nome do cliente da mensagem (via entidades do classificador)
  2. Buscar cliente no banco (fuzzy match por nome se necessário)
  3. Buscar CRM score via `crm/aggregator.py` (já existe — reutilizar)
  4. Buscar histórico de interações relevantes via `crm/analyzer.py` (já existe — reutilizar)
  5. Buscar processos ativos do cliente
  6. Montar contexto com `SYSTEM_PROMPT_INSIGHT_CLIENTE`
  7. Chamar `HarveyClient.gerar_resposta()`
  8. Formatar resposta: situação atual + pontos de atenção + próxima ação + risco de abandono
  9. Salvar `SessaoAdvogado` com `cliente_referenciado_id`

---

### 5.3 — Endpoints REST de histórico (`api/routes/hub_advogado.py`) — arquivo EXISTENTE (Fase 4)

- [ ] Criar `GET /api/v1/hub/historico?page=1&limit=25`:
  - Query `SessaoAdvogado` filtrado por `usuario_id` do JWT autenticado
  - Paginação com `page` e `limit`
  - Role: `advogado`, `admin`
  - Retornar lista com `id`, `intencao`, `modelo_ia`, `created_at`, preview da mensagem (100 chars)
- [ ] Criar `GET /api/v1/hub/historico/{sessao_id}`:
  - Buscar `SessaoAdvogado` por ID
  - Validar que `escritorio_id` bate com o do usuário autenticado (isolamento multi-tenant)
  - Retornar sessão completa
- [ ] Criar `GET /api/v1/hub/metricas`:
  - Role: `admin`
  - Agregar `SessaoAdvogado` por `escritorio_id`: tokens consumidos total, custo total, intenções mais usadas (TOP 5), advogados mais ativos
  - Retornar JSON com período `mes_atual`

---

### 5.4 — Schemas Pydantic para Hub (`shared/schemas/`) — arquivo NOVO

- [ ] Criar `shared/schemas/hub_advogado.py`
- [ ] Criar `ConsultaHubRequest`:
  ```python
  pergunta: str
  cliente_id: int | None = None
  processo_id: int | None = None
  ```
- [ ] Criar `SessaoAdvogadoResponse`:
  ```python
  id: int
  intencao: str
  mensagem_advogado: str
  resposta_hub: str
  modelo_ia: str
  tokens_input: int
  tokens_output: int
  custo_estimado: Decimal
  cliente_referenciado_id: int | None
  processo_referenciado_id: int | None
  created_at: datetime
  ```
- [ ] Criar `SessaoAdvogadoListItem` (versão reduzida para listagem)
- [ ] Criar `MetricasHubResponse`
- [ ] Exportar em `shared/schemas/__init__.py`

---

### 5.5 — Testes de integração de resumos e insights — arquivo NOVO

- [ ] Criar `tests/integration/test_hub_resumos_insights.py`
- [ ] Teste: "Resumo do processo 0001234-55.2023.8.26.0001" → Harvey recebe dados reais do banco (mock Harvey)
- [ ] Teste: "Insight da cliente Maria" → CRM `aggregator.py` chamado + Harvey gera recomendação
- [ ] Teste: `GET /hub/historico` retorna apenas sessões do usuário autenticado (isolamento)
- [ ] Teste: `GET /hub/historico/{id}` de outro escritório → HTTP 403
- [ ] Teste: `GET /hub/metricas` com role `advogado` → HTTP 403; com role `admin` → HTTP 200

---

## Arquivos a Criar (Resumo Completo)

```
NOVOS ARQUIVOS:
feature_1_ia_personalizada/
├── services/
│   └── ai/
│       ├── harvey_client.py              # Fase 1 — Cliente Harvey AI
│       ├── confidence_router.py          # Fase 2 — Roteador de Confiança
│       └── hub_advogado_classifier.py    # Fase 3 — Classificador de Intenção
├── workers/
│   └── hub_advogado.py                   # Fase 3 — Task Celery do Hub
└── api/
    └── routes/
        └── hub_advogado.py               # Fase 4 — Endpoints REST

shared/
├── models/
│   └── sessao_advogado.py                # Fase 3 — Histórico de Sessões
└── schemas/
    └── hub_advogado.py                   # Fase 5 — Schemas Pydantic

alembic/versions/
├── 016_add_harvey_fields_to_escritorios.py    # Fase 1
├── 017_add_modelo_ia_to_interacoes.py         # Fase 2
├── 018_add_whatsapp_numero_to_usuarios.py     # Fase 3 (se necessário)
└── 019_add_sessoes_advogado.py                # Fase 3

tests/
├── unit/
│   ├── test_harvey_client.py             # Fase 1
│   ├── test_confidence_router.py         # Fase 2 (unit)
│   └── test_hub_advogado.py              # Fase 3
└── integration/
    ├── test_confidence_router.py         # Fase 2
    ├── test_analise_peticao.py           # Fase 4
    └── test_hub_resumos_insights.py      # Fase 5
```

## Arquivos Existentes a Modificar (Resumo Completo)

```
shared/config/settings.py             → +5 vars Harvey (Fase 1)
shared/models/escritorio.py           → +5 campos Harvey (Fase 1)
shared/models/interacao.py            → +campo modelo_ia (Fase 2)
shared/models/usuario.py              → +whatsapp_numero se ausente (Fase 3)
shared/models/__init__.py             → +export SessaoAdvogado (Fase 3)
shared/schemas/__init__.py            → +exports hub_advogado.py (Fase 5)
.env.example                          → +HARVEY_* vars (Fase 1)

feature_1_ia_personalizada/
├── services/ai/
│   ├── orchestrator.py               → +2 nós LangGraph + verificações quota (Fase 2)
│   └── prompts.py                    → +6 prompts Harvey/Hub (Fases 2, 3)
├── workers/celery_app.py             → +fila hub_advogado (Fase 3)
└── api/
    ├── app.py                        → +include_router hub_advogado (Fase 4)
    ├── routes/webhook_whatsapp.py    → +roteamento por role (Fase 3)
    └── routes/metrics.py             → +métricas Harvey Prometheus (Fase 2)

infrastructure/docker/docker-compose.yml  → +hub_advogado na fila do worker (Fase 3)
railway.worker.json                        → +hub_advogado na fila de produção (Fase 3)
```

---

## Ordem de Implementação

```
PRÉ-REQUISITO: Confirmar API Harvey (seção acima)
  ↓
FASE 1: Fundação Harvey (sem impacto no código existente)
  1.2 (settings) → 1.3 (modelo) → 1.4 (migration) → 1.1 (HarveyClient) → 1.5 (testes)
  ↓
FASE 2: Roteador de Confiança
  2.3 (migration interacao) → 2.2 (modelo interacao) → 2.1 (ConfidenceRouter)
    → paralelo: 2.5 (prompts) + 2.6 (métricas)
  → 2.4 (orchestrator — 2 nós) → 2.7 (testes integração)
  ↓
FASE 3: Hub do Advogado via WhatsApp
  3.3 (modelo SessaoAdvogado) → 3.4 (migration) → 3.2 (usuario.whatsapp_numero)
    → paralelo: 3.5 (classificador) + 3.8 (prompts) + 3.7 (celery fila)
  → 3.6 (task hub_advogado) → 3.1 (webhook roteamento) → 3.9 (testes)
  ↓
FASE 4: Análise de Petições
  4.1 (handler PDF na task) → 4.2 (endpoints REST) → 4.3 (testes)
  ↓
FASE 5: Resumos e Insights CRM
  5.4 (schemas) → 5.1 (handler resumo) → 5.2 (handler insight) → 5.3 (endpoints histórico) → 5.5 (testes)
```

---

## Critérios de Aceite Globais

| Fase | Critério |
|------|----------|
| Fase 1 | `HarveyClient.gerar_resposta()` retorna resposta válida em teste de integração |
| Fase 2 | Pergunta jurídica complexa → score < 0.70 → Harvey responde; pergunta de status → Claude responde |
| Fase 3 | Advogado envia "CPC art. 485" → Harvey responde via WhatsApp em < 30s |
| Fase 4 | Advogado envia PDF → análise estruturada em < 60s |
| Fase 5 | "Resumo do João Silva" → Harvey retorna com dados reais do banco + recomendação CRM |
| Global | Todos os fluxos do cliente existentes continuam 100% inalterados (sem regressão) |
| Global | `harvey_habilitado=False` → zero impacto no desempenho ou comportamento do cliente |
| Global | Harvey indisponível → fallback para Claude sem erro visível ao usuário |
| Global | Cobertura de testes ≥ 70% nos arquivos novos (CI não quebra) |
