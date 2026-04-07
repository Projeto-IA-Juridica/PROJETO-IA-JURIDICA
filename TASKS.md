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

# TASKS — Feature Hub do Advogado (Claude Opus — ex-Harvey)

> **Conceito:** Ecossistema de IA dual — cliente usa Claude (fluido), advogado usa Claude Opus (raciocínio jurídico pesado) via WhatsApp dedicado. Um Roteador de Confiança decide quando Claude delega para Claude Opus no fluxo do cliente.
> **Nota:** Harvey AI foi substituído por Claude Opus (`claude-opus-4-6`) como modelo de escalação. Todos os campos e configs renomeados de `harvey_*` para `escalacao_*`.
> **Acesso:** Hub do Advogado restrito a `advogado` e `admin`. Roteador opera transparentemente no fluxo do cliente.
> **Referência:** [docs/FEATURE_HARVEY_HUB_ADVOGADO.md](docs/FEATURE_HARVEY_HUB_ADVOGADO.md)

---

## Status Geral

| Fase | Descrição | Status |
|------|-----------|--------|
| Fase 1 | Fundação (client + settings + feature flag) | ✅ Concluída |
| Fase 2 | Roteador de Confiança Claude → Claude Opus | ✅ Concluída |
| Fase 3 | Hub do Advogado via WhatsApp | ✅ Concluída |
| Fase 4 | Análise de Petições (PDF → Claude Opus) | ✅ Concluída |
| Fase 5 | Resumo de Processos e Insights CRM | 🔄 Em andamento |

---

## Auditoria de Viabilidade (02/04/2026)

> Resultado de auditoria contra o código real do projeto. Referência para evitar surpresas durante a implementação.

### O que JÁ EXISTE e pode ser reutilizado

| Componente | Arquivo real | Como reutilizar |
|---|---|---|
| `baixar_media(instance, message_id)` | `services/messaging/evolution_client.py:240` | Download de PDFs do WhatsApp (Fase 4) — **método é `baixar_media`, não `download_media`** |
| `_extrair_texto_pdf()` | `services/rag/ingestion.py` | Extração de texto de petições (Fase 4) |
| `CRMDataAggregator.coletar_contexto_cliente()` | `services/crm/aggregator.py:96` | Contexto CRM para insights (Fase 5) |
| `CRMAnalyzer.analisar_cliente()` | `services/crm/analyzer.py:88` | Score e recomendação CRM (Fase 5) |
| `FactChecker` — retorna `dict` | `services/ai/fact_checker.py` | Convertido para float em `ConfidenceRouter` (Fase 2) |
| `whatsapp_numero` em `Usuario` | `shared/models/usuario.py:65` | **Já existe** — migration `20260317_*` já aplicada |
| Routing de escalação no webhook | `api/routes/webhook_whatsapp.py:191` | Base para adicionar ramo do Hub (Fase 3) |
| LangGraph com 8 nós | `services/ai/orchestrator.py:695` | +2 nós Harvey sem refatorar grafo existente |
| `ConversationState` TypedDict | `orchestrator.py:199` | +2 campos: `confidence_score`, `modelo_ia_usado` |
| Filas Celery (4 existentes) | `workers/celery_app.py:67` | +1 fila `hub_advogado` |
| Circuit breaker `pybreaker` | já importado no projeto | `HarveyClient` usa o mesmo padrão do DataJud |

### Divergências corrigidas neste TASKS vs. doc original

| Seção | Problema na doc original | Correção aplicada |
|---|---|---|
| 3.1 | Pseudocódigo de webhook ignorava a lógica de escalação existente | Correto: Hub é terceiro ramo, após escalação |
| 3.2 | Dizia "verificar se whatsapp_numero existe" | Campo já existe; seção marcada como ✅ JÁ FEITO |
| 4.1 | `evolution_client.download_media()` | Método real: `baixar_media(instance, message_id)` |
| 1.4/2.3/3.4 | Migrations com formato `016_*`, `017_*`, `019_*` | Projeto usa formato date-based (`20260402_HHMM_HASH_*`) |
| 2.1 | "reutilizar resultado do fact_checker diretamente" (como se fosse float) | `fact_checker` retorna `dict`; conversão para float documentada |
| 2.4 | ConversationState não mencionava novos campos | Adicionados: `confidence_score` e `modelo_ia_usado` |

### Nenhum bloqueador técnico identificado

Toda a infraestrutura necessária existe: LangGraph extensível, Evolution API pronta, Celery com padrão de filas, CRM reutilizável, multi-tenant isolado. A feature é **100% aditiva** — nenhum código existente precisa ser refatorado.

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

## FASE 1 — Fundação (Claude Opus como escalação) ✅ CONCLUÍDA

> Harvey substituído por `claude-opus-4-6` via SDK Anthropic. Campos renomeados de `harvey_*` para `escalacao_*`.

---

### 1.1 — `EscalationClient` (`services/ai/escalation_client.py`) ✅ FEITO

- [x] Criar arquivo `feature_1_ia_personalizada/services/ai/escalation_client.py`
- [x] Criar enum `TipoAnalise` (ex-`TipoAnaliseHarvey`)
- [x] Criar dataclass `EscalacaoResponse` (ex-`HarveyResponse`)
- [x] Criar dataclass `AnaliseEscalacaoResponse` (ex-`AnaliseHarveyResponse`)
- [x] Criar dataclass `Jurisprudencia`
- [x] Criar classe `EscalationClient` usando SDK Anthropic com `claude-opus-4-6`
- [x] Implementar retry + backoff + circuit breaker
- [x] Implementar `gerar_resposta`, `analisar_peticao`, `pesquisar_jurisprudencia`
- [x] Implementar fallback com `EscalacaoUnavailableError`

---

### 1.2 — Variáveis de ambiente (`shared/config/settings.py`) ✅ FEITO

- [x] Adicionado `MODELO_ESCALACAO: str = "claude-opus-4-6"`
- [x] Adicionado `ESCALACAO_HABILITADO: bool = False`

---

### 1.3 — Feature flag por escritório (`shared/models/escritorio.py`) ✅ FEITO

- [x] Campos adicionados como `escalacao_habilitada`, `escalacao_canal_advogado_numero`, `escalacao_quota_tokens_mes`, `escalacao_tokens_usados_mes`, `escalacao_confidence_threshold`

---

### 1.4 — Migration Alembic: campos escalação em `escritorios` ✅ FEITO

- [x] `alembic/versions/20260404_1000_a1b2c3d4e5f6_add_harvey_fields_to_escritorios.py` criada

---

