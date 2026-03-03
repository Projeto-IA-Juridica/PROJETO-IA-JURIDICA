# FEATURE 1 — IA PERSONALIZADA (MVP)
## Lista de Tarefas Detalhada — v2.0 (Revisada)

> Organizada por módulo, seguindo a estrutura de pastas do projeto.
> Cada tarefa inclui: o que criar, onde criar e o que deve conter.
>
> **Changelog v2.0:** Incorporadas todas as correções da validação — nomes de pasta com underscore, dependências faltantes, rotas de autenticação, nó `tratar_erro`, fallback sem Claude, testes adicionais, estimativas revisadas.

---

## ⚠️ ERRATAS DO DOCUMENTO PRINCIPAL DO PROJETO

Antes de iniciar, corrigir no doc do projeto (`PROJETO-IA-JURIDICA`):

1. **SQLAlchemy versão errada** — Mudar `sqlalchemy==0.0.25` → `sqlalchemy==2.0.25`
2. **Termos jurídicos** — Alinhar: MVP usa **50 termos** (não 500). Os 500 são meta pós-MVP.
3. **Driver assíncrono ausente** — Adicionar `asyncpg==0.29.0` ao requirements (o `psycopg2-binary` é síncrono, não serve para `create_async_engine`)
4. **Nomes de pasta com hífens** — Renomear TODAS as pastas `feature-X-...` para `feature_X_...` (hífens são inválidos como módulo Python). Exemplo: `feature-1-ia-personalizada/` → `feature_1_ia_personalizada/`

---

## FASE 0 — SETUP DO PROJETO

### 0.1 Estrutura Raiz

- [x] **Criar repositório Git** — `concierge-juridico/` com `.gitignore` (Python, Node, .env, __pycache__, .pkl, .venv)
- [x] **Criar `pyproject.toml`** — configuração do projeto Python (nome, versão, dependências base)
- [x] **Criar `Makefile`** — comandos `make setup`, `make dev`, `make test`, `make lint`, `make migrate`
- [x] **Criar `.env.example`** — template com todas as variáveis de ambiente necessárias:
  ```
  DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/concierge
  REDIS_URL=redis://localhost:6379/0
  ANTHROPIC_API_KEY=sk-ant-...
  OPENAI_API_KEY=sk-...
  EVOLUTION_API_URL=http://localhost:8080
  EVOLUTION_API_KEY=...
  JUSBRASIL_API_KEY=...
  JWT_SECRET_KEY=...
  ENCRYPTION_KEY=...
  SENTRY_DSN=...
  CELERY_BROKER_URL=redis://localhost:6379/1
  CELERY_RESULT_BACKEND=redis://localhost:6379/2
  GOOGLE_SHEETS_ID=...
  GOOGLE_CREDENTIALS_PATH=/path/to/credentials.json
  ```
- [x] **Criar `docker-compose.yml`** em `infrastructure/docker/` — serviços: postgres:16, redis:7, evolution-api, celery-worker, celery-beat, flower, app-f1
- [x] **Criar `Dockerfile.f1`** em `infrastructure/docker/` — imagem Python 3.12-slim, instala dependências + ffmpeg, copia código, expõe porta 8000

### 0.2 Banco de Dados Local

- [x] **Instalar e configurar PostgreSQL 16** (local ou via Docker)
- [x] **Instalar e configurar Redis 7** (local ou via Docker)
- [x] **Criar database** `concierge_dev` no Postgres
- [x] **Configurar Alembic** — `alembic init` na raiz, ajustar `alembic.ini` e `env.py` para ler `DATABASE_URL` do `.env`

### 0.3 Ferramentas de Desenvolvimento

- [x] **Configurar `ruff`** para linting (`ruff.toml` na raiz)
- [x] **Configurar `pytest`** (`pytest.ini` ou seção em `pyproject.toml`)
- [x] **Configurar `pre-commit`** (`.pre-commit-config.yaml` — hooks: ruff, black, mypy)

### 0.4 Instalar Dependências Python ⚡ NOVA

- [x] **Criar `requirements-base.txt`** — dependências compartilhadas (shared):
  ```
  fastapi==0.109.0
  uvicorn[standard]==0.27.0
  sqlalchemy==2.0.25
  asyncpg==0.29.0
  alembic==1.13.1
  redis==5.0.1
  cryptography==42.0.0
  python-jose[cryptography]==3.3.0
  httpx==0.26.0
  pydantic==2.5.0
  pydantic-settings==2.1.0
  bcrypt==4.1.2
  prometheus-client==0.19.0
  sentry-sdk[fastapi]==1.40.0
  structlog==24.1.0
  ```
- [x] **Criar `requirements-f1.txt`** — dependências da Feature 1:
  ```
  -r requirements-base.txt
  # IA & LLM
  langchain==0.1.0
  langgraph==0.0.20
  anthropic==0.18.0
  openai==1.12.0
  # Async Tasks
  celery==5.3.6
  flower==2.0.1
  # HTTP
  aiohttp==3.9.3
  # Audio
  pydub==0.25.1
  # Google Sheets
  google-api-python-client==2.116.0
  google-auth==2.27.0
  # (ffmpeg instalado via apt no Dockerfile)
  ```
- [x] **Criar virtualenv** e instalar: `pip install -r requirements-f1.txt`
- [x] **Verificar instalação** — rodar `python -c "import fastapi, sqlalchemy, anthropic, langgraph, celery, structlog; print('OK')"`

### 0.5 Criar `__init__.py` em Todos os Módulos ⚡ NOVA

- [x] Criar `__init__.py` vazio em TODOS os diretórios que serão módulos Python:
  ```
  shared/__init__.py
  shared/models/__init__.py
  shared/schemas/__init__.py
  shared/database/__init__.py
  shared/utils/__init__.py
  shared/security/__init__.py
  shared/config/__init__.py
  feature_1_ia_personalizada/__init__.py
  feature_1_ia_personalizada/api/__init__.py
  feature_1_ia_personalizada/api/routes/__init__.py
  feature_1_ia_personalizada/api/middleware/__init__.py
  feature_1_ia_personalizada/services/__init__.py
  feature_1_ia_personalizada/services/ai/__init__.py
  feature_1_ia_personalizada/services/messaging/__init__.py
  feature_1_ia_personalizada/services/legal_data/__init__.py
  feature_1_ia_personalizada/services/integrations/__init__.py
  feature_1_ia_personalizada/workers/__init__.py
  feature_1_ia_personalizada/tests/__init__.py
  feature_1_ia_personalizada/tests/unit/__init__.py
  feature_1_ia_personalizada/tests/integration/__init__.py
  ```

### 0.6 Configurar Entry Point Uvicorn ⚡ NOVA

- [x] **Definir comando de execução** do servidor:
  ```bash
  uvicorn feature_1_ia_personalizada.api.app:app --host 0.0.0.0 --port 8000 --reload
  ```
- [x] Adicionar ao `Makefile` como `make dev`
- [x] Verificar que o import funciona corretamente (pasta com underscores, não hífens)

---

## FASE 1 — SHARED (Core Compartilhado)

> Tudo em `shared/` — usado por TODAS as features.
> ⚠️ Todas as pastas usam underscores (ex: `feature_1_ia_personalizada`, não hífens).

---

### 1.1 `shared/config/`

#### `shared/config/settings.py`
- [x] **Criar classe `Settings`** usando `pydantic_settings.BaseSettings` (pacote `pydantic-settings`, separado do pydantic desde v2)
- [x] Campos obrigatórios:
  - `DATABASE_URL: str`
  - `REDIS_URL: str`
  - `ANTHROPIC_API_KEY: str`
  - `OPENAI_API_KEY: str`
  - `EVOLUTION_API_URL: str`
  - `EVOLUTION_API_KEY: str`
  - `JUSBRASIL_API_KEY: str`
  - `JWT_SECRET_KEY: str`
  - `JWT_ALGORITHM: str = "HS256"`
  - `JWT_EXPIRATION_MINUTES: int = 60`
  - `ENCRYPTION_KEY: str`
  - `SENTRY_DSN: str | None = None`
  - `CELERY_BROKER_URL: str`
  - `CELERY_RESULT_BACKEND: str`
  - `GOOGLE_SHEETS_ID: str | None = None`
  - `GOOGLE_CREDENTIALS_PATH: str | None = None`
  - `ENVIRONMENT: str = "development"` (development | staging | production)
  - `LOG_LEVEL: str = "INFO"`
- [x] Implementar `model_config` com `env_file = ".env"`
- [x] Criar instância singleton `settings = Settings()`

#### `shared/config/constants.py`
- [x] Definir constantes globais:
  - `DISCLAIMER_OAB: str` — texto completo do disclaimer obrigatório
  - `PODE_FAZER: list[str]` — lista de ações permitidas pela IA
  - `NAO_PODE_FAZER: list[str]` — lista de ações proibidas (pareceres, previsões, estratégias)
  - `MAX_TOKENS_RESPOSTA: int = 1024`
  - `TEMPERATURA_CLAUDE: float = 0.3`
  - `MODELO_CLAUDE: str = "claude-sonnet-4-20250514"`
  - `CACHE_TTL_PROCESSO: int = 3600` (1 hora)
  - `CACHE_TTL_ANDAMENTO: int = 1800` (30 min)
  - `RETENCAO_DADOS_ANOS: int = 5`
  - `RETENCAO_LOGS_MESES: int = 6`
  - `FORMATO_NUMERO_PROCESSO: str` (regex CNJ: `\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}`)
  - `MENSAGENS_FALLBACK: dict` — mensagens pré-definidas para quando o Claude estiver fora do ar (ver Fase 3.1)

### 1.2 Logging Base ⚡ NOVA

#### `shared/config/logging.py`
- [x] **Configurar `structlog`** com setup básico para uso desde a Fase 1:
  - Formato: JSON em produção, colorido em desenvolvimento
  - Processadores: adicionar timestamp, log level, caller info
  - Binding de contexto: `escritorio_id`, `cliente_id`, `request_id`
- [x] **Criar helper `get_logger(nome_modulo)`** — retorna logger configurado
- [x] Exemplo de uso: `logger = get_logger("shared.database")`

---

### 1.2 `shared/database/`

#### `shared/database/connection.py`
- [x] **Criar engine SQLAlchemy** com `create_async_engine` (usar driver `asyncpg`, NOT `psycopg2`)
  - ⚠️ A `DATABASE_URL` deve usar o scheme `postgresql+asyncpg://` (não `postgresql://`)
