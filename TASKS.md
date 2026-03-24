# TASKS — Feature 3: Prospecção Inteligente (LinkedIn + DataJud)

> **Escopo:** motor de captação de clientes para advogados. Analisa o DNA do escritório e cruza com dados de empresas-alvo e seus funcionários, gerando uma fila de leads qualificados e pontuados.
> **Acesso:** exclusivo para `advogado` e `admin` — clientes nunca têm acesso a nada aqui.
> **Referência:** [README.md#feature-3](README.md) — seção "Feature 3 — Prospecção Inteligente"

---

## O que a Feature 3 entrega

| Entrega | Descrição |
|---|---|
| **DNA do Advogado** | Analisa o histórico de processos do escritório (já no banco) e identifica: áreas de especialidade, setores onde mais atua, tipo de ação mais recorrente, perfil de cliente ideal. Resultado salvo como JSON no `escritorio`. |
| **Intelligence de Empresa** | Dado um CNPJ ou nome de empresa, agrega: dados cadastrais + sócios (Receita Federal), processos públicos envolvendo a empresa (DataJud), funcionários e cargos (LinkedIn — quando disponível). |
| **Matching & Score** | Claude cruza o DNA do advogado com as necessidades jurídicas detectadas na empresa e gera um score de afinidade 0–100 + razão do match. |
| **Pipeline de Prospecção** | Lista ranqueada de leads (empresa + contato + score + motivo) que o advogado pode acessar, filtrar e atualizar o status (novo → contatado → qualificado → descartado). |

---

## O que já existe e SERÁ reaproveitado

| Componente | Arquivo | Como será usado |
|---|---|---|
| `datajud_client.py` | `services/legal_data/datajud_client.py` | Buscar processos públicos de uma empresa pelo nome/CNPJ. Já tem retry e cache Redis. |
| `ClaudeClient` | `services/ai/claude_client.py` | Gerar análise de DNA do escritório e score de matching. Wrapper com retry já pronto. |
| `TenantMixin` | `shared/models/base.py` | Isolamento por `escritorio_id` automático em todas as novas tabelas. |
| `processos` table | `shared/models/processo.py` | Fonte de dados para o DNA do advogado: `tipo_acao`, `polo_cliente`, `fase_processual`, `score_risco`. |
| `cache_manager` (Redis) | `services/` | Cachear respostas da Receita Federal (TTL 24h) e DataJud (TTL 6h) por CNPJ. |
| `require_advogado` | `api/middleware/auth.py` | Role guard já implementado (3.1) — bloqueia qualquer role que não seja advogado/admin. |
| `get_escritorio_id_advogado` | `api/middleware/auth.py` | Extrai `escritorio_id` do token — todas as rotas novas usam isso. |
| `escritorio` model | `shared/models/escritorio.py` | Campo `metadata_json` (JSONB já existente) — salvar o DNA do advogado sem nova coluna. |
| Alembic migrations | `alembic/versions/` | Padrão já estabelecido — nova migration para tabela `leads_prospeccao`. |

---

## Fontes de dados

| Dado | Origem | Custo / Acesso | Status |
|---|---|---|---|
| Histórico de processos do escritório | `processos` table (banco local) | Zero — dados próprios | ✅ Disponível |
| Processos públicos de uma empresa | DataJud CNJ | Gratuito, sem chave | ✅ Disponível (`datajud_client.py`) |
| Dados cadastrais + sócios de CNPJ | ReceitaWS (`receitaws.com.br/v1/cnpj/{cnpj}`) | Gratuito, sem chave, rate limit moderado | ✅ Disponível |
| Funcionários e cargos | LinkedIn People/Company API | Requer LinkedIn Partner Program (semanas de aprovação) | ⚠️ Bloqueado — implementar com fallback gracioso |
| Análise de DNA e scoring | Claude (Anthropic API) | Custo por token — usar Haiku para volume | ✅ Disponível |

> **Estratégia para o LinkedIn:** o cliente `LinkedInClient` é implementado com interface definida, mas opera em modo **degradado** quando sem credenciais: retorna `{"disponivel": false, "motivo": "aguardando_aprovacao_linkedin_partner"}`. O pipeline funciona sem LinkedIn usando apenas Receita Federal + DataJud. Quando as credenciais chegarem, basta configurar `LINKEDIN_CLIENT_ID` e `LINKEDIN_CLIENT_SECRET` no `.env`.

---

## Controle de acesso

```
cliente       → 403 Forbidden
estagiario    → 403 Forbidden
assistente    → 403 Forbidden
advogado      → acesso total (ver e criar leads do próprio escritório)
admin         → acesso total
```

Todas as rotas usam `Depends(get_escritorio_id_advogado)` — isolamento multi-tenant garantido.

---

## Modelo de Dados — Nova Tabela

```sql
-- alembic/versions/011_add_leads_prospeccao.py

CREATE TABLE leads_prospeccao (
    id                  SERIAL PRIMARY KEY,
    escritorio_id       INTEGER NOT NULL REFERENCES escritorios(id) ON DELETE CASCADE,
    cnpj                VARCHAR(18) NOT NULL,
    empresa_nome        VARCHAR(500) NOT NULL,
    empresa_setor       VARCHAR(200),
    empresa_porte       VARCHAR(50),          -- MEI | ME | EPP | MEDIO | GRANDE
    socios              JSONB DEFAULT '[]',   -- [{nome, qualificacao, data_entrada}]
    processos_publicos  JSONB DEFAULT '[]',   -- [{numero_cnj, tipo_acao, fase, polo}]
    contatos_linkedin   JSONB DEFAULT '[]',   -- [{nome, cargo, url_perfil}] — vazio se sem LinkedIn
    score_match         SMALLINT DEFAULT NULL, -- 0-100
    score_motivo        TEXT DEFAULT NULL,     -- texto gerado pelo Claude explicando o match
    status              VARCHAR(50) DEFAULT 'novo',  -- novo | contatado | qualificado | descartado
    notas_advogado      TEXT DEFAULT NULL,     -- campo livre para o advogado anotar
    fonte_descoberta    VARCHAR(100),          -- 'manual' | 'sugerido_ia' | 'importado'
    criado_em           TIMESTAMPTZ DEFAULT NOW(),
    atualizado_em       TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (escritorio_id, cnpj)
);

CREATE INDEX ON leads_prospeccao (escritorio_id, score_match DESC)
    WHERE score_match IS NOT NULL;

CREATE INDEX ON leads_prospeccao (escritorio_id, status);
```

---

## Status Geral

| Subtarefa | Status |
|---|---|
| 3.1 — Role guard (`require_advogado`) | ✅ Concluída |
| 3.2 — `ReceitaFederalClient` | ⬜ Pendente |
| 3.3 — `LinkedInClient` (com fallback) | ⬜ Pendente |
| 3.4 — Migration `leads_prospeccao` + modelo SQLAlchemy | ⬜ Pendente |
| 3.5 — `DNAAdvogadoService` | ⬜ Pendente |
| 3.6 — `EmpresaIntelligenceService` | ⬜ Pendente |
| 3.7 — `MatchingService` | ⬜ Pendente |
| 3.8 — Prompts para DNA e Matching | ⬜ Pendente |
| 3.9 — Schemas Pydantic | ⬜ Pendente |
| 3.10 — Rotas `/prospeccao/*` | ⬜ Pendente |
| 3.11 — Testes unitários | ⬜ Pendente |
| 3.12 — Testes de integração | ⬜ Pendente |

---

## 3.1 — Role guard ✅ (já feito)

Funções `require_advogado`, `get_escritorio_id_advogado` e `get_advogado_id` adicionadas em `feature_1_ia_personalizada/api/middleware/auth.py`.

---

## 3.2 — `ReceitaFederalClient`

**Objetivo:** buscar dados de CNPJ na API pública ReceitaWS — razão social, porte, setor (CNAE), endereço, sócios.

**Arquivo a criar:** `feature_1_ia_personalizada/services/prospeccao/receita_federal_client.py`

- [ ] Criar classe `ReceitaFederalClient`
- [ ] Método `async buscar_cnpj(cnpj: str) -> EmpresaDados | None`:
  - Normaliza CNPJ (remove `.`, `/`, `-`) antes de chamar
  - `GET https://receitaws.com.br/v1/cnpj/{cnpj}` via `httpx.AsyncClient`
  - Timeout 10s; retries 2x com backoff 1s
  - Se status 429 (rate limit): espera 60s e tenta uma vez mais
  - Se status 4xx/5xx: retorna `None` (graceful degradation — não quebra o fluxo)
  - Cacheia resposta no Redis: chave `receita:{cnpj}`, TTL 24h (dados raramente mudam)
  - Loga `cnpj`, `status_code`, `cache_hit` via structlog
- [ ] Método `async buscar_por_nome(nome: str, uf: str | None = None) -> list[EmpresaResumida]`:
  - Usa `https://receitaws.com.br/v1/cnpj/search?query={nome}&uf={uf}` se disponível
  - Fallback: retorna lista vazia se endpoint de busca não disponível na versão gratuita
- [ ] Dataclass interna `EmpresaDados`:
  ```python
  cnpj: str
  razao_social: str
  nome_fantasia: str | None
  situacao: str           # ATIVA | BAIXADA | SUSPENSA
  porte: str              # MEI | ME | EPP | DEMAIS
  cnae_principal: str     # código + descrição
  uf: str
  municipio: str
  socios: list[dict]      # [{nome, qualificacao, data_entrada}]
  ```

**Arquivo a tocar:**
- `requirements-f1.txt` — verificar se `httpx` já está listado (provavelmente sim, FastAPI depende dele)

**Critério de aceite:** CNPJ válido retorna `EmpresaDados`; CNPJ inexistente retorna `None`; segunda chamada para o mesmo CNPJ vem do Redis (cache_hit=True no log); rate limit não quebra o serviço.

---

## 3.3 — `LinkedInClient` (com fallback)

**Objetivo:** wrapper para a LinkedIn API com degradação graciosa — o sistema funciona sem LinkedIn, e quando as credenciais chegarem basta configurar as variáveis de ambiente.

**Arquivo a criar:** `feature_1_ia_personalizada/services/prospeccao/linkedin_client.py`

- [ ] Criar classe `LinkedInClient`
- [ ] `__init__`: verifica `settings.LINKEDIN_CLIENT_ID` e `settings.LINKEDIN_CLIENT_SECRET`. Se ausentes, seta `self.disponivel = False`
- [ ] Método `async buscar_funcionarios(empresa_nome: str, empresa_linkedin_id: str | None = None) -> list[ContatoLinkedIn]`:
  - Se `not self.disponivel`: retorna `[]` imediatamente (sem erro, sem log de warning excessivo)
  - Se disponível: chama LinkedIn People Search API com o nome da empresa como filtro
  - Filtra cargos relevantes para prospecção jurídica: `["CEO", "CFO", "Diretor", "Gerente Jurídico", "Compliance", "General Counsel", "Sócio", "Presidente"]`
  - Retorna máx 10 contatos por empresa
  - Cache Redis: chave `linkedin:{empresa_id}`, TTL 7 dias
- [ ] Dataclass `ContatoLinkedIn`:
  ```python
  nome: str
  cargo: str
  url_perfil: str | None
  empresa: str
  ```
- [ ] Adicionar `LINKEDIN_CLIENT_ID` e `LINKEDIN_CLIENT_SECRET` em `shared/config/settings.py` como campos opcionais (`str | None = None`)

**Arquivo a tocar:**
- `shared/config/settings.py` — adicionar as duas variáveis opcionais
- `docs/guides/secrets.md` — documentar as variáveis (quando LinkedIn for aprovado)

**Critério de aceite:** sem variáveis de env configuradas → `disponivel=False`, método retorna `[]` sem erro; com variáveis configuradas → faz chamada real (testável com mock). Nunca levanta exceção para o chamador.

---

## 3.4 — Migration + modelo SQLAlchemy `LeadProspeccao`

**Objetivo:** criar a tabela `leads_prospeccao` e o modelo ORM correspondente.

**Arquivo a criar (migration):** `alembic/versions/011_add_leads_prospeccao.py`

- [ ] Criar migration com o SQL definido na seção "Modelo de Dados" acima
- [ ] `upgrade()`: CREATE TABLE + 2 índices
- [ ] `downgrade()`: DROP TABLE (cascata)
- [ ] `down_revision` apontar para a migration mais recente (verificar com `alembic heads`)

**Arquivo a criar (modelo):** `shared/models/lead_prospeccao.py`

- [ ] Criar classe `LeadProspeccao(Base, TenantMixin, TimestampMixin)`:
  ```python
  __tablename__ = "leads_prospeccao"

  id: Mapped[int] = mapped_column(primary_key=True)
  cnpj: Mapped[str] = mapped_column(String(18), nullable=False)
  empresa_nome: Mapped[str] = mapped_column(String(500), nullable=False)
  empresa_setor: Mapped[str | None] = mapped_column(String(200))
  empresa_porte: Mapped[str | None] = mapped_column(String(50))
  socios: Mapped[dict] = mapped_column(JSONB, default=list)
  processos_publicos: Mapped[dict] = mapped_column(JSONB, default=list)
  contatos_linkedin: Mapped[dict] = mapped_column(JSONB, default=list)
  score_match: Mapped[int | None] = mapped_column(SmallInteger)
  score_motivo: Mapped[str | None] = mapped_column(Text)
  status: Mapped[str] = mapped_column(String(50), default="novo")
  notas_advogado: Mapped[str | None] = mapped_column(Text)
  fonte_descoberta: Mapped[str | None] = mapped_column(String(100))
  ```
- [ ] Exportar `LeadProspeccao` em `shared/models/__init__.py`

**Critério de aceite:** `alembic upgrade head` sem erros; tabela visível no schema com os dois índices; `alembic downgrade -1` reverte sem erro.

---

## 3.5 — `DNAAdvogadoService`

**Objetivo:** analisar o histórico de processos do escritório e gerar um perfil de especialização — as áreas, setores e tipos de causa onde o escritório tem mais experiência e resultados.

**Arquivo a criar:** `feature_1_ia_personalizada/services/prospeccao/dna_advogado.py`

- [ ] Criar classe `DNAAdvogadoService`
- [ ] Método `async gerar_dna(escritorio_id: int) -> DNAEscritorio`:
  1. Query em `processos` filtrando por `escritorio_id` e `status = 'ativo'` + processos encerrados dos últimos 2 anos:
     - `COUNT(*) GROUP BY tipo_acao ORDER BY COUNT DESC LIMIT 10` — top tipos de ação
     - Distribuição de `polo_cliente` (autor vs réu)
     - Distribuição de `score_nivel` (perfil de complexidade)
     - `fase_processual` mais frequente (onde os processos estão)
  2. Se menos de 5 processos no banco: retorna DNA com `dados_insuficientes=True` (sem chamar Claude)
  3. Com dados suficientes: chamar `ClaudeClient` com `SYSTEM_PROMPT_DNA_ADVOGADO` (ver 3.8) para gerar:
     - `especialidades: list[str]` — 3–5 áreas do direito
     - `setores_alvo: list[str]` — setores de empresa mais prováveis como clientes
     - `perfil_cliente_ideal: str` — parágrafo descrevendo o cliente ideal
     - `diferenciais: list[str]` — pontos fortes do escritório para usar na abordagem
  4. Salvar resultado em `escritorio.metadata_json["dna_prospeccao"]` + `dna_atualizado_em`
  5. Cachear no Redis: chave `dna:{escritorio_id}`, TTL 6h
- [ ] Método `async obter_dna(escritorio_id: int) -> DNAEscritorio`:
  - Tenta Redis → tenta `escritorio.metadata_json["dna_prospeccao"]` → chama `gerar_dna()` se nenhum
- [ ] Dataclass `DNAEscritorio`:
  ```python
  escritorio_id: int
  especialidades: list[str]
  setores_alvo: list[str]
  perfil_cliente_ideal: str
  diferenciais: list[str]
  top_tipos_acao: list[dict]   # [{tipo, contagem, percentual}]
  dados_insuficientes: bool
  gerado_em: datetime
  ```

**Arquivo a tocar:**
- `shared/database/worker_queries.py` — adicionar `get_distribuicao_processos(escritorio_id)`

**Critério de aceite:** com 0–4 processos → `dados_insuficientes=True`, sem chamada Claude; com 5+ processos → retorna DNA completo; segunda chamada no TTL vem do Redis.

---

## 3.6 — `EmpresaIntelligenceService`

**Objetivo:** dado um CNPJ, agregar dados de todas as fontes (Receita Federal, DataJud, LinkedIn) em um objeto único para ser avaliado pelo `MatchingService`.

**Arquivo a criar:** `feature_1_ia_personalizada/services/prospeccao/empresa_intelligence.py`

- [ ] Criar classe `EmpresaIntelligenceService`
- [ ] Método `async pesquisar(cnpj: str, escritorio_id: int) -> EmpresaInteligencia`:
  1. Normalizar e validar CNPJ (reusando `validators.py` se houver validador de CNPJ)
  2. Chamar em paralelo com `asyncio.gather` (timeout 15s total):
     - `ReceitaFederalClient.buscar_cnpj(cnpj)` → dados cadastrais
     - `DataJudClient.buscar_processos_empresa(cnpj_ou_nome)` → processos públicos
     - `LinkedInClient.buscar_funcionarios(empresa_nome)` → contatos (retorna [] se indisponível)
  3. Se Receita Federal retornar `None` (empresa não encontrada): retornar erro claro ao usuário (`EmpresaNaoEncontrada`)
  4. Montar `EmpresaInteligencia` com dados consolidados de todas as fontes
  5. Salvar snapshot no Redis: chave `empresa_intel:{cnpj}:{escritorio_id}`, TTL 6h
- [ ] Dataclass `EmpresaInteligencia`:
  ```python
  cnpj: str
  razao_social: str
  nome_fantasia: str | None
  situacao: str
  porte: str
  setor_cnae: str
  socios: list[dict]
  processos_publicos: list[dict]     # lista de processos do DataJud
  total_processos_publicos: int
  tipos_acao_envolvida: list[str]    # tipos únicos de ação
  contatos_linkedin: list[dict]      # vazio se LinkedIn indisponível
  linkedin_disponivel: bool
  ```

**Critério de aceite:** CNPJ válido → retorna `EmpresaInteligencia` com dados de pelo menos Receita + DataJud; LinkedIn indisponível não quebra o fluxo; chamadas externas rodam em paralelo (não sequencial).

---

## 3.7 — `MatchingService`

**Objetivo:** cruzar o DNA do advogado com a inteligência da empresa e gerar um score de afinidade com justificativa — respondendo: "por que este escritório seria a escolha certa para essa empresa?".

**Arquivo a criar:** `feature_1_ia_personalizada/services/prospeccao/matching.py`

- [ ] Criar classe `MatchingService`
- [ ] Método `async calcular_score(dna: DNAEscritorio, empresa: EmpresaInteligencia) -> ResultadoMatch`:
  1. **Score heurístico** (rápido, sem Claude) — pré-filtro antes de gastar tokens:
     - +30 pts: empresa tem processos públicos em tipos de ação que coincidem com especialidades do escritório
     - +20 pts: setor CNAE da empresa está em `dna.setores_alvo`
     - +15 pts: empresa tem 3+ processos públicos (indica demanda jurídica ativa)
     - +15 pts: contatos LinkedIn com cargo jurídico/diretoria encontrados
     - +10 pts: empresa é MÉDIA ou GRANDE porte
     - +10 pts: empresa ATIVA (não baixada/suspensa)
     - Score máximo heurístico: 100
  2. Se score heurístico < 30: retornar `ResultadoMatch(score=score_heuristico, motivo="Baixa afinidade com o perfil do escritório", gerado_por_ia=False)` — sem chamar Claude
  3. Se score heurístico ≥ 30: chamar Claude com `SYSTEM_PROMPT_MATCH_SCORE` (ver 3.8):
     - Claude refina o score (pode subir ou descer até 20 pts)
     - Claude gera `motivo` — parágrafo explicando o match para o advogado usar na abordagem
     - Claude gera `abordagem_sugerida` — como o advogado deve iniciar o contato
  4. Retornar `ResultadoMatch`
- [ ] Dataclass `ResultadoMatch`:
  ```python
  score: int                   # 0-100
  motivo: str                  # por que esse match é relevante
  abordagem_sugerida: str      # como abordar essa empresa
  gerado_por_ia: bool          # False se score heurístico < 30 (economia de tokens)
  componentes: dict            # detalhamento do score heurístico
  ```

**Critério de aceite:** empresa sem nenhuma sobreposição com o DNA → score < 30, sem chamada Claude; empresa com 2+ sobreposições → Claude chamado e score refinado; `abordagem_sugerida` não faz previsões de resultado.

---

## 3.8 — Prompts para Prospecção

**Arquivo a tocar:** `feature_1_ia_personalizada/services/ai/prompts.py`

- [ ] Adicionar `SYSTEM_PROMPT_DNA_ADVOGADO`:
  - Variáveis: `{nome_escritorio}`, `{top_tipos_acao}` (JSON), `{total_processos}`, `{distribuicao_polo}`, `{distribuicao_complexidade}`
  - Instrução: gerar JSON com `especialidades`, `setores_alvo`, `perfil_cliente_ideal`, `diferenciais`
  - Output: JSON válido — sem texto adicional
  - Max tokens: 600; modelo: Claude Haiku

- [ ] Adicionar `SYSTEM_PROMPT_MATCH_SCORE`:
  - Variáveis: `{dna_escritorio}` (JSON), `{empresa_intel}` (JSON), `{score_heuristico}`
  - Instrução: analisar a afinidade, ajustar o score, gerar motivo e abordagem sugerida
  - Output: JSON com `score_refinado`, `motivo`, `abordagem_sugerida`
  - Regras: nunca prometer resultados; focar em necessidades jurídicas da empresa; Tom direto e profissional
  - Max tokens: 500; modelo: Claude Haiku

**Critério de aceite:** ambos os prompts retornam JSON parseable pelo `json.loads()`; sem instruções que violem OAB.

---

## 3.9 — Schemas Pydantic

**Arquivo a criar:** `shared/schemas/prospeccao.py`

- [ ] `EmpresaBuscarRequest`:
  ```python
  cnpj: str = Field(..., description="CNPJ com ou sem formatação")
  ```
- [ ] `LeadProspeccaoCreate`:
  ```python
  cnpj: str
  notas_advogado: str | None = None
  fonte_descoberta: str = "manual"
  ```
- [ ] `LeadProspeccaoResponse`:
  ```python
  id: int
  cnpj: str
  empresa_nome: str
  empresa_setor: str | None
  empresa_porte: str | None
  score_match: int | None
  score_motivo: str | None
  status: str
  notas_advogado: str | None
  contatos_linkedin: list[dict]
  processos_publicos_count: int
  linkedin_disponivel: bool
  criado_em: datetime
  atualizado_em: datetime
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
  dna_disponivel: bool       # False se escritório tem < 5 processos
  linkedin_disponivel: bool  # False se sem credenciais LinkedIn
  ```
- [ ] `DNAEscritorioResponse`:
  ```python
  especialidades: list[str]
  setores_alvo: list[str]
  perfil_cliente_ideal: str
  diferenciais: list[str]
  dados_insuficientes: bool
  gerado_em: datetime | None
  ```
- [ ] Exportar todos em `shared/schemas/__init__.py`

---

## 3.10 — Rotas `/prospeccao/*`

**Arquivo a criar:** `feature_1_ia_personalizada/api/routes/prospeccao.py`

- [ ] `GET /prospeccao/dna`
  - `Depends(get_escritorio_id_advogado)`
  - Chama `DNAAdvogadoService.obter_dna(escritorio_id)`
  - Response: `DNAEscritorioResponse`
  - Se `dados_insuficientes=True`: retorna 200 com `dados_insuficientes=True` (não é erro)

- [ ] `POST /prospeccao/dna/atualizar`
  - `Depends(get_escritorio_id_advogado)`
  - Força regeneração do DNA (invalida cache Redis)
  - Chama `DNAAdvogadoService.gerar_dna(escritorio_id)`
  - Response: `DNAEscritorioResponse`

- [ ] `POST /prospeccao/empresa`
  - `Depends(get_escritorio_id_advogado)`
  - Body: `EmpresaBuscarRequest`
  - Chama `EmpresaIntelligenceService.pesquisar(cnpj, escritorio_id)`
  - Chama `MatchingService.calcular_score(dna, empresa_intel)`
  - Salva `LeadProspeccao` no banco (ou atualiza se CNPJ já existe para o escritório)
  - Response: `LeadProspeccaoResponse`
  - Se empresa não encontrada na Receita Federal: 404 com mensagem clara

- [ ] `GET /prospeccao/pipeline`
  - `Depends(get_escritorio_id_advogado)`
  - Query params: `?status=novo&score_minimo=50&page=1&per_page=20`
  - Lista `leads_prospeccao` do escritório ordenados por `score_match DESC`
  - Response: `PipelineResponse`

- [ ] `PATCH /prospeccao/{lead_id}/status`
  - `Depends(get_escritorio_id_advogado)`
  - Body: `LeadStatusUpdate`
  - Valida que `lead_id` pertence ao `escritorio_id` do token (403 se não pertencer)
  - Atualiza `status` e `notas_advogado`
  - Response: `LeadProspeccaoResponse`

- [ ] `DELETE /prospeccao/{lead_id}`
  - `Depends(get_escritorio_id_advogado)`
  - Valida tenant, hard delete (leads não têm valor histórico crítico)
  - Response: 204 No Content

- [ ] Registrar router em `feature_1_ia_personalizada/api/app.py`:
  ```python
  from feature_1_ia_personalizada.api.routes.prospeccao import router as prospeccao_router
  app.include_router(prospeccao_router)
  ```

---

## 3.11 — Testes unitários

- [ ] `tests/unit/test_receita_federal_client.py`
  - Mock `httpx.AsyncClient` — CNPJ válido retorna dados corretos
  - CNPJ inexistente (404) → retorna `None`
  - Rate limit (429) → retenta uma vez e retorna
  - Cache Redis hit → sem chamada HTTP
  - CNPJ inválido (não numérico) → retorna `None` sem HTTP call

- [ ] `tests/unit/test_linkedin_client.py`
  - Sem variáveis de env → `disponivel=False`, `buscar_funcionarios()` retorna `[]`
  - Com mock de credenciais → faz chamada, retorna lista filtrada por cargo
  - Rate limit → retorna `[]` sem exceção

- [ ] `tests/unit/test_dna_advogado.py`
  - < 5 processos no banco → `dados_insuficientes=True`, sem Claude
  - ≥ 5 processos → Claude chamado, JSON parseado corretamente
  - Cache hit → sem query ao banco, sem Claude
  - `gerar_dna()` após erro do Claude → retorna DNA parcial (só dados heurísticos)

- [ ] `tests/unit/test_matching_service.py`
  - Score heurístico < 30 → `gerado_por_ia=False`, sem Claude
  - Score heurístico ≥ 30 → Claude chamado, score refinado
  - Empresa BAIXADA → desconta pontos (ou bloqueia matching)
  - Todos os 6 critérios heurísticos testados individualmente

- [ ] `tests/unit/test_empresa_intelligence.py`
  - Receita + DataJud + LinkedIn (mock) → `EmpresaInteligencia` completa
  - LinkedIn indisponível → `EmpresaInteligencia` com `linkedin_disponivel=False`, sem erro
  - Receita retorna `None` → levanta `EmpresaNaoEncontrada`
  - Chamadas externas rodam em paralelo (verificar com mock de timing)

---

## 3.12 — Testes de integração

- [ ] `tests/integration/test_prospeccao_routes.py`
  - Setup: escritório, advogado, 5 processos no banco
  - `GET /prospeccao/dna` com token advogado → 200 + `DNAEscritorioResponse`
  - `GET /prospeccao/dna` com token cliente → 403
  - `POST /prospeccao/empresa` com CNPJ válido (mock Receita + DataJud) → 200 + lead salvo no banco
  - `POST /prospeccao/empresa` com CNPJ já existente para o escritório → atualiza, não duplica
  - `GET /prospeccao/pipeline` → lista leads com paginação e filtro por status
  - `PATCH /prospeccao/{id}/status` com lead de outro escritório → 403
  - `DELETE /prospeccao/{id}` → 204, lead removido do banco
  - Multi-tenant: advogado de escritório B não vê leads de escritório A

---

## Arquivos novos a criar (resumo)

```
feature_1_ia_personalizada/
└── api/
│   └── routes/
│       └── prospeccao.py                 # Rotas /prospeccao/*
└── services/
    └── prospeccao/
        ├── __init__.py
        ├── receita_federal_client.py     # ReceitaFederalClient
        ├── linkedin_client.py            # LinkedInClient (com fallback)
        ├── dna_advogado.py               # DNAAdvogadoService
        ├── empresa_intelligence.py       # EmpresaIntelligenceService
        └── matching.py                   # MatchingService

shared/
├── models/
│   └── lead_prospeccao.py                # Modelo ORM LeadProspeccao
└── schemas/
    └── prospeccao.py                     # Todos os schemas de resposta

alembic/versions/
└── 011_add_leads_prospeccao.py           # Migration
```

## Arquivos existentes a modificar (resumo)

```
feature_1_ia_personalizada/services/ai/prompts.py
  → + SYSTEM_PROMPT_DNA_ADVOGADO
  → + SYSTEM_PROMPT_MATCH_SCORE

feature_1_ia_personalizada/api/app.py
  → + include_router(prospeccao_router)

shared/config/settings.py
  → + LINKEDIN_CLIENT_ID: str | None = None
  → + LINKEDIN_CLIENT_SECRET: str | None = None

shared/models/__init__.py
  → + LeadProspeccao

shared/schemas/__init__.py
  → + exportar schemas de prospeccao.py
```

---

## Ordem de implementação

```
3.1 ✅ (role guard — feito)
  → 3.4 (migration + modelo)
    → 3.2 (ReceitaFederalClient)     ← pode ser paralelo com 3.3
    → 3.3 (LinkedInClient)           ← pode ser paralelo com 3.2
      → 3.5 (DNAAdvogadoService)     ← depende de queries no banco
        → 3.6 (EmpresaIntelligenceService)  ← depende de 3.2 + 3.3
          → 3.8 (Prompts)            ← pode ser paralelo com 3.7
          → 3.7 (MatchingService)    ← depende de 3.5 + 3.6
            → 3.9 (Schemas)
              → 3.10 (Rotas)
                → 3.11 (Testes unit)
                  → 3.12 (Testes integração)
```