### 1.5 — Testes unitários `EscalationClient` ✅ FEITO

- [x] `tests/unit/test_escalation_client.py` criado (ex-`test_harvey_client.py`)

---

## FASE 2 — Roteador de Confiança ✅ CONCLUÍDA

> Claude delega automaticamente para Claude Opus quando confiança está abaixo do threshold.
> Critério de aceite: pergunta jurídica complexa → score < 0.70 → Claude Opus responde. Pergunta de status → Claude responde.

---

### 2.1 — `ConfidenceRouter` (`services/ai/confidence_router.py`) ✅ FEITO

- [x] `feature_1_ia_personalizada/services/ai/confidence_router.py` criado
- [x] Dataclass `ConfidenceScore` com `valor`, `componentes`, `deve_escalar_harvey`, `motivo`
- [x] Classe `ConfidenceRouter` com `THRESHOLD = 0.70`
- [x] Método `avaliar()` com fórmula ponderada (rag×0.35 + fact×0.25 + intencao×0.25 + historico×0.15)
- [x] Termos de forçamento (CPC art, STJ, STF, Súmula, CLT art) via regex
- [x] Método `rotear()` usando `escalacao_habilitada` e `escalacao_confidence_threshold` do escritório

---

### 2.2 — Campo `modelo_ia` em `Interacao` ✅ FEITO

- [x] Campo `modelo_ia` adicionado em `shared/models/interacao.py:94`

---

### 2.3 — Migration Alembic: `modelo_ia` em `interacoes` ✅ FEITO

- [x] `alembic/versions/20260404_1001_b2c3d4e5f6a7_add_modelo_ia_to_interacoes.py` criada

---

### 2.4 — Dois novos nós no LangGraph Orchestrator ✅ FEITO

- [x] `confidence_score: float | None`, `modelo_ia_usado: str` e `_escalar_para_opus: bool` adicionados em `ConversationState`
- [x] Nó `avaliar_confianca` inserido entre `gerar_resposta` e `verificar_resposta`
- [x] Nó `gerar_resposta_escalacao` criado com fallback gracioso para Claude
- [x] Verifica `escalacao_habilitada` e quota via `ConfidenceRouter.rotear()`
- [x] `modelo_ia_usado` persistido no campo `Interacao.modelo_ia` via `_salvar_interacao`
- [x] `_fluxo_sequencial` (fallback sem LangGraph) atualizado com os 2 novos nós

---

### 2.5 — Prompts escalação para canal do cliente (`services/ai/prompts.py`) ✅ FEITO

- [x] Seção `# === PROMPTS ESCALAÇÃO — CANAL DO CLIENTE ===` adicionada
- [x] `SYSTEM_PROMPT_ESCALACAO_CLIENTE_BASE` criado
- [x] `SYSTEM_PROMPT_ESCALACAO_PERGUNTA_JURIDICA` criado

---

### 2.6 — Métricas escalação em `api/routes/metrics.py` ✅ FEITO

- [x] `escalacao_requests_total` (labels: escritorio_id, resultado)
- [x] `escalacao_roteamentos_total` (labels: escritorio_id, motivo)
- [x] `escalacao_tokens_total` (labels: escritorio_id, tipo)
- [x] `escalacao_latencia_ms` (histogram)

---

### 2.7 — Testes de integração do Roteador ✅ FEITO

- [x] `tests/integration/test_confidence_router.py` criado (commit: "testes confidence")

---

## FASE 3 — Hub do Advogado via WhatsApp ✅ CONCLUÍDA

> Objetivo: Advogado consegue fazer perguntas jurídicas via WhatsApp e receber respostas Claude Opus em < 30s.
> Critério de aceite: Advogado envia "Dúvida sobre CPC art. 485" → Claude Opus responde via WhatsApp em < 30 segundos.

---

### 3.1 — Roteamento no Webhook (`api/routes/webhook_whatsapp.py`) — arquivo EXISTENTE

> **AUDITORIA:** O webhook atual já roteia advogados, mas **somente quando `escalacao_ativa == True`** (resposta de escalação). O Hub precisa de um terceiro ramo: advogados que mandam mensagem **sem escalação ativa** → Hub do Advogado.
>
> O fluxo atual é: `cliente encontrado?` → sim: fluxo cliente | não: `advogado com escalacao_ativa?` → sim: `processar_resposta_advogado` | não: "ignored"
>
> Após a modificação: `cliente encontrado?` → sim: fluxo cliente | não: `advogado com escalacao_ativa?` → sim: `processar_resposta_advogado` (existente, inalterado) | não: `advogado com role advogado/admin e ativo?` → sim: Hub | não: "ignored"

- [x] Adicionar terceiro ramo logo após o bloco de escalação existente (linhas ~191–217 do arquivo):
  - Implementado: query única com `escalacao_ativa` como branch condition (uma query ao invés de duas — mais eficiente)
  - `advogado.escalacao_ativa=True` → `processar_resposta_advogado` (inalterado)
  - `advogado.escalacao_ativa=False` + `escritorio.escalacao_habilitada` → `processar_mensagem_advogado.apply_async(queue="hub_advogado")`
- [x] `Usuario.whatsapp_numero` **já existe** no modelo — nenhuma alteração necessária
- [x] Fluxo existente do cliente e da escalação completamente inalterados
- [x] Quando `escalacao_habilitada=False` o bloco Hub é ignorado

---

### 3.2 — ~~Campo `whatsapp_numero` em `Usuario`~~ — JÁ EXISTE ✅

> **AUDITORIA:** `shared/models/usuario.py` linha 65 já tem `whatsapp_numero: Mapped[str | None]`.
> Migration `20260317_1537_e4bcb5d405fa_add_usuario_whatsapp.py` já aplicada em produção.
> **Nenhuma ação necessária. Nenhuma migration adicional para este campo.**

---

### 3.3 — Modelo `SessaoAdvogado` (`shared/models/sessao_advogado.py`) — arquivo NOVO

- [x] Criar arquivo `shared/models/sessao_advogado.py`
- [x] Criar modelo `SessaoAdvogado(Base, TimestampMixin, TenantMixin)` com todos os campos
  - Índice composto `(usuario_id, escritorio_id, created_at)` — otimizado vs índice em `created_at` isolado
- [x] Exportar `SessaoAdvogado` em `shared/models/__init__.py`

---

### 3.4 — Migration Alembic: `sessoes_advogado` — arquivo NOVO