- [x] Configurar pool: `pool_size=20`, `max_overflow=10`, `pool_timeout=30`
- [x] Habilitar SSL se `ENVIRONMENT != "development"`
- [x] Criar `async_session_factory` com `async_sessionmaker`

#### `shared/database/session.py`
- [x] **Criar dependency `get_db()`** — generator assíncrono que fornece sessão e faz commit/rollback automático
  ```python
  async def get_db() -> AsyncGenerator[AsyncSession, None]:
      async with async_session_factory() as session:
          try:
              yield session
              await session.commit()
          except Exception:
              await session.rollback()
              raise
  ```

---

### 1.3 `shared/models/`

#### `shared/models/base.py`
- [x] **Criar `Base`** — `DeclarativeBase` do SQLAlchemy
- [x] **Criar `TimestampMixin`** — mixin com `created_at` e `updated_at` (ambos `DateTime` com timezone, `updated_at` com `onupdate=func.now()`)
- [x] **Criar `TenantMixin`** — mixin com `escritorio_id: int` (FK para tabela `escritorios`) para isolamento multi-tenant

#### `shared/models/escritorio.py`
- [x] **Criar model `Escritorio`** (tabela `escritorios`):
  - `id: int` (PK, autoincrement)
  - `nome: str` (max 200, not null)
  - `cnpj: str` (max 18, unique, not null) — formato XX.XXX.XXX/XXXX-XX
  - `email: str` (max 200, not null)
  - `telefone: str` (max 20, nullable)
  - `endereco: str` (max 500, nullable)
  - `oab_responsavel: str` (max 20, not null) — OAB do advogado responsável
  - `nome_responsavel: str` (max 200, not null)
  - `plano: str` (max 50, default "basico") — basico | profissional | enterprise
  - `ativo: bool` (default True)
  - `max_processos: int` (default 100)
  - `max_clientes: int` (default 200)
  - `webhook_whatsapp_instance: str` (max 100, nullable) — nome da instância Evolution API
  - Herda `TimestampMixin`
- [x] Criar índice único em `cnpj`

#### `shared/models/cliente.py`
- [x] **Criar model `Cliente`** (tabela `clientes`):
  - `id: int` (PK)
  - `escritorio_id: int` (FK `escritorios.id`, not null)
  - `nome: str` (max 200, not null)
  - `cpf: str` (max 14, not null) — criptografado em repouso
  - `email: str` (max 200, nullable)
  - `telefone_whatsapp: str` (max 20, not null) — formato 5511999999999
  - `data_nascimento: Date` (nullable) — para mensagens de aniversário
  - `profissao: str` (max 100, nullable) — para mensagens de datas comemorativas
  - `empresa_atual: str` (max 200, nullable) — contextualização adicional
  - `cargo: str` (max 100, nullable) — personalização de mensagens
  - `ativo: bool` (default True)
  - `aceite_lgpd: bool` (default False)
  - `data_aceite_lgpd: datetime` (nullable)
  - `preferencia_horario_notificacao: str` (default "comercial") — comercial | qualquer | silencioso
  - Herda `TimestampMixin`, `TenantMixin`
- [x] Criar índice composto `(escritorio_id, cpf)` unique
- [x] Criar índice em `telefone_whatsapp`
- [x] **Criar property `idade`** — calcula idade a partir de `data_nascimento`
- [x] **Criar property `e_bancario`** — detecta se profissão contém termos bancários

#### `shared/models/processo.py`
- [x] **Criar model `Processo`** (tabela `processos`):
  - `id: int` (PK)
  - `escritorio_id: int` (FK `escritorios.id`, not null)
  - `cliente_id: int` (FK `clientes.id`, not null)
  - `numero_cnj: str` (max 25, not null) — formato NNNNNNN-DD.AAAA.J.TR.OOOO
  - `tribunal: str` (max 10, nullable) — ex: TJSP, TRF3
  - `vara: str` (max 200, nullable)
  - `comarca: str` (max 200, nullable)
  - `tipo_acao: str` (max 200, nullable) — ex: Ação de Cobrança
  - `polo_cliente: str` (max 20, default "autor") — autor | reu | terceiro
  - `status: str` (max 50, default "ativo") — ativo | arquivado | suspenso | encerrado
  - `ultimo_andamento: str` (text, nullable)
  - `data_ultimo_andamento: datetime` (nullable)
  - `data_distribuicao: datetime` (nullable)
  - `valor_causa: Decimal` (nullable)
  - `advogado_responsavel_id: int` (FK `usuarios.id`, nullable)
  - `jusbrasil_id: str` (max 100, nullable) — ID interno do Jusbrasil
  - `monitoramento_ativo: bool` (default True)
  - `frequencia_monitoramento: str` (default "diario") — diario | semanal
  - Herda `TimestampMixin`, `TenantMixin`
- [x] Criar índice único em `(escritorio_id, numero_cnj)`
- [x] Criar índice em `cliente_id`
- [x] Criar índice em `status`

#### `shared/models/usuario.py`
- [x] **Criar model `Usuario`** (tabela `usuarios`):
  - `id: int` (PK)
  - `escritorio_id: int` (FK `escritorios.id`, not null)
  - `nome: str` (max 200, not null)
  - `email: str` (max 200, not null)
  - `senha_hash: str` (max 300, not null) — bcrypt hash
  - `role: str` (max 30, default "advogado") — admin | advogado | assistente | estagiario
  - `oab: str` (max 20, nullable)
  - `ativo: bool` (default True)
  - `ultimo_login: datetime` (nullable)
  - Herda `TimestampMixin`, `TenantMixin`
- [x] Criar índice único em `email`

#### `shared/models/interacao.py`
- [x] **Criar model `Interacao`** (tabela `interacoes`):
  - `id: int` (PK)
  - `escritorio_id: int` (FK `escritorios.id`, not null)
  - `cliente_id: int` (FK `clientes.id`, not null)
  - `processo_id: int` (FK `processos.id`, nullable) — pode ser interação geral
  - `tipo: str` (max 30) — whatsapp_texto | whatsapp_audio | sistema | notificacao
  - `direcao: str` (max 10) — entrada | saida
  - `mensagem_cliente: str` (text, nullable) — o que o cliente enviou
  - `mensagem_ia: str` (text, nullable) — o que a IA respondeu
  - `tokens_input: int` (default 0)
  - `tokens_output: int` (default 0)
  - `custo_estimado: Decimal` (default 0)
  - `tempo_resposta_ms: int` (nullable) — latência em milissegundos
  - `satisfacao: int` (nullable) — 1 a 5 (pesquisa NPS)
  - `audio_transcricao: str` (text, nullable) — transcrição do áudio se houver
  - `metadata_json: JSON` (nullable) — dados extras (ID mensagem WhatsApp, tipo_relacionamento: aniversario | data_comemorativa | check_in)
  - Herda `TimestampMixin`, `TenantMixin`
- [x] Criar índice em `(escritorio_id, cliente_id)`
- [x] Criar índice em `created_at` — para queries de analytics
- [x] Configurar particionamento por mês (se volume alto)

#### `shared/models/__init__.py`
- [x] Exportar todos os models: `Base, Escritorio, Cliente, Processo, Usuario, Interacao`

---

### 1.4 `shared/schemas/`

#### `shared/schemas/escritorio.py`
- [x] `EscritorioCreate` — campos para criação (nome, cnpj, email, telefone, oab_responsavel, nome_responsavel)
- [x] `EscritorioUpdate` — todos opcionais (partial update)
- [x] `EscritorioResponse` — resposta da API (inclui id, created_at, exclui dados sensíveis)
- [x] `EscritorioList` — resposta paginada (items, total, page, per_page)

#### `shared/schemas/cliente.py`
- [x] `ClienteCreate` — nome, cpf, telefone_whatsapp, email (opcional), data_nascimento (opcional), profissao (opcional), empresa_atual (opcional), cargo (opcional)
- [x] `ClienteUpdate` — todos opcionais
- [x] `ClienteResponse` — resposta com CPF mascarado (***.***.***-XX), inclui idade calculada se data_nascimento presente
- [x] `ClienteAceiteLGPD` — schema para registrar aceite LGPD
- [x] **Adicionar validador em `ClienteCreate`** para `data_nascimento`:
  - Não pode ser futura
  - Cliente deve ser maior de 18 anos
  - Data não pode ser anterior a 150 anos atrás

#### `shared/schemas/processo.py`
- [x] `ProcessoCreate` — numero_cnj, cliente_id, polo_cliente, tipo_acao (opcional)
- [x] `ProcessoUpdate` — todos opcionais
- [x] `ProcessoResponse` — inclui dados do último andamento
- [x] `ProcessoComAndamentos` — resposta com lista de andamentos recentes
- [x] `AndamentoSchema` — data, descricao, tipo

#### `shared/schemas/usuario.py`
- [x] `UsuarioCreate` — nome, email, senha, role, oab (opcional)
- [x] `UsuarioLogin` — email, senha
- [x] `UsuarioResponse` — sem senha_hash
- [x] `TokenResponse` — access_token, refresh_token, token_type, expires_in

#### `shared/schemas/response.py`
- [x] `SuccessResponse` — {success: bool, message: str, data: Any}
- [x] `ErrorResponse` — {success: false, error: str, detail: str | None}
- [x] `PaginatedResponse` — {items: list, total: int, page: int, per_page: int, pages: int}

---

### 1.5 `shared/security/`

#### `shared/security/jwt.py`
- [x] **`criar_token(user_id, escritorio_id, role)`** — gera JWT com payload: sub, escritorio_id, role, exp, iat
- [x] **`validar_token(token)`** — decodifica e valida JWT, retorna payload ou raise
- [x] **`criar_refresh_token(user_id)`** — token de refresh com validade longa (7 dias)
- [x] Usar `python-jose` com algoritmo HS256

#### `shared/security/encryption.py`
- [x] **`criptografar(texto)`** — AES-256 usando `cryptography.fernet`
- [x] **`descriptografar(texto_cifrado)`** — reverso
- [x] **`hash_senha(senha)`** — bcrypt hash (usando pacote `bcrypt`)
- [x] **`verificar_senha(senha, hash)`** — bcrypt verify
- [x] **`mascarar_cpf(cpf)`** — retorna `***.***.***-XX`
- [x] **`mascarar_telefone(tel)`** — retorna `(**) *****-XXXX`