- [x] Criar `alembic/versions/20260405_1000_c3d4e5f6a7b8_add_sessoes_advogado.py`
- [x] `upgrade()`: `CREATE TABLE sessoes_advogado` com todos os campos + FKs CASCADE + índice composto `(usuario_id, escritorio_id, created_at)`
- [x] `downgrade()`: `DROP TABLE sessoes_advogado`
- [ ] Validar: `alembic upgrade head` + `alembic downgrade -1` (pendente — executar em ambiente com banco)

---

### 3.5 — Classificador de intenção do advogado (`services/ai/hub_advogado_classifier.py`) — arquivo NOVO

- [x] Criar arquivo `feature_1_ia_personalizada/services/ai/hub_advogado_classifier.py`
- [x] Criar enum `IntencaoAdvogado` com os 7 valores
- [x] Criar dataclass `ClassificacaoAdvogado` (definida ANTES da classe que a usa — fix IDE)
- [x] Criar classe `HubAdvogadoClassificador`
- [x] Implementar `async classificar(mensagem, tipo_media)`:
  - `document` → `ANALISE_PETICAO` sem Claude
  - keywords status/dashboard → `STATUS_ESCRITORIO` via regex (sem Claude)
  - Caso contrário: Claude Haiku com timeout 5s
  - Fallback → `DUVIDA_JURIDICA`
- [x] `SYSTEM_PROMPT_CLASSIFICADOR_ADVOGADO` embutido no arquivo como `_SYSTEM_PROMPT_CLASSIFICADOR` (sem duplicação em prompts.py)

---

### 3.6 — Task Celery do Hub (`workers/hub_advogado.py`) — arquivo NOVO

- [x] Criar arquivo `feature_1_ia_personalizada/workers/hub_advogado.py`
- [x] Criar task `processar_mensagem_advogado` com `base=DLQTask`, `max_retries=3`, `soft_time_limit=120`
- [x] Fluxo completo: validar usuário → verificar `escalacao_habilitada` → classificar → despachar → enviar WhatsApp → salvar `SessaoAdvogado`
- [x] Todos os 7 handlers implementados:
  - `_handler_duvida_juridica` — Claude Opus via `EscalacaoClient`
  - `_handler_analise_peticao` — baixa PDF via `evo.baixar_media`, extrai texto, Claude Opus
  - `_handler_pesquisa_jurisprudencia` — Claude Opus com prompt especializado
  - `_handler_insight_cliente` — `CRMDataAggregator` para dados reais + Claude Opus
  - `_handler_resumo_processo` — busca processo por CNJ no banco + Claude Opus
  - `_handler_rascunho_mensagem` — Claude Opus com prefixo "RASCUNHO — revisar antes de enviar"
  - `_handler_status_escritorio` — dashboard sem LLM (dados estruturados do banco)
- [x] `EscalacaoClient` instanciado UMA vez em `_processar` e passado como parâmetro (fix: não 7x)
- [x] Incrementa `escalacao_tokens_usados_mes` no `Escritorio`

---

### 3.7 — Fila Celery `hub_advogado` (`workers/celery_app.py`) — arquivo EXISTENTE

- [x] Adicionada fila `Queue("hub_advogado", routing_key="hub_advogado")` em `task_queues`
- [x] Adicionada rota `"processar_mensagem_advogado": {"queue": "hub_advogado"}` em `task_routes`
- [x] Adicionado import explícito `feature_1_ia_personalizada.workers.hub_advogado` no bloco de imports
- [ ] Atualizar `infrastructure/docker/docker-compose.yml` para incluir `hub_advogado` nas queues do container worker
- [ ] Atualizar `railway.worker.json` para incluir a nova fila na configuração de produção

---

### 3.8 — Prompts do Hub do Advogado (`services/ai/prompts.py`) — arquivo EXISTENTE

- [x] Adicionada seção `# === PROMPTS DO HUB DO ADVOGADO ===` em `services/ai/prompts.py`
- [x] `SYSTEM_PROMPT_HUB_ADVOGADO_BASE` criado (tom técnico-jurídico, inputs: nome_usuario, nome_escritorio, data_hoje)
- [x] `SYSTEM_PROMPT_HUB_ANALISE_PETICAO` criado (estrutura: IDENTIFICAÇÃO → PONTOS FORTES → VULNERABILIDADES → JURISPRUDÊNCIA → SUGESTÕES → AVALIAÇÃO)
- [x] `SYSTEM_PROMPT_HUB_PESQUISA_JURISPRUDENCIA` criado (output: ementa, data+tribunal, aplicabilidade, tendência)
- [x] `SYSTEM_PROMPT_HUB_INSIGHT_CLIENTE` criado (inputs: nome_cliente, crm_score, resumo_interacoes, resumo_processos, ultima_acao_crm)
- [x] Prompt do classificador embutido em `hub_advogado_classifier.py` como `_SYSTEM_PROMPT_CLASSIFICADOR`

---

### 3.9 — Testes unitários do Hub do Advogado — arquivo NOVO

- [x] Criar `tests/unit/test_hub_advogado.py`
- [x] Teste: `document` → `ANALISE_PETICAO` sem chamar Claude
- [x] Teste: keywords de status → `STATUS_ESCRITORIO` (heurística, sem Claude)
- [x] Teste: Claude com JSON válido → intenção + entidades extraídas corretamente
- [x] Teste: Claude retorna intenção inválida → `DUVIDA_JURIDICA` (fallback)
- [x] Teste: Claude lança exceção → `DUVIDA_JURIDICA` (fallback)
- [x] Teste: `_despachar STATUS_ESCRITORIO` não chama `escalacao_client`
- [x] Teste: `_despachar DUVIDA_JURIDICA` usa `escalacao_client`
- [x] Teste: webhook advogado sem `escalacao_ativa` + hub habilitado → hub enfileirado
- [x] Teste: webhook advogado com `escalacao_ativa=True` → escalation reply (não hub)
- [x] Teste: webhook hub desabilitado → ignored
- [ ] Teste: `SessaoAdvogado` salva com campos corretos (requer fixture de banco — Fase 5)

---

## FASE 4 — Análise de Petições PDF (2–3 dias)

> Objetivo: Advogado envia PDF no WhatsApp → Harvey analisa e responde com insights estruturados.
> Critério de aceite: Advogado envia PDF de petição → recebe análise estruturada em < 60 segundos.

---

### 4.1 — Handler de análise de petição na task Celery (`workers/hub_advogado.py`) — arquivo EXISTENTE (Fase 3) ✅ FEITO

- [x] Implementar `_handler_analise_peticao(payload, usuario, escritorio, db)`:
  1. Baixar PDF via `evolution_client.baixar_media(instance, message_id)`
  2. Extrair texto via `_extrair_texto_pdf()` (função module-level em `ingestion.py`)
  3. Limpar artefatos OCR via `LegalDataCleaner.normalizar_espacos()`
  4. Truncar em 15 000 chars se PDF muito grande
  5. Enviar mensagem imediata de confirmação ao advogado
  6. Chamar `EscalacaoClient.analisar_peca()` com `TipoAnalise.ANALISE_COMPLETA`
  7. Formatar `AnalisePecaResponse` em markdown WhatsApp estruturado (IDENTIFICAÇÃO, PONTOS FORTES, VULNERABILIDADES, JURISPRUDÊNCIA, SUGESTÕES, AVALIAÇÃO X/100)
  8. Salvar `SessaoAdvogado` com `intencao="analise_peticao"`, `modelo_ia="claude_opus"`

---

### 4.2 — Endpoint REST de análise de petição (`api/routes/hub_advogado.py`) — arquivo NOVO ✅ FEITO

- [x] Criar arquivo `feature_1_ia_personalizada/api/routes/hub_advogado.py`
- [x] Criar `POST /hub/analisar-peticao`:
  - Validação por magic bytes `%PDF-` (não só MIME)
  - Tamanho máximo: 10 MB
  - Role: `advogado`, `admin` via `require_advogado`
  - Chama `EscalacaoClient.analisar_peca()` via `get_escalacao_client()` (singleton mockável)
  - Retorna `AnalisePecaResponse` + `texto_truncado` + `percentual_analisado`
  - Salva `SessaoAdvogado`
- [x] Criar `POST /hub/consultar`:
  - Body: `ConsultaHubRequest` com `pergunta`, `cliente_id?`, `processo_id?`
  - Isolamento multi-tenant: `cliente_id`/`processo_id` validados contra `escritorio_id`
  - Chama `EscalacaoClient.gerar_resposta()`
  - Retorna `ConsultaHubResponse` (resposta, modelo_ia, tokens, custo)
  - Salva `SessaoAdvogado`
- [x] Registrar router em `feature_1_ia_personalizada/api/app.py`

---

### 4.3 — Testes de integração de análise de petição — arquivo NOVO ✅ FEITO (12/12 passando)

- [x] Criar `tests/integration/test_analise_peticao.py`
- [x] Teste: role `cliente` → 403
- [x] Teste: arquivo sem magic bytes `%PDF-` → 422
- [x] Teste: PDF > 10 MB → 422
- [x] Teste: falha na extração de texto → 422
- [x] Teste: `EscalacaoIndisponivelError` em análise → 503
- [x] Teste: PDF válido → `EscalacaoClient.analisar_peca()` chamado + `SessaoAdvogado` salva + `texto_truncado`/`percentual_analisado` corretos
- [x] Teste: texto > 15 000 chars → `texto_truncado=True`
- [x] Teste: `POST /hub/consultar` → resposta + `SessaoAdvogado` salva
- [x] Teste: `consultar` com `cliente_id` → nome no contexto + referência salva
- [x] Teste: `consultar` com `processo_id` → CNJ no contexto + referência salva
- [x] Teste: `cliente_id` de outro escritório → ignorado (multi-tenant)
- [x] Teste: `EscalacaoIndisponivelError` em consulta → 503

---

## FASE 5 — Resumos de Processos e Insights CRM (2 dias)

> Objetivo: Harvey cruza dados jurídicos + CRM para insights acionáveis ao advogado.
> Critério de aceite: "Me dá um resumo do João Silva" → Harvey retorna resumo com dados reais + recomendação CRM.

---

### 5.1 — Handler de resumo de processo (`workers/hub_advogado.py`) — arquivo EXISTENTE (Fase 3) ✅ FEITO

- [x] Implementar `_handler_resumo_processo(mensagem, usuario, escritorio, db)`:
  1. Lookup por CNJ (prioridade) OU pelo nome do cliente → processo ativo mais recente
  2. Enriquece com todos os campos do banco: `tipo_acao`, `fase_processual`, `score_risco`, `score_nivel`, `score_interpretacao`, `estado_atual` (andamentos + próximo passo), `valor_causa`, `tribunal`, `vara`
  3. Coleta contexto CRM via `CRMDataAggregator` (score, NPS, interações, último contato, ação sugerida)
  4. Chama `EscalacaoClient.gerar_resposta()` com `SYSTEM_PROMPT_HUB_RESUMO_PROCESSO`
  5. Retorna `(cliente_id_ref, processo_id)` populados para `SessaoAdvogado`
  - **Nota**: RAG de documentos ingeridos disponível em iteração futura (Jusbrasil/DataJud omitidos — dados do DB já são ricos)

---

### 5.2 — Handler de insight de cliente (`workers/hub_advogado.py`) — arquivo EXISTENTE (Fase 3) ✅ FEITO

- [x] Implementar `_handler_insight_cliente(mensagem, usuario, escritorio, db)`:
  1. Fuzzy match por nome (`ilike`) no banco, isolado por `escritorio_id`
  2. Coleta CRM via `CRMDataAggregator.coletar_contexto_cliente()`: score, NPS, interações 30d, último contato, processos ativos
  3. Monta contexto com `SYSTEM_PROMPT_HUB_INSIGHT_CLIENTE`
  4. Chama `EscalacaoClient.gerar_resposta()`
  5. Resposta: situação atual + pontos de atenção + próxima ação + risco de abandono
  6. Salva `SessaoAdvogado` com `cliente_referenciado_id`

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
├── 20260402_*_add_harvey_fields_to_escritorios.py    # Fase 1
├── 20260402_*_add_modelo_ia_to_interacoes.py         # Fase 2
└── 20260402_*_add_sessoes_advogado.py                # Fase 3
# NOTA: whatsapp_numero em usuarios JÁ EXISTE (migration 20260317_*_add_usuario_whatsapp)

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
shared/models/__init__.py             → +export SessaoAdvogado (Fase 3)
# shared/models/usuario.py — NÃO precisa de alteração; whatsapp_numero JÁ EXISTE
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
  3.3 (modelo SessaoAdvogado) → 3.4 (migration)
    → paralelo: 3.5 (classificador) + 3.8 (prompts) + 3.7 (celery fila)
  → 3.6 (task hub_advogado) → 3.1 (webhook roteamento) → 3.9 (testes)
  # 3.2 ignorado — whatsapp_numero já existe
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

---

---

# ESTRATÉGIA — Três Motores de IA Jurídica