#### `shared/security/permissions.py`
- [x] **Criar enum `Role`** — ADMIN, ADVOGADO, ASSISTENTE, ESTAGIARIO
- [x] **Criar dicionário de permissões** por role:
  - ADMIN: tudo
  - ADVOGADO: CRUD processos, clientes, ver interações
  - ASSISTENTE: leitura processos/clientes, criar interações
  - ESTAGIARIO: apenas leitura
- [x] **Criar decorator/dependency `require_role(roles: list[Role])`** — verifica se o usuário autenticado tem a role necessária
- [x] **Criar dependency `get_current_user(token)`** — extrai e valida token do header Authorization, retorna usuário
- [x] **Criar dependency `check_tenant(user, resource)`** — verifica se o recurso pertence ao mesmo escritório do usuário

---

### 1.6 `shared/utils/`

#### `shared/utils/validators.py`
- [x] **`validar_cpf(cpf: str) -> bool`** — valida CPF com dígitos verificadores
- [x] **`validar_cnpj(cnpj: str) -> bool`** — valida CNPJ com dígitos verificadores
- [x] **`validar_numero_processo(numero: str) -> bool`** — valida formato CNJ (NNNNNNN-DD.AAAA.J.TR.OOOO)
- [x] **`validar_telefone_whatsapp(tel: str) -> bool`** — valida formato brasileiro (55 + DDD + 9 dígitos)
- [x] **`normalizar_cpf(cpf: str) -> str`** — remove pontuação
- [x] **`normalizar_telefone(tel: str) -> str`** — remove formatação, garante 55 + DDD + número
- [x] **`normalizar_numero_processo(num: str) -> str`** — padroniza formato CNJ

#### `shared/utils/formatters.py`
- [x] **`formatar_data_br(dt: datetime) -> str`** — retorna "16/02/2026 às 14:30"
- [x] **`formatar_data_relativa(dt: datetime) -> str`** — retorna "há 3 dias", "hoje", "ontem"
- [x] **`formatar_moeda_brl(valor: Decimal) -> str`** — retorna "R$ 1.500,00"
- [x] **`formatar_numero_processo(num: str) -> str`** — retorna com pontuação CNJ

#### `shared/utils/lgpd.py`
- [x] **`registrar_acesso(user_id, recurso, acao, ip)`** — loga acesso a dados sensíveis
- [x] **`exportar_dados_cliente(cliente_id) -> dict`** — gera pacote JSON com todos os dados de um cliente (portabilidade)
- [x] **`anonimizar_dados_cliente(cliente_id)`** — substitui dados pessoais por valores anônimos (direito ao esquecimento)
- [x] **`verificar_aceite_lgpd(cliente_id) -> bool`** — checa se cliente aceitou termos

#### `shared/utils/audio_handler.py`
- [x] **`converter_ogg_para_mp3(audio_bytes) -> bytes`** — converte áudio OGG do WhatsApp para MP3 (usando `pydub` + `ffmpeg`)
  - ⚠️ Dependências: `pydub` (Python) + `ffmpeg` (binário do SO — instalar via `apt install ffmpeg` no Dockerfile)
- [x] **`transcrever_audio(audio_bytes) -> str`** — envia para OpenAI Whisper API, retorna transcrição em português
- [x] **`validar_duracao_audio(audio_bytes) -> int`** — retorna duração em segundos, rejeita se > 120s
- [x] Configurar timeout e retry para a API Whisper

---

### 1.7 Migrations

- [x] **Criar migration inicial** com Alembic — `alembic revision --autogenerate -m "create_initial_tables"`
- [x] **Validar migration** — `alembic upgrade head` no banco dev
- [x] **Criar script `scripts/setup/init_db.py`** — roda migrations + cria tabelas
- [x] **Criar script `scripts/setup/seed_data.py`** — insere dados de teste:
  - 1 escritório fictício
  - 3 clientes fictícios
  - 5 processos fictícios com números CNJ válidos
  - 2 usuários (admin + advogado)
- [x] **Criar script `scripts/setup/create_admin.py`** — cria usuário admin via CLI interativo

---

## FASE 2 — FEATURE 1: API (FastAPI)

> Tudo em `feature_1_ia_personalizada/api/`
> ⚠️ Nota: o webhook WhatsApp depende do Celery (Fase 4) para processamento assíncrono. Na Fase 2, implementar com processamento **síncrono temporário** (chamar orchestrator direto). Na Fase 4, refatorar para `processar_mensagem_recebida.delay()`.

---

### 2.1 App Principal

#### `feature_1_ia_personalizada/api/app.py` (entry point)
- [x] **Criar app FastAPI** com metadata (title, description, version)
- [x] **Registrar routers**: auth, webhook_whatsapp, processos, chat, health
- [x] **Registrar middlewares**: CORS, auth, rate_limit
- [x] **Configurar event handlers**: startup (conectar DB, Redis) e shutdown (fechar conexões)
- [x] **Configurar Sentry** se `SENTRY_DSN` presente
- [x] **Configurar Prometheus** metrics endpoint (`/metrics`)

---

### 2.2 `feature_1_ia_personalizada/api/middleware/`

#### `auth.py`
- [x] **Criar middleware de autenticação JWT** — intercepta requests, extrai token do header `Authorization: Bearer <token>`, valida usando `shared/security/jwt.py`
- [x] Definir lista de rotas públicas (ex: `/webhook/whatsapp`, `/health`, `/docs`, `/auth/login`, `/auth/refresh`)
- [x] Injetar `current_user` no request state

#### `rate_limit.py`
- [x] **Criar middleware de rate limiting** usando Redis:
  - Webhook WhatsApp: 100 req/min por IP
  - API geral: 60 req/min por usuário
  - Endpoint chat: 30 req/min por usuário
- [x] Retornar header `X-RateLimit-Remaining` e `429 Too Many Requests` quando exceder
- [x] Usar sliding window com Redis (`INCR` + `EXPIRE`)

---

### 2.3 `feature_1_ia_personalizada/api/routes/`

#### `auth.py` ⚡ NOVA — Rotas de Autenticação

> Sem estas rotas, o middleware JWT não funciona (não há como obter token).

- [x] **`POST /auth/login`** — autenticação de usuário
  - Body: `UsuarioLogin` (email, senha)
  - Buscar usuário por email no banco
  - Verificar senha com `verificar_senha()`
  - Se válido: gerar `access_token` + `refresh_token` via `shared/security/jwt.py`
  - Atualizar `ultimo_login` do usuário
  - Retornar `TokenResponse`
  - Se inválido: retornar 401
- [x] **`POST /auth/refresh`** — renovar token expirado
  - Body: `{refresh_token: str}`
  - Validar refresh token
  - Gerar novo `access_token`
  - Retornar `TokenResponse`
- [x] **`GET /auth/me`** — dados do usuário autenticado
  - Requer autenticação
  - Retornar `UsuarioResponse` do usuário do token

#### `health.py` ⚡ MOVIDA DA FASE 7 (básico aqui, detalhado na Fase 7)
- [x] **`GET /health`** — health check básico (retorna 200 + `{"status": "ok"}`)
- [x] **`GET /health/ready`** — verifica conexão DB + Redis (mínimo para saber se a API está funcional)

#### `webhook_whatsapp.py`
- [x] **`POST /webhook/whatsapp`** — recebe mensagens da Evolution API
  - Validar assinatura/API key do webhook
  - Parsear payload da Evolution API (extrair: número remetente, texto da mensagem, tipo: texto/áudio/imagem, instance_name)
  - Se tipo = áudio: chamar `audio_handler.transcrever_audio()`
  - Identificar cliente pelo `telefone_whatsapp` + `instance_name` → escritório
  - Se cliente não encontrado: responder com mensagem padrão "Não encontramos seu cadastro..."
  - Se cliente encontrado: enviar mensagem para o orchestrator (serviço IA)
  - Salvar `Interacao` no banco (direção: entrada)
  - Retornar 200 OK imediatamente
  - ⚠️ **Fase 2**: processamento síncrono (chamar orchestrator direto, com timeout)
  - ⚠️ **Fase 4**: refatorar para `processar_mensagem_recebida.delay()` (Celery assíncrono)
- [x] **`POST /webhook/whatsapp/status`** — webhook de status de mensagem (entregue, lida)
  - Atualizar metadata da interação com status de entrega
- [x] **`GET /webhook/whatsapp/health`** — health check do webhook

#### `processos.py`
- [x] **`GET /processos`** — listar processos do escritório autenticado
  - Query params: `status`, `cliente_id`, `page`, `per_page`, `search` (busca por número CNJ ou nome cliente)
  - Filtrar por `escritorio_id` do token JWT (tenant isolation)
  - Retornar `PaginatedResponse[ProcessoResponse]`
- [x] **`GET /processos/{id}`** — detalhes de um processo
  - Verificar que processo pertence ao escritório
  - Retornar `ProcessoComAndamentos` (com últimos 10 andamentos)
- [x] **`POST /processos`** — cadastrar novo processo
  - Validar `numero_cnj` com `validar_numero_processo()`
  - Verificar que `cliente_id` pertence ao escritório
  - Buscar dados iniciais no Jusbrasil (tribunal, vara, tipo_ação)
  - ⚠️ **Dependência**: requer `jusbrasil_client.py` da Fase 3.3. Se implementar antes, usar dados manuais como fallback temporário.
  - Ativar monitoramento automático
  - Retornar `ProcessoResponse`
- [x] **`PUT /processos/{id}`** — atualizar processo
  - Campos atualizáveis: polo_cliente, advogado_responsavel_id, monitoramento_ativo, frequencia_monitoramento
- [x] **`DELETE /processos/{id}`** — soft delete (status = "encerrado", monitoramento_ativo = False)
- [x] **`POST /processos/{id}/sincronizar`** — forçar sincronização com Jusbrasil agora

#### `chat.py`
- [x] **`GET /chat/history/{cliente_id}`** — histórico de conversas com um cliente
  - Query params: `page`, `per_page`, `data_inicio`, `data_fim`
  - Retornar interações ordenadas por data
- [x] **`POST /chat/send`** — enviar mensagem proativa para cliente
  - Body: `{cliente_id, mensagem, processo_id (opcional)}`
  - Enviar via WhatsApp (Evolution API)
  - Registrar interação (direção: saída, tipo: sistema)
- [x] **`GET /chat/stats`** — estatísticas de interações do escritório
  - Total interações (mês), tempo médio resposta, custo total IA, NPS médio

---

## FASE 3 — FEATURE 1: SERVICES (Lógica de Negócio)

> Tudo em `feature_1_ia_personalizada/services/`

---

### 3.1 `services/ai/` — Orquestração de IA

#### `services/ai/prompts.py`
- [x] **Criar `SYSTEM_PROMPT_BASE`** — prompt de sistema principal do Claude:
  - Persona: assistente jurídico digital do escritório {nome}
  - Tom: profissional mas acessível, empático, paciente
  - Idioma: português brasileiro, evitar juridiquês
  - Regras OAB: NUNCA dar pareceres, NUNCA prever resultados, NUNCA sugerir estratégias
  - Quando não souber: "Vou verificar com o advogado responsável e retorno"
  - Sempre incluir disclaimer quando relevante
  - Formato: mensagens curtas (WhatsApp), usar emojis com moderação (📋, ⚖️, 📅)
- [x] **Criar `SYSTEM_PROMPT_STATUS_PROCESSO`** — prompt específico para consultas de status:
  - Contexto: dados do processo (número, tribunal, último andamento)
  - Instrução: traduzir andamento para linguagem leiga
  - Formato: resumo + explicação + próximos passos previstos
- [x] **Criar `SYSTEM_PROMPT_TRADUZIR_TERMO`** — prompt para tradução de termos jurídicos:
  - Instrução: explicar como se fosse para uma pessoa sem formação jurídica
  - Usar analogias do cotidiano quando possível
- [x] **Criar `SYSTEM_PROMPT_BOAS_VINDAS`** — prompt para onboarding de novo cliente
- [x] **Criar `SYSTEM_PROMPT_SEM_MOVIMENTACAO`** — prompt para quando não há movimentação:
  - Contexto: dias sem movimentação, estágio atual
  - Instrução: explicar que inatividade é normal, contextualizar por que demora
- [x] **Criar `SYSTEM_PROMPT_PESQUISA_SATISFACAO`** — prompt para NPS:
  - Perguntar de 1 a 5 como avalia o atendimento
  - Tom casual e rápido

#### `services/ai/claude_client.py`
- [x] **Criar classe `ClaudeClient`**:
  - `__init__(api_key)` — instanciar cliente `anthropic.Anthropic`
  - `async enviar_mensagem(system_prompt, mensagens_historico, mensagem_usuario) -> dict` — chama `client.messages.create()` com:
    - model: `claude-sonnet-4-20250514`
    - max_tokens: 1024
    - temperature: 0.3
    - system: system_prompt
    - messages: histórico + mensagem atual
  - Retornar: `{resposta: str, tokens_input: int, tokens_output: int, custo: Decimal}`
  - Implementar retry com backoff exponencial (3 tentativas)
  - Implementar timeout de 30 segundos
  - Tratar erros: `RateLimitError`, `APIError`, `AuthenticationError`
  - Logar métricas no Prometheus (latência, tokens, erros)

#### `services/ai/memory.py`
- [x] **Criar classe `ConversationMemory`**:
  - `__init__(redis_client)` — conexão Redis
  - `async salvar_mensagem(escritorio_id, cliente_id, role, content)` — salva em Redis list `conv:{escritorio_id}:{cliente_id}`
  - `async buscar_historico(escritorio_id, cliente_id, limite=20) -> list[dict]` — retorna últimas N mensagens no formato `[{role, content}]`
  - `async limpar_historico(escritorio_id, cliente_id)` — deleta conversa
  - **TTL de 24 horas** por conversa (após 24h sem interação, histórico expira — nova conversa)
  - **Limite de 50 mensagens** por conversa (FIFO — remove as mais antigas)
  - Serialização: JSON compacto

#### `services/ai/translator.py`
- [x] **Criar classe `JuridicalTranslator`**:
  - `__init__()` — carregar dicionário de `data/termos_juridicos/traducoes.json`
  - `traduzir_termo(termo: str) -> str | None` — busca no dicionário local (O(1) com dict)
  - `traduzir_andamento(texto_andamento: str) -> str` — usa Claude para traduzir andamento completo
  - `identificar_termos_tecnicos(texto: str) -> list[str]` — regex + NLP leve para achar termos jurídicos no texto
- [x] **Criar arquivo `data/termos_juridicos/traducoes.json`** com 50 termos iniciais (MVP):
  - "sentença" → "Decisão final do juiz sobre o seu caso"
  - "agravo de instrumento" → "Recurso contra uma decisão parcial do juiz"
  - "tutela antecipada" → "Pedido para o juiz decidir algo antes do julgamento final"
  - "citação" → "Comunicação oficial informando que existe um processo"
  - "contestação" → "Resposta da parte contrária ao processo"
  - (+ 45 termos mais comuns)

#### `services/ai/fact_checker.py`
- [x] **Criar classe `FactChecker`**:
  - `async verificar_status_processo(processo_id, afirmacao_ia: str) -> dict` — compara o que a IA disse com os dados reais do banco
    - Busca processo no banco
    - Verifica: número CNJ correto? tribunal correto? último andamento correto?
    - Retorna: `{verificado: bool, correcoes: list[str]}`
  - `async verificar_prazo(processo_id, prazo_mencionado: str) -> dict` — verifica se prazo mencionado é factível
  - `filtrar_resposta(resposta_ia: str) -> str` — remove qualquer linguagem que soe como parecer jurídico:
    - Regex patterns para detectar: "você deve", "recomendo que", "a estratégia é", "você vai ganhar"
    - Substitui por linguagem neutra ou adiciona disclaimer
  - Logar em `interacao.metadata_json` se houve correção

#### ⭐ `services/ai/orchestrator.py` — CÉREBRO DA IA
- [x] **Criar workflow LangGraph** com os seguintes nós (states):

  **State Schema:**
  ```python
  class ConversationState(TypedDict):
      escritorio_id: int
      cliente_id: int
      processo_id: int | None
      mensagem_original: str
      tipo_mensagem: str  # texto | audio_transcrito
      historico: list[dict]
      intencao: str  # status | duvida_termo | agendamento | saudacao | reclamacao | outro
      dados_processo: dict | None
      resposta_ia: str | None
      resposta_verificada: str | None
      tokens_usados: dict
      erro: str | None
      tentativas_correcao: int  # contador para limitar loops
      usando_fallback: bool  # indica se Claude está fora e está usando mensagem pré-definida
  ```

  **Nó 1: `classificar_intencao`**
  - [x] Recebe mensagem do cliente
  - [x] Usa Claude (prompt curto) para classificar intenção: status, duvida_termo, agendamento, saudacao, reclamacao, outro
  - [x] Se intenção = saudacao → vai direto para `gerar_resposta` (sem consultar processo)
  - [x] Se intenção tem a ver com processo → vai para `buscar_dados`
  - [x] ⚡ **Se Claude falhar aqui**: usar classificação por keywords como fallback (regex simples: "status|andamento|processo" → status, "significa|quer dizer" → duvida_termo, etc.)

  **Nó 2: `buscar_dados`**
  - [x] Identifica qual processo o cliente está perguntando:
    - Se cliente tem 1 processo → usa esse
    - Se cliente tem vários → pergunta qual
    - Se mencionou número → busca pelo número
    - ⚡ **Se cliente tem 0 processos** → responder: "Não encontrei processos vinculados ao seu cadastro. Entre em contato com o escritório para verificar." → pular para `enviar_resposta`
  - [x] Consulta cache Redis primeiro
  - [x] Se cache miss → chama Jusbrasil API
  - [x] Salva no state `dados_processo`

  **Nó 3: `gerar_resposta`**
  - [x] Monta system_prompt baseado na intenção
  - [x] Injeta dados do processo no prompt (se houver)
  - [x] Injeta histórico de conversa (memória Redis)
  - [x] Chama Claude via `ClaudeClient`
  - [x] Salva resposta no state
  - [x] ⚡ **Se Claude estiver fora do ar** (após retries): ativar `usando_fallback = True`, usar mensagens pré-definidas de `constants.MENSAGENS_FALLBACK`:
    - status → "Recebemos sua mensagem sobre o processo {numero}. No momento estou com dificuldades técnicas, mas o escritório retornará em breve."
    - duvida_termo → "Obrigado pela pergunta! Estou com uma dificuldade técnica temporária. Encaminhei sua dúvida ao escritório."
    - saudacao → "Olá! No momento estou passando por uma manutenção rápida. O escritório entrará em contato em breve."
    - outro → mensagem genérica de indisponibilidade

  **Nó 4: `verificar_resposta`**
  - [x] **Se `usando_fallback = True`**: pular verificação (mensagem pré-definida é segura), ir para `enviar_resposta`
  - [x] Chama `FactChecker.verificar_status_processo()` se resposta mencionou dados do processo
  - [x] Chama `FactChecker.filtrar_resposta()` para sanitizar
  - [x] Se houve correção e `tentativas_correcao < 2` → incrementar contador, regenerar resposta
  - [x] Se houve correção e `tentativas_correcao >= 2` → enviar mensagem de fallback

  **Nó 5: `enviar_resposta`**
  - [x] Envia resposta final via WhatsApp (Evolution API)
  - [x] Salva interação completa no banco (Interacao model)
  - [x] Atualiza memória de conversa (Redis)
  - [x] Emite métrica Prometheus
  - [x] Se `usando_fallback = True`: registrar em metadata e disparar alerta para admin

  **Nó 6: `tratar_erro`** ⚡ NOVO — Implementação completa
  - [x] Recebe o state com `erro` preenchido
  - [x] Logar erro completo com stack trace (structlog)
  - [x] Enviar mensagem genérica ao cliente: "Desculpe, estou com uma dificuldade técnica. Encaminhei sua mensagem para o escritório."
  - [x] Disparar notificação para admin/advogado responsável:
    - Via WhatsApp (se configurado) ou log de alta prioridade
    - Conteúdo: cliente_id, mensagem original, erro ocorrido, timestamp
  - [x] Salvar interação no banco com `metadata_json: {erro: true, tipo_erro: "...", stack: "..."}`
  - [x] Emitir métrica Prometheus `ia_errors_total`

  **Edges (transições):**
  - [x] `classificar_intencao` → `buscar_dados` (se precisa de dados)
  - [x] `classificar_intencao` → `gerar_resposta` (se saudação/geral)
  - [x] `buscar_dados` → `gerar_resposta` (se achou dados)
  - [x] `buscar_dados` → `enviar_resposta` (se cliente tem 0 processos — resposta já definida)
  - [x] `gerar_resposta` → `verificar_resposta`
  - [x] `verificar_resposta` → `enviar_resposta` (se OK ou fallback)
  - [x] `verificar_resposta` → `gerar_resposta` (se precisou corrigir, max 2 loops)
  - [x] Qualquer nó com exceção não tratada → `tratar_erro`