> **Contexto:** As fases anteriores assumem Harvey como único motor avançado. Esta seção define a arquitetura plugável com três motores — Harvey AI, Claude Opus e OpenAI o1/GPT-4o — cada um com suas forças e estratégias de performance específicas para este projeto.
>
> **Descoberta crítica do código:** O `orchestrator.py` já classifica intenções como `parecer_juridico`, `estrategia_processual`, `negociacao`, `decisao_judicial_impacto_alto` — e hoje as roteia para escalação humana. Esses são exatamente os casos que o motor avançado deve interceptar **antes** de escalar.

---

## Arquitetura Plugável — `MotorIAJuridico`

### Por que plugável

Harvey pode não estar disponível (API Key pendente, latência do Brasil, custo). Em vez de hardcodar Harvey em todo lugar, definir um protocolo único que todos os motores implementam. O escritório escolhe o motor no plano de assinatura. O `ConfidenceRouter` não precisa saber qual motor está por baixo.

### M.0 — Protocolo Base (`services/ai/motor_juridico_base.py`) — arquivo NOVO

- [ ] Criar `feature_1_ia_personalizada/services/ai/motor_juridico_base.py`
- [ ] Criar dataclass compartilhado `RespostaMotorIA`:
  ```python
  conteudo: str
  motor_usado: str          # 'harvey' | 'claude_opus' | 'openai_o1' | 'openai_gpt4o'
  tokens_input: int
  tokens_output: int
  custo_estimado: Decimal
  latencia_ms: int
  cached: bool              # True se veio do cache Redis
  ```
- [ ] Criar dataclass compartilhado `AnaliseDocumento`:
  ```python
  tipo_peca: str
  pontos_fortes: list[str]
  vulnerabilidades: list[str]
  argumentos_ausentes: list[str]
  precedentes_relevantes: list[str]
  sugestoes: list[str]
  score_qualidade: int       # 0–100
  recomendacao_final: str
  motor_usado: str
  custo_estimado: Decimal
  ```
- [ ] Criar `Protocol` `MotorIAJuridico`:
  ```python
  class MotorIAJuridico(Protocol):
      async def gerar_resposta(
          self,
          system_prompt: str,
          mensagem: str,
          contexto_rag: list[str] | None,
          escritorio_id: int,
      ) -> RespostaMotorIA: ...

      async def analisar_documento(
          self,
          conteudo: str,
          tipo_analise: str,
          contexto_processo: dict | None,
      ) -> AnaliseDocumento: ...

      async def pesquisar_jurisprudencia(
          self,
          query: str,
          tribunal: str | None,
          periodo: str | None,
      ) -> list[dict]: ...

      def esta_disponivel(self) -> bool: ...
      # True se circuit breaker fechado e API key configurada
  ```
- [ ] Criar `MotorRouter` — seleciona o motor correto na hora da chamada:
  ```python
  class MotorRouter:
      def selecionar(
          self,
          escritorio: Escritorio,
          intencao: str,
          fallback_chain: list[str],   # ['harvey', 'claude_opus', 'openai_o1']
      ) -> MotorIAJuridico:
          """
          Percorre fallback_chain em ordem.
          Retorna o primeiro motor disponível (circuit breaker fechado + API key set).
          """
  ```

### M.0b — Campo `motor_juridico_avancado` em `Escritorio` — arquivo EXISTENTE

- [ ] Adicionar campo em `shared/models/escritorio.py`:
  ```python
  motor_juridico_avancado: Mapped[str] = mapped_column(
      String(20), server_default="claude_opus"
  )
  # Valores: 'harvey' | 'claude_opus' | 'openai_o1' | 'desativado'
  ```
- [ ] Adicionar migration `20260402_HHMM_HASH_add_motor_juridico_to_escritorios.py`
- [ ] `upgrade()`: `ALTER TABLE escritorios ADD COLUMN motor_juridico_avancado VARCHAR(20) DEFAULT 'claude_opus';`
- [ ] `downgrade()`: `DROP COLUMN motor_juridico_avancado`

### M.0c — Mapeamento de intenções por motor (lógica no `MotorRouter`)

> Baseado nas intenções reais do `orchestrator.py` (linha 811–824):

```
Claude Sonnet (atual, inalterado):
  status | duvida_termo | duvida_geral | saudacao | reclamacao | desabafo | outro

Motor Avançado (Harvey | Claude Opus | OpenAI o1):
  parecer_juridico              → motor avançado ANTES de escalar
  estrategia_processual         → motor avançado ANTES de escalar
  negociacao                    → motor avançado ANTES de escalar
  decisao_judicial_impacto_alto → motor avançado ANTES de escalar
  perspectivas                  → motor avançado (alto risco de alucinação no Sonnet)
```

**Impacto arquitetural:** O nó `avaliar_escalacao` no LangGraph hoje encaminha `parecer_juridico` etc. direto para escalação. Com o motor avançado, o fluxo muda:

```
classificar_intencao
  → avaliar_escalacao
    → intencao em {parecer_juridico, estrategia_processual...}:
        → [NOVO] gerar_resposta_motor_avancado   ← motor tenta responder
            → se confiança OK: verificar_resposta → enviar_resposta
            → se confiança baixa: preparar_escalacao (mantém comportamento atual)
```

---

## Motor 1 — Harvey AI

> **Perfil:** Especializado em raciocínio jurídico denso, potencialmente com base de jurisprudência própria. Motor premium — mais lento e mais caro, mas mais preciso para análise de documentos.

### Quando usar Harvey

| Caso de uso | Justificativa |
|---|---|
| Análise de petições (PDF) | Harvey pode ter endpoint dedicado para documentos |
| Pesquisa de jurisprudência | Base própria STJ/STF (a confirmar) — RAG complementar |
| `parecer_juridico` no Hub do Advogado | Raciocínio denso especializado |
| `estrategia_processual` no Hub do Advogado | Requer integração de múltiplos precedentes |
| Fallback do ConfidenceRouter < 0.50 | Score muito baixo = Claude Opus falhou também |

### Estratégias de performance — Harvey

#### H.1 — Cache agressivo em Redis (impacto alto, custo Harvey é alto)

- [ ] Implementar cache em `HarveyClient.gerar_resposta()`:
  - Chave: `harvey_resp:{escritorio_id}:{hash(system_prompt[:200] + mensagem)}`
  - TTL: 30 minutos (respostas jurídicas têm validade curta)
  - Hash via `hashlib.sha256` — rápido, colisões aceitáveis nessa escala
  - Hit rate esperado: 15–30% no Hub (advogados perguntam variações similares)