---

### 3.2 `services/messaging/` — WhatsApp

#### `services/messaging/evolution_client.py`
- [x] **Criar classe `EvolutionClient`**:
  - `__init__(base_url, api_key)` — config
  - `async enviar_texto(instance, numero, texto) -> dict` — `POST /message/sendText/{instance}`
  - `async enviar_botoes(instance, numero, texto, botoes) -> dict` — envia mensagem com botões interativos
  - `async enviar_lista(instance, numero, titulo, secoes) -> dict` — envia mensagem com lista de opções
  - `async buscar_status_mensagem(instance, message_id) -> str` — verifica se foi entregue/lida
  - `async baixar_media(instance, message_id) -> bytes` — baixa áudio/imagem recebida
  - Implementar retry com backoff (3 tentativas)
  - Timeout de 15 segundos
  - Tratar erros: conexão, timeout, instância offline

#### `services/messaging/whatsapp.py`
- [x] **Criar classe `WhatsAppService`** (wrapper de alto nível):
  - `__init__(evolution_client, db_session)` — dependências
  - `async enviar_mensagem(escritorio_id, cliente_id, texto, processo_id=None)` — resolve instância do escritório, envia via EvolutionClient, salva Interacao
  - `async enviar_notificacao_andamento(processo_id, andamento)` — monta mensagem de atualização e envia para o cliente do processo
  - `async enviar_boas_vindas(escritorio_id, cliente_id)` — envia disclaimer OAB + mensagem de boas-vindas
  - `async enviar_pesquisa_satisfacao(escritorio_id, cliente_id)` — envia pesquisa NPS (botões 1-5)
  - `async enviar_sem_movimentacao(processo_id)` — mensagem explicando inatividade do processo
  - **Respeitar horário**: verificar `preferencia_horario_notificacao` do cliente — se "comercial", só enviar entre 8h-18h (agendar se fora)
  - **Rate limit por cliente**: máximo 5 mensagens/dia por cliente (exceto respostas a perguntas)

#### `services/messaging/templates.py`
- [x] **Criar templates de mensagens** (strings formatáveis):
  - `TEMPLATE_BOAS_VINDAS` — com disclaimer OAB, apresentação, o que a IA pode fazer
  - `TEMPLATE_NOVO_ANDAMENTO` — "📋 Atualização no seu processo {numero}! {resumo_traduzido}"
  - `TEMPLATE_SEM_MOVIMENTACAO` — "Olá! Sobre o processo {numero}, informo que..."
  - `TEMPLATE_PESQUISA_NPS` — "Como você avalia nosso atendimento? (1-5)"
  - `TEMPLATE_ERRO_GENERICO` — "Desculpe, estou com dificuldade. Vou encaminhar para o escritório."
  - `TEMPLATE_CLIENTE_NAO_ENCONTRADO` — "Olá! Não encontrei seu cadastro..."
  - `TEMPLATE_AGENDAMENTO_CONFIRMADO` — "Consulta agendada com Dr(a). {nome} para {data}"
  - `TEMPLATE_CLIENTE_SEM_PROCESSO` — ⚡ NOVO — "Não encontrei processos vinculados ao seu cadastro..."
  - `TEMPLATE_ANIVERSARIO` — ⚡ NOVO — "🎉🎂 Feliz Aniversário, {nome}! A equipe do escritório {escritorio} deseja..."
  - `TEMPLATE_DIA_BANCARIO` — ⚡ NOVO — "💼 Feliz Dia do Bancário! Seu processo está {status_processo}..."
  - `TEMPLATE_DIA_PROFESSOR` — ⚡ NOVO — "📚 Feliz Dia do Professor!..."
  - `TEMPLATE_MENSAGEM_TRIMESTRAL` — ⚡ NOVO — "Olá {nome}! Faz {dias} dias desde nosso último contato..."

#### `services/messaging/scheduler.py`
- [x] **Criar classe `MessageScheduler`**:
  - `agendar_mensagem(escritorio_id, cliente_id, texto, horario_envio: datetime)` — salva tarefa no Celery com ETA
  - `cancelar_agendamento(task_id)` — cancela tarefa Celery
  - `listar_agendamentos(escritorio_id) -> list` — lista mensagens pendentes
  - Lógica de horário comercial: se mensagem gerada fora do horário, agendar para próximo horário válido (ex: 20h → agenda para 8h do dia seguinte)

---

### 3.3 `services/legal_data/` — Dados Processuais

#### `services/legal_data/jusbrasil_client.py`
- [x] **Criar classe `JusbrasilClient`**:
  - `__init__(api_key)` — config
  - `async buscar_processo(numero_cnj: str) -> dict | None` — `GET /processos?numero={numero_cnj}`
    - Retorna: tribunal, vara, comarca, tipo_acao, partes, status
  - `async buscar_andamentos(processo_id: str, desde: datetime = None) -> list[dict]` — `GET /processos/{id}/andamentos`
    - Retorna lista de andamentos: [{data, descricao, tipo}]
  - `async registrar_webhook(numero_cnj: str, callback_url: str)` — registra webhook para notificações
  - `async cancelar_webhook(webhook_id: str)` — cancela monitoramento
  - Implementar retry com backoff
  - Timeout 20 segundos
  - Tratar erros: 404 (processo não encontrado), 429 (rate limit), 5xx

#### `services/legal_data/datajud_client.py`
- [x] **Criar classe `DataJudClient`** (fallback):
  - `__init__()` — sem API key (gratuito)
  - `async buscar_processo(numero_cnj: str) -> dict | None` — consulta DataJud CNJ
  - `async buscar_andamentos(numero_cnj: str) -> list[dict]`
  - Mesma interface que JusbrasilClient (Strategy Pattern)
  - Nota: dados menos ricos, mais lento

#### `services/legal_data/data_cleaner.py`
- [x] **Criar classe `DataCleaner`**:
  - `limpar_andamento(texto_bruto: str) -> str` — remove HTML, caracteres especiais, normaliza espaços
  - `extrair_data_andamento(texto: str) -> datetime | None` — regex para achar datas no texto
  - `classificar_tipo_andamento(texto: str) -> str` — classifica: despacho, sentença, decisão, petição, certidão, audiência, outro
  - `detectar_urgencia(texto: str) -> bool` — detecta termos urgentes: "intimação", "prazo fatal", "citação"

#### `services/legal_data/cache_manager.py`
- [x] **Criar classe `CacheManager`**:
  - `__init__(redis_client)` — conexão Redis
  - `async get_processo(numero_cnj: str) -> dict | None` — busca cache `proc:{numero_cnj}`
  - `async set_processo(numero_cnj: str, dados: dict)` — salva com TTL 1 hora
  - `async get_andamentos(numero_cnj: str) -> list | None` — busca cache `and:{numero_cnj}`
  - `async set_andamentos(numero_cnj: str, dados: list)` — salva com TTL 30 min
  - `async invalidar_processo(numero_cnj: str)` — deleta cache do processo e andamentos
  - Usar prefixos de chave para namespace: `f1:proc:{numero}`, `f1:and:{numero}`

---

### 3.4 `services/integrations/` — Integrações Externas ⚡ NOVA

#### `services/integrations/google_sheets.py`
- [x] **Criar classe `GoogleSheetsClient`**:
  - `__init__(credentials_path, spreadsheet_id)` — inicializa com credenciais service account
  - `async get_clientes() -> list[dict]` — busca dados da planilha "Clientes" (range A2:I)
    - Retorna lista de dicts com: id, nome, telefone, cpf, data_nascimento, profissao, empresa, status, ultimo_contato
    - Parseia data_nascimento do formato DD/MM/YYYY
    - Pula linhas incompletas
  - `async get_datas_comemorativas() -> list[dict]` — busca da planilha "Datas" (range A2:D)
    - Retorna: profissao, dia, mes, nome, template
  - `async registrar_envio(cliente_id, tipo, sucesso, erro=None)` — registra no log (planilha "Log")
    - Append em range "Log!A:E"
    - Campos: cliente_id, tipo, data_envio, sucesso (Sim/Não), erro
- [x] Implementar retry com backoff exponencial (3 tentativas)
- [x] Timeout de 30 segundos por request
- [x] Logar todas as operações com structlog

---

## FASE 4 — FEATURE 1: WORKERS (Celery)

> Tudo em `feature_1_ia_personalizada/workers/`

---

#### `workers/celery_app.py`
- [x] **Configurar Celery app**:
  - Broker: Redis (`CELERY_BROKER_URL`)
  - Result backend: Redis (`CELERY_RESULT_BACKEND`)
  - Serializer: JSON
  - Task routes: definir filas separadas (`monitoramento`, `notificacoes`, `ia`, `relacionamento`)
  - Beat schedule:
    - `monitorar-processos`: a cada 6 horas (06h, 12h, 18h, 00h)
    - `enviar-sem-movimentacao`: semanal (segunda, 10h)
    - `pesquisa-satisfacao`: mensal (dia 1, 14h)
    - `limpar-cache-expirado`: diário (03h)
    - `verificar-aniversarios`: diário (08h)
    - `verificar-datas-profissoes`: diário (08h30)
    - `mensagens-trimestrais`: semanal (segunda, 10h)

#### `workers/monitor_processos.py`
- [x] **Criar task `monitorar_todos_processos()`**:
  - Buscar todos os processos com `monitoramento_ativo=True`
  - Para cada processo (em batch de 10, com rate limit):
    1. Consultar Jusbrasil por novos andamentos (desde `data_ultimo_andamento`)
    2. Se há novo andamento:
       - Atualizar `processo.ultimo_andamento` e `processo.data_ultimo_andamento`
       - Chamar `DataCleaner.limpar_andamento()`
       - Chamar `JuridicalTranslator.traduzir_andamento()`
       - Disparar task `enviar_notificacao_andamento(processo_id, andamento_traduzido)`
    3. Se Jusbrasil falhar: tentar DataJud como fallback
    4. Logar resultado (sucesso/falha) por processo
  - Timeout por processo: 30 segundos
  - Se falhar em um processo, continua para os próximos (log error, não interrompe)

- [x] **Criar task `monitorar_processo_individual(processo_id)`**:
  - Mesma lógica, mas para um processo específico (chamado pelo endpoint `POST /processos/{id}/sincronizar`)

#### `workers/send_notifications.py`
- [x] **Criar task `enviar_notificacao_andamento(processo_id, andamento_traduzido)`**:
  - Buscar processo + cliente
  - Verificar horário permitido (se fora, reagendar)
  - Montar mensagem usando `TEMPLATE_NOVO_ANDAMENTO`
  - Enviar via `WhatsAppService`
  - Registrar interação

- [x] **Criar task `enviar_lote_sem_movimentacao()`**:
  - Buscar processos sem movimentação há mais de 30 dias
  - Para cada: enviar mensagem explicativa via `WhatsAppService`
  - Limite: 1 mensagem de "sem movimentação" por processo a cada 30 dias

- [x] **Criar task `enviar_pesquisa_satisfacao_lote()`**:
  - Buscar clientes que interagiram no último mês e não responderam pesquisa
  - Enviar pesquisa NPS via WhatsApp (botões 1-5)
  - Limite: 1 pesquisa por cliente por mês

- [x] **Criar task `processar_mensagem_recebida(escritorio_id, cliente_id, mensagem, tipo)`**:
  - Task principal chamada pelo webhook (após refatoração da Fase 2)
  - Instancia o orchestrator LangGraph
  - Executa workflow completo
  - Em caso de erro: envia mensagem genérica + notifica admin

#### `workers/mensagens_relacionamento.py` ⚡ NOVA
- [x] **Criar task `verificar_aniversarios_diarios()`** — roda todo dia às 8h:
  - Buscar clientes do Google Sheets com `GoogleSheetsClient.get_clientes()`
  - Filtrar clientes com status "Ativo"
  - Identificar aniversariantes do dia (comparar dia/mês de `data_nascimento` com hoje)
  - Para cada aniversariante:
    1. Buscar processo ativo do cliente
    2. Montar mensagem usando `TEMPLATE_ANIVERSARIO`
    3. Enviar via `WhatsAppService`
    4. Registrar envio no Google Sheets log
    5. Salvar interação no banco com `metadata_json: {tipo_relacionamento: "aniversario"}`
  - Rate limit: processar em batches de 10
  - Timeout: 15 segundos por cliente

- [x] **Criar task `verificar_datas_comemorativas()`** — roda todo dia às 8h30:
  - Buscar datas comemorativas do Google Sheets
  - Identificar quais profissões fazem aniversário hoje
  - Para cada profissão:
    1. Buscar clientes com aquela profissão (filtro case-insensitive)
    2. Para cada cliente:
       - Buscar processo ativo
       - Montar mensagem usando template apropriado (TEMPLATE_DIA_BANCARIO, etc)
       - Enviar via WhatsAppService
       - Registrar envio no log
       - Salvar interação com `metadata_json: {tipo_relacionamento: "data_comemorativa"}`

- [x] **Criar task `verificar_clientes_sem_contato()`** — roda semanalmente (segunda 10h):
  - Buscar clientes ativos do Google Sheets
  - Para cada cliente:
    1. Verificar última interação no banco de dados
    2. Se última interação > 90 dias ou nenhuma interação:
       - Buscar processo ativo do cliente
       - Montar mensagem usando `TEMPLATE_MENSAGEM_TRIMESTRAL`
       - Enviar via WhatsAppService
       - Registrar envio
       - Salvar interação com `metadata_json: {tipo_relacionamento: "check_in"}`
  - Limite: máximo 10 clientes sem contato por execução (evitar spam)

#### Refatoração do Webhook ⚡ NOVA
- [x] **Refatorar `webhook_whatsapp.py`** para usar Celery:
  - Substituir chamada síncrona ao orchestrator por `processar_mensagem_recebida.delay()`
  - O webhook agora apenas: valida payload → identifica cliente → dispara task → retorna 200

#### Teste Local do Celery Beat ⚡ NOVA
- [ ] **Testar Celery Beat localmente**:
  - Subir Celery worker: `celery -A feature_1_ia_personalizada.workers.celery_app worker --loglevel=info`
  - Subir Celery beat: `celery -A feature_1_ia_personalizada.workers.celery_app beat --loglevel=info`
  - Verificar que cron jobs disparam nos horários configurados
  - Verificar no Flower (`localhost:5555`) que tasks aparecem na fila

---

## FASE 5 — DADOS ESTÁTICOS

> Tudo em `feature_1_ia_personalizada/data/`

---

#### `data/knowledge_base/disclaimers.json`
- [x] Criar JSON com disclaimers:
  ```json
  {
    "primeiro_contato": "Olá! Sou a assistente digital do escritório {escritorio}...",
    "antes_informacao_processual": "Lembrando que sou uma assistente digital...",
    "quando_perguntam_conselho": "Entendo sua dúvida! Porém, como assistente digital, não posso dar orientações jurídicas..."
  }
  ```

#### `data/knowledge_base/datas_comemorativas.json` ⚡ NOVA
- [x] Criar JSON com datas profissionais pré-configuradas:
  ```json
  [
    {
      "profissao": "Bancário",
      "dia": 28,
      "mes": 8,
      "nome": "Dia do Bancário",
      "template": "DIA_BANCARIO"
    },
    {
      "profissao": "Professor",
      "dia": 15,
      "mes": 10,
      "nome": "Dia do Professor",
      "template": "DIA_PROFESSOR"
    },
    {
      "profissao": "Advogado",
      "dia": 11,
      "mes": 8,
      "nome": "Dia do Advogado",
      "template": "DIA_ADVOGADO"
    },
    {
      "profissao": "Médico",
      "dia": 18,
      "mes": 10,
      "nome": "Dia do Médico",
      "template": "DIA_MEDICO"
    }
  ]
  ```
  - Total de ~11 profissões pré-configuradas

#### `data/termos_juridicos/traducoes.json`
- [x] Criar JSON com **50 termos** iniciais (MVP) e traduções — formato:
  ```json
  {
    "sentença": {
      "traducao": "Decisão final do juiz de primeira instância sobre o caso",
      "exemplo": "Quando o juiz dá a sentença, ele decide quem tem razão naquela etapa"
    },
    "agravo de instrumento": {
      "traducao": "Recurso contra uma decisão do juiz que não encerra o processo",
      "exemplo": "Se o juiz negou um pedido urgente, seu advogado pode pedir revisão"
    }
  }
  ```
  > ℹ️ Meta pós-MVP: expandir para 500 termos validados.

---

## FASE 6 — TESTES

> Tudo em `feature_1_ia_personalizada/tests/`

---

### 6.1 Testes Unitários (`tests/unit/`)

#### `test_orchestrator.py`
- [x] Testar classificação de intenção (mock Claude): mensagem "qual o status?" → intenção "status"
- [x] Testar classificação: "o que significa sentença?" → intenção "duvida_termo"
- [x] Testar classificação: "bom dia" → intenção "saudacao"
- [x] Testar fluxo completo com mocks (Claude + Jusbrasil + Redis)
- [x] Testar comportamento quando Claude falha (retry + fallback para mensagem pré-definida)
- [x] Testar loop de verificação (max 2 correções)
- [x] ⚡ **Testar cliente com 0 processos** — deve retornar mensagem "não encontrei processos" sem chamar Claude
- [x] ⚡ **Testar nó `tratar_erro`** — simular exceção em qualquer nó, verificar que mensagem genérica é enviada e admin notificado
- [x] ⚡ **Testar fallback de classificação por keywords** — quando Claude está fora, regex classifica corretamente

#### `test_translator.py`
- [x] Testar tradução de termo existente no dicionário
- [x] Testar tradução de termo inexistente (fallback para Claude)
- [x] Testar identificação de termos jurídicos em texto livre
- [x] Testar com termos em maiúscula/minúscula

#### `test_fact_checker.py`
- [x] Testar verificação de número de processo correto → `verificado: True`
- [x] Testar verificação de número de processo incorreto → `verificado: False, correcoes: [...]`
- [x] Testar filtro de linguagem proibida ("você deve fazer X" → removido)
- [x] Testar que linguagem permitida passa sem alteração

#### `test_validators.py` (em shared)
- [x] CPF válido → True; CPF inválido → False; CPF com pontuação → True
- [x] CNPJ válido → True; CNPJ inválido → False
- [x] Número processo CNJ válido → True; formato errado → False
- [x] Telefone com 55+DDD+9 dígitos → True; sem 55 → False

#### `test_encryption.py` ⚡ NOVO (em shared)
- [x] Testar `criptografar` → `descriptografar` retorna texto original
- [x] Testar com texto vazio
- [x] Testar com caracteres especiais (acentos, emojis)
- [x] Testar `hash_senha` → `verificar_senha` retorna True
- [x] Testar `verificar_senha` com hash errado → False
- [x] Testar `mascarar_cpf` com CPF válido → formato `***.***.***-XX`
- [x] Testar `mascarar_telefone` com telefone válido → formato `(**) *****-XXXX`

#### `test_evolution_client.py`
- [x] Testar envio de texto (mock HTTP) → verifica payload correto
- [x] Testar retry em caso de timeout
- [x] Testar tratamento de erro 4xx/5xx

#### `test_jusbrasil_client.py`
- [ ] Testar busca de processo existente (mock) → retorna dados
- [ ] Testar busca de processo inexistente → retorna None
- [ ] Testar busca de andamentos → retorna lista
- [ ] Testar fallback para DataJud quando Jusbrasil falha

#### `test_memory.py` ⚡ NOVO
- [x] Testar salvar e buscar mensagem → retorna corretamente
- [x] Testar TTL de 24 horas → após expiração, histórico vazio
- [x] Testar limite de 50 mensagens → FIFO, mais antigas removidas
- [x] Testar `limpar_historico` → histórico vazio após limpeza
- [x] Testar com múltiplos clientes → históricos isolados

#### `test_cache_manager.py` ⚡ NOVO
- [ ] Testar cache hit → retorna dados salvos
- [ ] Testar cache miss → retorna None
- [ ] Testar TTL processo (1h) → após expiração, retorna None
- [ ] Testar TTL andamento (30min) → após expiração, retorna None
- [ ] Testar `invalidar_processo` → cache limpo para processo e andamentos

#### `test_whatsapp_service.py` ⚡ NOVO
- [ ] Testar envio em horário comercial (10h) → envia imediatamente
- [ ] Testar envio fora do horário (22h) com preferência "comercial" → agenda para 8h
- [ ] Testar envio com preferência "qualquer" fora do horário → envia imediatamente
- [ ] Testar rate limit: 5ª mensagem do dia → envia; 6ª → rejeita (exceto resposta a pergunta)
- [ ] Testar `enviar_boas_vindas` → mensagem contém disclaimer OAB