- [ ] Cache separado para análise de processo (mais estável):
  - Chave: `harvey_proc:{processo_id}:{data_ultima_movimentacao}`
  - TTL: 6 horas (invalida se processo tiver nova movimentação)
  - Usar `data_ultima_movimentacao` na chave = cache naturalmente invalidado quando processo atualiza

#### H.2 — Pre-warming de contexto antes de chamar Harvey

- [ ] Na task `processar_mensagem_advogado`, antes de chamar Harvey, disparar em paralelo via `asyncio.gather`:
  1. Buscar histórico das últimas 5 sessões do advogado (Redis)
  2. Buscar top-5 documentos RAG mais relevantes (já em pgvector)
  3. Buscar dados do escritório (nome, especialidades do DNA)
- [ ] Injetar todo o contexto pré-carregado no `system_prompt` do Harvey de uma vez
- [ ] **Nunca** fazer essas buscas dentro da chamada Harvey (latência seria somada)

#### H.3 — Chunking inteligente para PDFs grandes

- [ ] No `_handler_analise_peticao`, antes de chamar Harvey:
  - Se `len(texto) > 8000 tokens`: dividir em chunks de 4000 tokens com 200 de overlap
  - Enviar chunk por chunk e agregar `AnaliseDocumento` (merge de pontos fortes/fracos/sugestões)
  - Usar `asyncio.gather` para chunks do mesmo documento em paralelo (se Harvey suportar concorrência)
- [ ] Reutilizar `_chunk_texto()` de `ingestion.py` — já existe no projeto

#### H.4 — Mensagem imediata de "pensando" no WhatsApp

- [ ] Ao detectar intenção pesada (`ANALISE_PETICAO`, `PESQUISA_JURISPRUDENCIA`):
  - Enviar imediatamente via `WhatsAppService.enviar()`: "🔍 Analisando... respondo em até 60 segundos."
  - Só então chamar Harvey
- [ ] Para `DUVIDA_JURIDICA` simples: não enviar mensagem prévia (Harvey responde em < 15s)

#### H.5 — Circuit breaker com fallback em cascata

- [ ] Configurar `pybreaker.CircuitBreaker` no `HarveyClient.__init__`:
  - `fail_max=3` (abre após 3 falhas consecutivas)
  - `reset_timeout=60` (tenta reabrir após 1 minuto)
- [ ] Fallback em cascata automático via `MotorRouter`:
  - Harvey indisponível → Claude Opus
  - Claude Opus indisponível → OpenAI GPT-4o
  - Todos indisponíveis → Claude Sonnet (motor padrão existente) com aviso

#### H.6 — Prompt engineering específico para Harvey

- [ ] Prompt em **inglês** para Harvey (a confirmar com equipe Harvey se suporte BR é nativo)
  - Se Harvey suporta PT-BR nativamente → prompts em português
  - Se não: prompt base em inglês + instrução `"Always respond in Brazilian Portuguese"`
- [ ] Prompts Harvey devem ser mais concisos que Claude (Harvey raciocina internamente — menos chain-of-thought no prompt)
- [ ] Para análise de petição: estruturar como checklist jurídico, não como conversa

---

## Motor 2 — Claude Opus 4.6

> **Perfil:** Zero nova dependência. Mesmo SDK, mesma API key, mesma `ClaudeClient`. A diferença é o modelo passado para `chamar_direto()`. Claude Opus é ~4x mais capaz que Sonnet em raciocínio mas ~6x mais caro.

### Quando usar Claude Opus

| Caso de uso | Justificativa |
|---|---|
| Fallback do Harvey (circuit breaker aberto) | Mesma API, ativa imediatamente |
| `perspectivas` no canal do cliente | Alto risco de alucinação no Sonnet |
| `parecer_juridico` quando Harvey desativado | Opus é forte o suficiente para 80% dos casos |
| Escritórios sem acesso Harvey/OpenAI | Motor avançado padrão (zero onboarding) |
| Extended thinking em análise complexa | Claude 3.7+ suporta — raciocínio passo a passo |

### Estratégias de performance — Claude Opus

#### O.1 — Reutilizar `ClaudeClient.chamar_direto()` — zero novo código de client

- [ ] `ClaudeClient.chamar_direto()` já aceita `modelo: str` como parâmetro (linha 198–230 do arquivo)
- [ ] Implementar `ClaudeOpusMotor(MotorIAJuridico)` como thin wrapper:
  ```python
  class ClaudeOpusMotor:
      MODELO = "claude-opus-4-6"
      TEMPERATURA = 0.2    # mais determinístico que Sonnet (0.3) para raciocínio jurídico
      MAX_TOKENS = 4096    # Opus pode responder mais longo

      async def gerar_resposta(self, system_prompt, mensagem, contexto_rag, escritorio_id):
          resultado = await self._claude_client.chamar_direto(
              system_prompt=system_prompt,
              mensagem=mensagem,
              modelo=self.MODELO,
              max_tokens=self.MAX_TOKENS,
              temperature=self.TEMPERATURA,
          )
          return RespostaMotorIA(
              conteudo=resultado["resposta"],
              motor_usado="claude_opus",
              tokens_input=resultado["tokens_input"],
              tokens_output=resultado["tokens_output"],
              custo_estimado=resultado["custo"],
              ...
          )
  ```
- [ ] **Não criar novo client HTTP** — toda a infra de retry, backoff, circuit breaker e métricas Prometheus do `ClaudeClient` é herdada automaticamente

#### O.2 — Temperatura 0.2 para jurídico (vs. 0.3 padrão do Sonnet)

- [ ] Opus com temperature 0.2 produz respostas mais consistentes e citações mais precisas
- [ ] Para classificação de intenção no Hub: temperature 0.0 (determinístico)
- [ ] Para rascunho de mensagem ao cliente: temperature 0.5 (mais variado, mais humano)

#### O.3 — Extended Thinking para análise de petição

- [ ] Claude Opus 4.6 suporta `extended_thinking` (chain-of-thought explícito):
  ```python
  # Na análise de petição com Opus
  response = await client.messages.create(
      model="claude-opus-4-6",
      max_tokens=16000,
      thinking={"type": "enabled", "budget_tokens": 8000},
      messages=[{"role": "user", "content": conteudo_peticao}],
  )
  ```
- [ ] O `thinking` block NÃO é enviado ao advogado — apenas o bloco `text` final
- [ ] Custo: tokens de thinking são cobrados como input — incluir no `custo_estimado`
- [ ] Quando usar: somente para `ANALISE_PETICAO` e `PESQUISA_JURISPRUDENCIA` (alto valor, tolera custo extra)