#### `test_google_sheets.py` ⚡ NOVA
- [x] Testar `get_clientes()` com mock — retorna lista de dicts
- [x] Testar parse de data DD/MM/YYYY → objeto date correto
- [x] Testar pular linhas incompletas (< 8 colunas)
- [x] Testar `get_datas_comemorativas()` — retorna lista com profissão, dia, mês
- [x] Testar `registrar_envio()` — append no Google Sheets
- [x] Testar retry em caso de erro de API
- [x] Testar timeout (30s)

### 6.2 Testes de Integração (`tests/integration/`)

#### `test_whatsapp_flow.py`
- [ ] Testar fluxo completo: webhook recebe mensagem → orchestrator processa → resposta enviada
  - Usar mocks para APIs externas (Claude, Evolution, Jusbrasil)
  - Usar banco de teste real (SQLite ou Postgres de teste)
  - Verificar que Interacao foi salva no banco
- [ ] Testar fluxo com áudio: webhook com mídia → transcrição → processamento → resposta

#### `test_process_monitoring.py`
- [ ] Testar worker de monitoramento: processo com novo andamento → notificação enviada
- [ ] Testar worker: processo sem novidade → nenhuma notificação
- [ ] Testar fallback: Jusbrasil down → DataJud chamado
- [ ] Testar rate limit: não enviar mais de 5 mensagens/dia para o mesmo cliente

#### `test_mensagens_relacionamento.py` ⚡ NOVA
- [x] Testar `verificar_aniversarios_diarios()`:
  - Mock Google Sheets retorna 2 clientes: 1 aniversariante, 1 não
  - Verificar que apenas aniversariante recebe mensagem
  - Verificar que log é registrado no Sheets
  - Verificar que interação é salva no banco com metadata correto
- [x] Testar `verificar_datas_comemorativas()`:
  - Hoje é Dia do Bancário (28/08)
  - Mock retorna 3 clientes: 2 bancários, 1 professor
  - Verificar que apenas bancários recebem mensagem
- [x] Testar `verificar_clientes_sem_contato()`:
  - Cliente com última interação há 95 dias → recebe mensagem
  - Cliente com última interação há 50 dias → não recebe
  - Cliente sem interação → recebe

#### `test_auth_flow.py` ⚡ NOVO
- [x] Testar login com credenciais válidas → retorna tokens
- [x] Testar login com senha errada → 401
- [x] Testar login com email inexistente → 401
- [x] Testar refresh token → novo access_token
- [x] Testar acesso a rota protegida com token válido → 200
- [x] Testar acesso a rota protegida sem token → 401
- [x] Testar acesso com token expirado → 401

### 6.3 Configuração de Testes

#### `tests/conftest.py`
- [x] Fixtures pytest:
  - `db_session` — sessão de banco de teste (transacional, rollback após cada teste)
  - `redis_client` — Redis de teste (flush após cada teste)
  - `mock_claude` — mock do ClaudeClient
  - `mock_evolution` — mock do EvolutionClient
  - `mock_jusbrasil` — mock do JusbrasilClient
  - `mock_google_sheets` — ⚡ NOVA — mock do GoogleSheetsClient
  - `escritorio_factory` — cria escritório de teste
  - `cliente_factory` — cria cliente de teste
  - `processo_factory` — cria processo de teste
  - `usuario_factory` — ⚡ NOVO — cria usuário de teste com senha hasheada
  - `auth_token` — ⚡ NOVO — gera token JWT válido para testes
  - `async_client` — `httpx.AsyncClient` para testar endpoints FastAPI

---

## FASE 7 — MONITORAMENTO E OBSERVABILIDADE

---

### 7.1 Prometheus Metrics

#### Em `feature_1_ia_personalizada/api/app.py`
- [x] Registrar métricas:
  - `Counter: whatsapp_messages_received_total` (labels: escritorio_id, tipo)
  - `Counter: whatsapp_messages_sent_total` (labels: escritorio_id, tipo)
  - `Counter: ia_requests_total` (labels: intencao, sucesso)
  - `Counter: ia_errors_total` (labels: tipo_erro)
  - `Counter: ia_fallback_used_total` — ⚡ NOVO — conta vezes que fallback foi ativado
  - `Counter: mensagens_relacionamento_enviadas_total` — ⚡ NOVA (labels: tipo=aniversario|data_comemorativa|check_in)
  - `Histogram: ia_response_time_seconds`
  - `Histogram: webhook_processing_time_seconds`
  - `Gauge: processos_monitorados_total`
  - `Counter: ia_tokens_consumed_total` (labels: tipo=input|output)
  - `Counter: jusbrasil_requests_total` (labels: endpoint, status)
  - `Counter: fact_check_corrections_total`
  - `Counter: google_sheets_requests_total` — ⚡ NOVA (labels: operacao=get|append, sucesso)

### 7.2 Logging Estruturado

- [x] ⚡ Logging base já configurado na Fase 1 (`shared/config/logging.py`). Aqui, expandir:
- [x] Adicionar middleware de request logging (log de cada request com request_id, método, path, status, latência)
- [x] Logs obrigatórios (validar que todos estão presentes):
  - Toda interação com Claude (tokens, latência, modelo)
  - Todo acesso a dados de cliente (LGPD audit trail)
  - Toda mensagem WhatsApp enviada/recebida
  - Toda consulta Jusbrasil
  - Todos os erros com stack trace
  - Todo uso de fallback (quando Claude está fora)
  - ⚡ NOVO: Toda mensagem de relacionamento enviada (aniversário, data comemorativa, check-in)
  - ⚡ NOVO: Toda operação Google Sheets (sucesso/falha, tempo)

### 7.3 Health Checks Detalhados

#### `feature_1_ia_personalizada/api/routes/health.py` (expandir o criado na Fase 2)
- [x] **`GET /health/detailed`** — verifica:
  - Conexão PostgreSQL (SELECT 1)
  - Conexão Redis (PING)
  - Conectividade Claude API (HEAD)
  - Conectividade Evolution API (status da instância)
  - Status workers Celery
  - ⚡ NOVO: Conectividade Google Sheets API (verificar se consegue ler planilha)

---

## FASE 8 — DEPLOY INICIAL

---

### 8.1 Docker

- [x] Criar `Dockerfile.f1` otimizado (multi-stage build, inclui `ffmpeg`)
- [x] Criar `docker-compose.yml` com todos os serviços
- [x] Testar `docker compose up` funcionando localmente
- [ ] Criar `docker-compose.prod.yml` com variáveis de produção

### 8.2 Scripts de Setup

#### `scripts/setup/init_db.py`
- [x] Roda Alembic migrations
- [x] Verifica conexão com PostgreSQL
- [x] Verifica conexão com Redis

#### `scripts/setup/seed_data.py`
- [x] Popula dados de demonstração

#### `scripts/migration/sync_sheets_to_db.py` ⚡ NOVA
- [x] **Migrar dados do Google Sheets para o banco de dados**:
  - [x] Buscar todos os clientes do Google Sheets
  - [x] Para cada cliente:
    1. [x] Verificar se já existe no banco (por CPF + escritorio_id)
    2. [x] Se não existe: criar registro em `clientes`
    3. [x] Se existe: atualizar campos (data_nascimento, profissao, empresa_atual, cargo)
  - [x] Logar estatísticas: total processado, novos criados, atualizados, erros
  - [x] Modo dry-run opcional (--dry-run flag)
  - [x] Validar dados antes de inserir (CPF, telefone, data_nascimento)

#### `scripts/monitoring/health_check.py`
- [x] Script standalone que verifica saúde de todos os serviços
- [x] Retorna exit code 0 (OK) ou 1 (falha) — usável em CI/CD

---

## RESUMO: ORDEM DE EXECUÇÃO RECOMENDADA

| Fase | Prioridade | Estimativa | Descrição |
|------|-----------|------------|-----------|
| 0    | 🔴 Crítica | 1-2 dias   | Setup projeto, Docker, .env, deps, __init__.py |
| 1    | 🔴 Crítica | 3-4 dias   | Shared: models (+ novos campos Cliente), schemas, security, utils, DB, logging base |
| 2    | 🔴 Crítica | 3-4 dias   | API: auth, webhook, processos, chat, health + middleware |
| 3.1  | 🔴 Crítica | **6-7 dias** | Services AI: orchestrator (6 nós), claude_client, prompts, memory, fact_checker, fallbacks |
| 3.2  | 🔴 Crítica | 2-3 dias   | Services Messaging: evolution_client, whatsapp, templates (+ novos templates) |
| 3.3  | 🟡 Alta    | 2-3 dias   | Services Legal Data: jusbrasil, datajud, cache |
| 3.4  | 🟢 Média   | **1 dia**  | ⚡ NOVA: Services Integrations: google_sheets.py |
| 4    | 🟡 Alta    | **3-4 dias** | Workers Celery: monitoramento, notificações, mensagens_relacionamento, refatoração webhook |
| 5    | 🟢 Média   | 1 dia      | Dados estáticos: disclaimers, 50 termos, datas_comemorativas.json |
| 6    | 🟡 Alta    | **5-6 dias** | Testes unitários (13 arquivos) + integração (4 fluxos) |
| 7    | 🟢 Média   | 1-2 dias   | Monitoramento: Prometheus, logging expandido, health detalhado |
| 8    | 🟡 Alta    | 1-2 dias   | Deploy Docker local completo + script migração Sheets→DB |
| **TOTAL** | | **~30-38 dias** | **Para 1 desenvolvedor senior full-time** |

---

> **Nota:** Estimativa atualizada de 28-35 → **30-38 dias** após adicionar Google Sheets + workers de relacionamento. A Fase 3.4 (Google Sheets) adiciona 1 dia, a Fase 4 (workers) aumentou de 2-3 → 3-4 dias, e a Fase 6 (testes) aumentou de 4-5 → 5-6 dias. Com 2 devs, as fases podem ser paralelizadas (ex: um faz Shared/API enquanto o outro faz Services AI). A ordem das fases é sequencial por dependência — não é possível fazer a Fase 3 sem a Fase 1 completa.
>
> **Dependências críticas entre fases:**
> - Fase 2 (API) depende de Fase 1 (Shared) completa
> - Fase 2 `POST /processos` depende de Fase 3.3 `jusbrasil_client.py` (usar stub temporário)
> - Fase 2 webhook depende de Fase 4 para processamento assíncrono (usar síncrono temporário)
> - Fase 3.1 orchestrator depende de Fase 3.2 (messaging) e 3.3 (legal_data)
> - Fase 3.4 (Google Sheets) é independente, pode ser feita em paralelo com 3.1-3.3
> - Fase 4 (Workers) pode ser feita em paralelo com Fase 3.2/3.3, mas workers de relacionamento dependem de 3.4