#### O.4 — Cache Redis com TTL diferenciado por intenção

- [ ] Cache mais curto para intenções que mudam (status de processo): 5 minutos
- [ ] Cache mais longo para análise de documentos (petição não muda): 2 horas
- [ ] Chave: `opus_resp:{escritorio_id}:{intencao}:{hash(mensagem[:300])}`
- [ ] Invalidar cache de processo quando `monitor_processos` worker detectar nova movimentação (já acontece — usar evento Celery existente)

#### O.5 — Preços Opus vs. Sonnet — controle de custo

- [ ] Opus 4.6: ~$15/M input, ~$75/M output (estimativa — verificar pricing atual Anthropic)
- [ ] Sonnet 4.6: $3/M input, $15/M output (valores atuais no `claude_client.py`)
- [ ] Adicionar constantes em `shared/config/constants.py`:
  ```python
  CUSTO_OPUS_INPUT_POR_MILHAO = Decimal("15.00")
  CUSTO_OPUS_OUTPUT_POR_MILHAO = Decimal("75.00")
  ```
- [ ] `ClaudeOpusMotor._calcular_custo()` usa as constantes corretas
- [ ] Quota Opus por escritório: usar mesmo campo `harvey_quota_tokens_mes` — é a quota do motor avançado, não específico do Harvey

#### O.6 — Prompts Opus: aproveitar capacidade de raciocínio longo

- [ ] Opus lida bem com prompts longos e estruturados — injetar **mais contexto** que no Sonnet:
  - RAG: top-10 documentos (vs. top-5 do Sonnet)
  - Histórico: últimas 10 interações (vs. 5 do Sonnet)
  - DNA do escritório: completo (especialidades, setores, diferenciais)
- [ ] Pedir ao Opus que estruture a resposta antes de responder (sem extended thinking):
  ```
  Antes de responder, identifique internamente:
  1. O que o advogado realmente quer saber
  2. Quais dados do contexto são relevantes
  3. Quais riscos jurídicos existem na resposta
  Então responda com precisão técnica.
  ```

---

## Motor 3 — OpenAI o1 / GPT-4o

> **Perfil:** SDK `openai==1.50.2` e `OPENAI_API_KEY` já estão no projeto (usados para Whisper). `langchain-openai==0.1.25` também já está instalado. Zero nova dependência — apenas novo uso do client existente.

### Quando usar OpenAI

| Modelo | Caso de uso | Justificativa |
|---|---|---|
| `o1-mini` | Análise de petição, pesquisa de jurisprudência | Chain-of-thought nativo, raciocínio denso |
| `gpt-4o` | Respostas rápidas no Hub, estruturação de dados | Rápido + JSON mode nativo |
| `gpt-4o-mini` | Classificação de intenção no Hub (alternativa ao Haiku) | Barato, rápido, confiável em JSON |

### Regras de seleção dentro do motor OpenAI

```
intencao in {DUVIDA_JURIDICA, RASCUNHO_MENSAGEM}  → gpt-4o    (velocidade)
intencao in {ANALISE_PETICAO, PESQUISA_JURISPRUDENCIA}  → o1-mini  (raciocínio)
classificacao de intencao                          → gpt-4o-mini (custo)
STATUS_ESCRITORIO (dashboard)                      → sem IA (dados estruturados, não precisa de LLM)
```

### Estratégias de performance — OpenAI

#### GPT.1 — `OpenAIMotor` com `AsyncOpenAI` — arquivo NOVO

- [ ] Criar `feature_1_ia_personalizada/services/ai/openai_motor.py`
- [ ] Importar `openai.AsyncOpenAI` — SDK já instalado, zero nova dependência
- [ ] Criar classe `OpenAIMotor(MotorIAJuridico)`:
  ```python
  class OpenAIMotor:
      MODELO_RAPIDO = "gpt-4o"
      MODELO_RACIOCINIO = "o1-mini"
      MODELO_CLASSIFICACAO = "gpt-4o-mini"
      TIMEOUT = 60          # o1 é mais lento que gpt-4o
      MAX_RETRIES = 3

      def __init__(self, api_key: str):
          self._client = openai.AsyncOpenAI(api_key=api_key, timeout=self.TIMEOUT)
          self._breaker = pybreaker.CircuitBreaker(fail_max=3, reset_timeout=60)
  ```
- [ ] Implementar `async gerar_resposta()` usando `gpt-4o`:
  - `response_format={"type": "json_object"}` quando resposta precisar ser estruturada
  - Retry com backoff igual ao `claude_client.py` (mesma lógica `_com_retry`)
  - Log estruturado com `structlog` (mesmo padrão do projeto)
- [ ] Implementar `async analisar_documento()` usando `o1-mini`:
  - **Atenção:** `o1` não suporta `temperature` — omitir o parâmetro
  - **Atenção:** `o1` não suporta `system` role separado — mesclar system + user em mensagem `user`
  - Resposta do `o1` já contém chain-of-thought interno — não pedir explicitamente

#### GPT.2 — Structured Outputs (JSON mode) — vantagem sobre Harvey e Opus

- [ ] GPT-4o tem JSON mode nativo confiável: `response_format={"type": "json_object"}`
- [ ] Usar para:
  - Classificação de intenção do Hub (`HubAdvogadoClassificador`) — substituir Claude Haiku se necessário
  - `AnaliseDocumento` (estrutura definida, fácil parsear)
  - `DNAEscritorio` (campos bem definidos)
- [ ] Schema Pydantic → JSON schema → OpenAI structured output (garante parse sem `try/except`)

#### GPT.3 — Preços OpenAI — controle explícito

- [ ] Adicionar constantes em `shared/config/constants.py`:
  ```python
  # gpt-4o (verificar pricing atual em platform.openai.com)
  CUSTO_GPT4O_INPUT_POR_MILHAO = Decimal("2.50")
  CUSTO_GPT4O_OUTPUT_POR_MILHAO = Decimal("10.00")
  # o1-mini
  CUSTO_O1_MINI_INPUT_POR_MILHAO = Decimal("3.00")
  CUSTO_O1_MINI_OUTPUT_POR_MILHAO = Decimal("12.00")
  # gpt-4o-mini
  CUSTO_GPT4O_MINI_INPUT_POR_MILHAO = Decimal("0.15")
  CUSTO_GPT4O_MINI_OUTPUT_POR_MILHAO = Decimal("0.60")
  ```
- [ ] Atualizar constantes ao renovar contrato (preços mudam com frequência)

#### GPT.4 — Reutilizar OPENAI_API_KEY já existente no settings