**Última atualização:** Fevereiro 2026  
**Versão:** 2.1 (+ Google Sheets Integration)
---

## FASE 9 — PRODUCTION READINESS

> Tarefas identificadas na auditoria de fevereiro/2026. Detalhes completos em `docs/guides/production-readiness.md`.
> Organizado por sprint conforme o plano.

---

### 9.1 Sprint 1 — Lógica de Negócio (Blockers Críticos)

#### `workers/monitor_processos.py` — Stubs do banco
- [ ] Implementar `listar_processos_com_monitoramento_ativo()` com query SQLAlchemy síncrona (`SELECT * FROM processos WHERE monitoramento_ativo = true LIMIT :limite`)
- [ ] Implementar `buscar_processo_por_id()` com query real (`SELECT * FROM processos WHERE id = :id`)
- [ ] Implementar `atualizar_ultimo_andamento_do_processo()` com UPDATE real no banco
- [ ] Descomentar imports: `DataJudClient`, `JusbrasilClient`, `JuridicalTranslator` (linhas 12–18)
- [ ] Adicionar `psycopg2-binary` ao `requirements-f1.txt` (driver síncrono para workers Celery)

#### `workers/send_notifications.py` — NotImplementedError [PIJ-193] ✅
- [x] Implementar `buscar_processo_e_cliente(id_processo)` — JOIN processos + clientes
- [x] Implementar `buscar_processos_sem_movimentacao()` — WHERE data_ultimo_andamento < NOW() - INTERVAL '30 days'
- [x] Implementar `buscar_clientes_para_pesquisa()` — clientes com interações no último mês sem pesquisa respondida

#### `workers/mensagens_relacionamento.py` — Helpers sem implementação
- [ ] Implementar `WhatsAppService.enviar_mensagem()` — chamar `EvolutionClient.enviar_texto()`
- [ ] Implementar `buscar_processo_ativo_do_cliente(id_cliente)` — query SQLAlchemy síncrona
- [ ] Implementar `salvar_interacao()` — INSERT em `interacoes` com ORM
- [ ] Implementar `buscar_data_ultima_interacao(id_cliente)` — SELECT MAX(created_at) FROM interacoes

#### `services/messaging/whatsapp.py` — NotImplementedError de contexto [PIJ-195]
- [ ] Implementar resolução `processo_id → (escritorio_id, cliente_id)` nas linhas 241 e 293

#### `workers/celery_app.py` — Testar Beat
- [ ] Testar Celery Beat localmente: subir worker + beat, verificar no Flower que cron jobs disparam

---

### 9.2 Sprint 2 — Segurança

#### Secrets
- [ ] Verificar se `.env` está no histórico git (`git log --oneline --all -- .env`)
- [ ] Se estiver: limpar histórico com `git filter-branch` e revogar/regenerar todas as chaves comprometidas
- [ ] Garantir que `.env.local` ou similar é usado em dev e nunca commitado

#### `api/app.py` — CORS e Error Handler
- [ ] Restringir `allow_origins` para domínio específico em produção (ler `CORS_ALLOWED_ORIGINS` do settings)
- [ ] Adicionar variável `CORS_ALLOWED_ORIGINS` ao `settings.py` e ao `.env.example`
- [ ] Criar `@app.exception_handler(Exception)` global — retornar mensagem genérica sem stack trace para o cliente

#### `api/routes/webhook_whatsapp.py` — Autenticação [PIJ-197]
- [ ] Adicionar validação do header `apikey` comparando com `settings.EVOLUTION_API_KEY`
- [ ] Retornar 401 se apikey ausente ou incorreto

#### `shared/config/settings.py` — Validação de chaves
- [ ] Adicionar `Field(min_length=32)` ao `JWT_SECRET_KEY`
- [ ] Adicionar `@field_validator("ENCRYPTION_KEY")` que valida formato Fernet via `Fernet(v.encode())`

#### `shared/config/logging.py` — Mascarar dados sensíveis
- [ ] Adicionar processador structlog que mascara CPF, tokens JWT e API keys nos logs

---

### 9.3 Sprint 3–4 — Testes e CI/CD

#### Testes HTTP das rotas (`tests/integration/test_api_routes.py`) — arquivo novo [PIJ-201]
- [ ] Criar `tests/integration/test_api_routes.py` com `httpx.AsyncClient` + `ASGITransport`
- [ ] Testar `GET /health` → 200
- [ ] Testar `GET /health/ready` → 200 (com DB/Redis mockados como up)
- [ ] Testar `GET /health/ready` → 503 (com DB mockado como down)
- [ ] Testar `POST /auth/login` com credenciais válidas → 200 + tokens
- [ ] Testar `POST /auth/login` com senha errada → 401
- [ ] Testar `GET /chat/history/{id}` sem token → 401
- [ ] Testar `GET /chat/history/{id}` com token válido → 200
- [ ] Testar `POST /webhook/whatsapp` sem header `apikey` → 401
- [ ] Testar `POST /webhook/whatsapp` com payload válido e apikey correto → 200
- [ ] Testar `GET /metrics` → 200 com content-type Prometheus

#### Testes ausentes (unitários)
- [x] Criar `tests/unit/test_encryption.py` (shared) — criptografar/descriptografar, hash_senha, mascarar_cpf
- [x] Criar `tests/unit/test_evolution_client.py` — envio texto mock HTTP, retry, erro 4xx/5xx
- [ ] Criar `tests/unit/test_jusbrasil_client.py` — busca processo mock, fallback DataJud
- [ ] Criar `tests/unit/test_cache_manager.py` — cache hit/miss, TTL, invalidar
- [ ] Criar `tests/unit/test_whatsapp_service.py` — horário comercial, rate limit por cliente

#### Cobertura mínima
- [ ] Adicionar `--cov-fail-under=70` ao `addopts` no `pyproject.toml`

#### CI/CD — GitHub Actions
- [ ] Criar `.github/workflows/ci.yml` com serviços Postgres + Redis, steps: lint, mypy, pytest
- [ ] Criar `.github/workflows/deploy.yml` com build + push de imagem Docker para registry
- [ ] Configurar secrets no GitHub: `TEST_ENCRYPTION_KEY`, `CODECOV_TOKEN`, credenciais registry

---

### 9.4 Sprint 5–6 — Observabilidade e Alertas

#### Prometheus + Grafana + Alertmanager [PIJ-205]
- [ ] Adicionar serviços `prometheus`, `grafana`, `alertmanager` ao `docker-compose.yml`
- [ ] Criar `infrastructure/docker/prometheus/prometheus.yml` com scrape do `/metrics` da API
- [ ] Criar `infrastructure/docker/prometheus/alerts.yml` com regras: `APIDown`, `TaxaErroIAAlta`, `LatenciaAlta`, `WorkerCelarySemResposta` [PIJ-206]
- [ ] Criar `infrastructure/docker/grafana/dashboards/concierge.json` com painéis de requests/min, taxa de erro, latência p95, processos monitorados

#### Sentry em produção
- [ ] Configurar `sentry_sdk.init()` no `app.py` com `FastApiIntegration`, `SqlalchemyIntegration`, `CeleryIntegration`
- [ ] Garantir `send_default_pii=False` (LGPD)
- [ ] Adicionar DSN real em `.env` de produção

#### Centralização de logs (Loki)
- [ ] Adicionar serviços `loki` e `promtail` ao docker-compose de produção
- [ ] Configurar Grafana para usar Loki como datasource

---

### 9.5 Sprint 7–8 — Infraestrutura de Produção

#### Docker
- [ ] Criar `infrastructure/docker/docker-compose.prod.yml` com resource limits (`mem_limit`, `cpus`) em todos os serviços [PIJ-211]
- [ ] Criar `infrastructure/nginx/nginx.conf` com reverse proxy HTTP→HTTPS e TLS [PIJ-212]

#### Scripts
- [x] Criar `scripts/migration/sync_sheets_to_db.py` — migrar clientes do Google Sheets para o banco PostgreSQL (com modo `--dry-run`)
- [ ] Criar `infrastructure/scripts/backup.sh` — `pg_dump` + compressão + upload S3 + retenção 30 dias [PIJ-213]

#### Secrets Management
- [ ] Documentar em `docs/guides/secrets.md` o processo de geração, rotação e armazenamento seguro de chaves

---

### 9.6 Sprint 9–10 — Resiliência e Escalabilidade

#### Dead Letter Queue
- [ ] Configurar `task_reject_on_worker_lost=True` e `task_acks_late=True` no `celery_app.py`
- [ ] Adicionar fila `dead_letter` ao `task_queues`
- [ ] Implementar lógica de redirecionar tasks para DLQ após retries esgotados

#### Circuit Breaker para APIs externas [PIJ-216]
- [ ] Adicionar `pybreaker` ao `requirements-f1.txt`
- [ ] Envolver chamadas ao JusbrasilClient e DataJudClient com `CircuitBreaker(fail_max=5, reset_timeout=60)`
- [ ] Tratar `CircuitBreakerError` no monitor de processos — fazer fallback para DataJud quando Jusbrasil circuit está aberto

#### Cache de dados jurídicos
- [ ] Implementar cache Redis para andamentos nos workers (TTL 1h) — evitar chamar Jusbrasil desnecessariamente

#### Load Testing
- [ ] Criar `tests/load/locustfile.py` com cenários: health check, histórico chat, webhook
- [ ] Validar metas: p95 < 500ms para `/chat/history`, 0% erro com 50 usuários simultâneos

---

### Resumo FASE 9

| Sprint | Prioridade | Descrição |
|--------|-----------|-----------|
| 9.1 | 🔴 Crítica | Workers funcionais — stubs e NotImplementedError bloqueiam prod |
| 9.2 | 🔴 Crítica | Segurança — CORS, webhook sem auth, secrets no git |
| 9.3 | 🟡 Alta    | Testes HTTP + CI/CD — sem isso regressões entram em main |
| 9.4 | 🟡 Alta    | Alertas e Sentry — sem isso falhas passam despercebidas |
| 9.5 | 🟡 Alta    | Infra de prod — TLS, backups, resource limits |
| 9.6 | 🟢 Média   | Resiliência — DLQ, circuit breaker, load testing |