- [ ] `settings.OPENAI_API_KEY` **já existe** em `shared/config/settings.py` (linha 23)
- [ ] Não adicionar nova variável — `OpenAIMotor.__init__(api_key=settings.OPENAI_API_KEY)`
- [ ] Adicionar em `settings.py` apenas:
  ```python
  OPENAI_MOTOR_HABILITADO: bool = True   # False desativa motor sem remover credencial
  OPENAI_MODELO_RAPIDO: str = "gpt-4o"
  OPENAI_MODELO_RACIOCINIO: str = "o1-mini"
  ```

#### GPT.5 — Limite de contexto do o1-mini e chunking

- [ ] `o1-mini` suporta 128K tokens de contexto — mas raciocínio em contextos grandes é lento
- [ ] Estratégia: para PDFs > 20 páginas, extrair apenas partes relevantes antes de enviar:
  1. Extrair texto completo via PyMuPDF (já existe)
  2. Usar RAG (pgvector) para selecionar as seções mais relevantes para a query
  3. Enviar apenas as seções selecionadas ao o1-mini (não o PDF completo)
- [ ] Resultado: análise mais focada + menor custo + menor latência

#### GPT.6 — Cache específico por modelo OpenAI

- [ ] Chave Redis: `openai_resp:{modelo}:{escritorio_id}:{hash(mensagem[:300])}`
- [ ] TTL por modelo:
  - `gpt-4o`: 15 minutos (respostas rápidas — menos valor em cache longo)
  - `o1-mini`: 2 horas (raciocínio denso — mais caro, vale guardar mais tempo)
- [ ] **Atenção:** o1 tem "reasoning tokens" que NÃO aparecem no usage — custo real é maior que `usage.total_tokens` indica. Monitorar via `usage.completion_tokens_details.reasoning_tokens` se disponível.

#### GPT.7 — Prompts OpenAI: diferenças críticas vs. Claude

- [ ] **GPT-4o:** suporta `system` + `user` normalmente — mesmo padrão do Claude
- [ ] **o1-mini/o1:** NÃO suporta `system` role nem `temperature`
  ```python
  # ERRADO para o1:
  messages=[{"role": "system", "content": prompt}, {"role": "user", "content": msg}]

  # CORRETO para o1:
  messages=[{"role": "user", "content": f"{prompt}\n\n{msg}"}]
  ```
- [ ] Criar método `_preparar_mensagens(system, user, modelo)` no `OpenAIMotor` que aplica a regra correta automaticamente

---

## Comparativo Final — Qual Motor para Cada Situação

| Situação | Motor 1 | Motor 2 | Motor 3 |
|---|---|---|---|
| **Custo de setup** | Alto (API pendente, confirmações) | Zero (já no stack) | Zero (SDK + key já existem) |
| **Análise de petição** | ⭐⭐⭐ (especializado) | ⭐⭐ (extended thinking) | ⭐⭐ (o1-mini chain-of-thought) |
| **Jurisprudência** | ⭐⭐⭐ (base própria?) | ⭐⭐ (via RAG) | ⭐⭐ (via RAG) |
| **Dúvida jurídica Hub** | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ |
| **Respostas rápidas** | ⭐ (lento) | ⭐⭐ | ⭐⭐⭐ (gpt-4o) |
| **Structured output** | ⭐⭐ | ⭐⭐ | ⭐⭐⭐ (JSON mode nativo) |
| **Latência Brasil** | ❓ (US-based, incógnita) | ✅ (mesma infra atual) | ✅ (datacenters SA) |
| **Custo por análise** | ❓ (desconhecido) | Alto (Opus ~6x Sonnet) | Médio (o1-mini previsível) |
| **Fallback se indisponível** | Claude Opus → OpenAI | OpenAI → Sonnet | Sonnet |

### Ordem de fallback recomendada por tipo de tarefa

```
Análise de Petição:
  Harvey → o1-mini → Claude Opus (extended thinking) → Claude Sonnet (sem análise profunda)

Dúvida Jurídica Hub:
  Harvey → Claude Opus → gpt-4o → Claude Sonnet

Classificação de Intenção (Hub):
  Claude Haiku (atual) → gpt-4o-mini → heurística por keywords (já existe)

Canal do Cliente (ConfidenceRouter):
  Claude Sonnet (score ≥ 0.70) → motor_juridico_avancado do escritório (score < 0.70)
```

---

## Implementação — Arquivos da Camada Plugável

### Novos arquivos (adicionais às Fases 1–5)

```
feature_1_ia_personalizada/services/ai/
├── motor_juridico_base.py     # Protocol + dataclasses compartilhados
├── claude_opus_motor.py       # Thin wrapper sobre ClaudeClient.chamar_direto()
└── openai_motor.py            # AsyncOpenAI — usa SDK já instalado
```

### Modificações adicionais

```
shared/models/escritorio.py
  → +campo motor_juridico_avancado: str (default 'claude_opus')

shared/config/settings.py
  → +OPENAI_MOTOR_HABILITADO: bool
  → +OPENAI_MODELO_RAPIDO: str
  → +OPENAI_MODELO_RACIOCINIO: str

shared/config/constants.py
  → +constantes de preço para Opus, gpt-4o, o1-mini

alembic/versions/
  → +20260402_*_add_motor_juridico_to_escritorios.py
```

### Testes adicionais

```
tests/unit/
├── test_claude_opus_motor.py   # Verifica que chamar_direto é chamado com modelo correto
├── test_openai_motor.py        # Mock AsyncOpenAI; verifica chunking, JSON mode, o1 sem temperature
└── test_motor_router.py        # Fallback em cascata; circuit breaker abre → próximo motor

tests/integration/
└── test_motor_completo.py      # End-to-end: intent → MotorRouter → motor → RespostaMotorIA
```

### Critérios de aceite da camada plugável

- [ ] `motor_juridico_avancado = "claude_opus"` → análise de petição usa `claude-opus-4-6` com extended thinking
- [ ] `motor_juridico_avancado = "openai_o1"` → análise usa `o1-mini` com prompt sem `system` role
- [ ] `motor_juridico_avancado = "harvey"` → comportamento das Fases 1–5
- [ ] Harvey com circuit breaker aberto → `MotorRouter` seleciona Claude Opus automaticamente
- [ ] Todos os motores gravam `motor_usado` em `SessaoAdvogado` e `modelo_ia` em `Interacao`
- [ ] Custo calculado corretamente para cada motor (constantes diferentes por modelo)
- [ ] `motor_juridico_avancado = "desativado"` → comportamento atual (Claude Sonnet para tudo)
