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

- [ ] **Criar repositório Git** — `concierge-juridico/` com `.gitignore` (Python, Node, .env, __pycache__, .pkl, .venv)
- [ ] **Criar `pyproject.toml`** — configuração do projeto Python (nome, versão, dependências base)
- [ ] **Criar `Makefile`** — comandos `make setup`, `make dev`, `make test`, `make lint`, `make migrate`
- [ ] **Criar `.env.example`** — template com todas as variáveis de ambiente necessárias:
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
  ```
- [ ] **Criar `docker-compose.yml`** em `infrastructure/docker/` — serviços: postgres:16, redis:7, evolution-api, celery-worker, celery-beat, flower, app-f1
- [ ] **Criar `Dockerfile.f1`** em `infrastructure/docker/` — imagem Python 3.12-slim, instala dependências + ffmpeg, copia código, expõe porta 8000

### 0.2 Banco de Dados Local

- [ ] **Instalar e configurar PostgreSQL 16** (local ou via Docker)
- [ ] **Instalar e configurar Redis 7** (local ou via Docker)
- [ ] **Criar database** `concierge_dev` no Postgres
- [ ] **Configurar Alembic** — `alembic init` na raiz, ajustar `alembic.ini` e `env.py` para ler `DATABASE_URL` do `.env`

### 0.3 Ferramentas de Desenvolvimento

- [ ] **Configurar `ruff`** para linting (`ruff.toml` na raiz)
- [ ] **Configurar `pytest`** (`pytest.ini` ou seção em `pyproject.toml`)
- [ ] **Configurar `pre-commit`** (`.pre-commit-config.yaml` — hooks: ruff, black, mypy)

### 0.4 Instalar Dependências Python ⚡ NOVA

- [ ] **Criar `requirements-base.txt`** — dependências compartilhadas (shared):
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
- [ ] **Criar `requirements-f1.txt`** — dependências da Feature 1:
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
  # (ffmpeg instalado via apt no Dockerfile)
  ```
- [ ] **Criar virtualenv** e instalar: `pip install -r requirements-f1.txt`
- [ ] **Verificar instalação** — rodar `python -c "import fastapi, sqlalchemy, anthropic, langgraph, celery, structlog; print('OK')"`

### 0.5 Criar `__init__.py` em Todos os Módulos ⚡ NOVA

- [ ] Criar `__init__.py` vazio em TODOS os diretórios que serão módulos Python:
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
  feature_1_ia_personalizada/workers/__init__.py
  feature_1_ia_personalizada/tests/__init__.py
  feature_1_ia_personalizada/tests/unit/__init__.py
  feature_1_ia_personalizada/tests/integration/__init__.py
  ```

### 0.6 Configurar Entry Point Uvicorn ⚡ NOVA

- [ ] **Definir comando de execução** do servidor:
  ```bash
  uvicorn feature_1_ia_personalizada.api.app:app --host 0.0.0.0 --port 8000 --reload
  ```
- [ ] Adicionar ao `Makefile` como `make dev`
- [ ] Verificar que o import funciona corretamente (pasta com underscores, não hífens)

---

## FASE 1 — SHARED (Core Compartilhado)

> Tudo em `shared/` — usado por TODAS as features.
> ⚠️ Todas as pastas usam underscores (ex: `feature_1_ia_personalizada`, não hífens).

---

### 1.1 `shared/config/`

#### `shared/config/settings.py`
- [ ] **Criar classe `Settings`** usando `pydantic_settings.BaseSettings` (pacote `pydantic-settings`, separado do pydantic desde v2)
- [ ] Campos obrigatórios:
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
  - `ENVIRONMENT: str = "development"` (development | staging | production)
  - `LOG_LEVEL: str = "INFO"`
- [ ] Implementar `model_config` com `env_file = ".env"`
- [ ] Criar instância singleton `settings = Settings()`

#### `shared/config/constants.py`
- [ ] Definir constantes globais:
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
- [ ] **Configurar `structlog`** com setup básico para uso desde a Fase 1:
  - Formato: JSON em produção, colorido em desenvolvimento
  - Processadores: adicionar timestamp, log level, caller info
  - Binding de contexto: `escritorio_id`, `cliente_id`, `request_id`
- [ ] **Criar helper `get_logger(nome_modulo)`** — retorna logger configurado
- [ ] Exemplo de uso: `logger = get_logger("shared.database")`

---

### 1.2 `shared/database/`

#### `shared/database/connection.py`
- [ ] **Criar engine SQLAlchemy** com `create_async_engine` (usar driver `asyncpg`, NOT `psycopg2`)
  - ⚠️ A `DATABASE_URL` deve usar o scheme `postgresql+asyncpg://` (não `postgresql://`)
- [ ] Configurar pool: `pool_size=20`, `max_overflow=10`, `pool_timeout=30`
- [ ] Habilitar SSL se `ENVIRONMENT != "development"`
- [ ] Criar `async_session_factory` com `async_sessionmaker`

#### `shared/database/session.py`
- [ ] **Criar dependency `get_db()`** — generator assíncrono que fornece sessão e faz commit/rollback automático
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
- [ ] **Criar `Base`** — `DeclarativeBase` do SQLAlchemy
- [ ] **Criar `TimestampMixin`** — mixin com `created_at` e `updated_at` (ambos `DateTime` com timezone, `updated_at` com `onupdate=func.now()`)
- [ ] **Criar `TenantMixin`** — mixin com `escritorio_id: int` (FK para tabela `escritorios`) para isolamento multi-tenant

#### `shared/models/escritorio.py`
- [ ] **Criar model `Escritorio`** (tabela `escritorios`):
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
- [ ] Criar índice único em `cnpj`

#### `shared/models/cliente.py`
- [ ] **Criar model `Cliente`** (tabela `clientes`):
  - `id: int` (PK)
  - `escritorio_id: int` (FK `escritorios.id`, not null)
  - `nome: str` (max 200, not null)
  - `cpf: str` (max 14, not null) — criptografado em repouso
  - `email: str` (max 200, nullable)
  - `telefone_whatsapp: str` (max 20, not null) — formato 5511999999999
  - `ativo: bool` (default True)
  - `aceite_lgpd: bool` (default False)
  - `data_aceite_lgpd: datetime` (nullable)
  - `preferencia_horario_notificacao: str` (default "comercial") — comercial | qualquer | silencioso
  - Herda `TimestampMixin`, `TenantMixin`
- [ ] Criar índice composto `(escritorio_id, cpf)` unique
- [ ] Criar índice em `telefone_whatsapp`

#### `shared/models/processo.py`
- [ ] **Criar model `Processo`** (tabela `processos`):
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
- [ ] Criar índice único em `(escritorio_id, numero_cnj)`
- [ ] Criar índice em `cliente_id`
- [ ] Criar índice em `status`

#### `shared/models/usuario.py`
- [ ] **Criar model `Usuario`** (tabela `usuarios`):
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
- [ ] Criar índice único em `email`

#### `shared/models/interacao.py`
- [ ] **Criar model `Interacao`** (tabela `interacoes`):
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
  - `metadata_json: JSON` (nullable) — dados extras (ID mensagem WhatsApp, etc)
  - Herda `TimestampMixin`, `TenantMixin`
- [ ] Criar índice em `(escritorio_id, cliente_id)`
- [ ] Criar índice em `created_at` — para queries de analytics
- [ ] Configurar particionamento por mês (se volume alto)

#### `shared/models/__init__.py`
- [ ] Exportar todos os models: `Base, Escritorio, Cliente, Processo, Usuario, Interacao`

---

### 1.4 `shared/schemas/`

#### `shared/schemas/escritorio.py`
- [ ] `EscritorioCreate` — campos para criação (nome, cnpj, email, telefone, oab_responsavel, nome_responsavel)
- [ ] `EscritorioUpdate` — todos opcionais (partial update)
- [ ] `EscritorioResponse` — resposta da API (inclui id, created_at, exclui dados sensíveis)
- [ ] `EscritorioList` — resposta paginada (items, total, page, per_page)

#### `shared/schemas/cliente.py`
- [ ] `ClienteCreate` — nome, cpf, telefone_whatsapp, email (opcional)
- [ ] `ClienteUpdate` — todos opcionais
- [ ] `ClienteResponse` — resposta com CPF mascarado (***.***.***-XX)
- [ ] `ClienteAceiteLGPD` — schema para registrar aceite LGPD

#### `shared/schemas/processo.py`
- [ ] `ProcessoCreate` — numero_cnj, cliente_id, polo_cliente, tipo_acao (opcional)
- [ ] `ProcessoUpdate` — todos opcionais
- [ ] `ProcessoResponse` — inclui dados do último andamento
- [ ] `ProcessoComAndamentos` — resposta com lista de andamentos recentes
- [ ] `AndamentoSchema` — data, descricao, tipo

#### `shared/schemas/usuario.py`
- [ ] `UsuarioCreate` — nome, email, senha, role, oab (opcional)
- [ ] `UsuarioLogin` — email, senha
- [ ] `UsuarioResponse` — sem senha_hash
- [ ] `TokenResponse` — access_token, refresh_token, token_type, expires_in

#### `shared/schemas/response.py`
- [ ] `SuccessResponse` — {success: bool, message: str, data: Any}
- [ ] `ErrorResponse` — {success: false, error: str, detail: str | None}
- [ ] `PaginatedResponse` — {items: list, total: int, page: int, per_page: int, pages: int}

---

### 1.5 `shared/security/`

#### `shared/security/jwt.py`
- [ ] **`criar_token(user_id, escritorio_id, role)`** — gera JWT com payload: sub, escritorio_id, role, exp, iat
- [ ] **`validar_token(token)`** — decodifica e valida JWT, retorna payload ou raise
- [ ] **`criar_refresh_token(user_id)`** — token de refresh com validade longa (7 dias)
- [ ] Usar `python-jose` com algoritmo HS256

#### `shared/security/encryption.py`
- [ ] **`criptografar(texto)`** — AES-256 usando `cryptography.fernet`
- [ ] **`descriptografar(texto_cifrado)`** — reverso
- [ ] **`hash_senha(senha)`** — bcrypt hash (usando pacote `bcrypt`)
- [ ] **`verificar_senha(senha, hash)`** — bcrypt verify
- [ ] **`mascarar_cpf(cpf)`** — retorna `***.***.***-XX`
- [ ] **`mascarar_telefone(tel)`** — retorna `(**) *****-XXXX`

#### `shared/security/permissions.py`
- [ ] **Criar enum `Role`** — ADMIN, ADVOGADO, ASSISTENTE, ESTAGIARIO
- [ ] **Criar dicionário de permissões** por role:
  - ADMIN: tudo
  - ADVOGADO: CRUD processos, clientes, ver interações
  - ASSISTENTE: leitura processos/clientes, criar interações
  - ESTAGIARIO: apenas leitura
- [ ] **Criar decorator/dependency `require_role(roles: list[Role])`** — verifica se o usuário autenticado tem a role necessária
- [ ] **Criar dependency `get_current_user(token)`** — extrai e valida token do header Authorization, retorna usuário
- [ ] **Criar dependency `check_tenant(user, resource)`** — verifica se o recurso pertence ao mesmo escritório do usuário

---

### 1.6 `shared/utils/`

#### `shared/utils/validators.py`
- [ ] **`validar_cpf(cpf: str) -> bool`** — valida CPF com dígitos verificadores
- [ ] **`validar_cnpj(cnpj: str) -> bool`** — valida CNPJ com dígitos verificadores
- [ ] **`validar_numero_processo(numero: str) -> bool`** — valida formato CNJ (NNNNNNN-DD.AAAA.J.TR.OOOO)
- [ ] **`validar_telefone_whatsapp(tel: str) -> bool`** — valida formato brasileiro (55 + DDD + 9 dígitos)
- [ ] **`normalizar_cpf(cpf: str) -> str`** — remove pontuação
- [ ] **`normalizar_telefone(tel: str) -> str`** — remove formatação, garante 55 + DDD + número
- [ ] **`normalizar_numero_processo(num: str) -> str`** — padroniza formato CNJ

#### `shared/utils/formatters.py`
- [ ] **`formatar_data_br(dt: datetime) -> str`** — retorna "16/02/2026 às 14:30"
- [ ] **`formatar_data_relativa(dt: datetime) -> str`** — retorna "há 3 dias", "hoje", "ontem"
- [ ] **`formatar_moeda_brl(valor: Decimal) -> str`** — retorna "R$ 1.500,00"
- [ ] **`formatar_numero_processo(num: str) -> str`** — retorna com pontuação CNJ

#### `shared/utils/lgpd.py`
- [ ] **`registrar_acesso(user_id, recurso, acao, ip)`** — loga acesso a dados sensíveis
- [ ] **`exportar_dados_cliente(cliente_id) -> dict`** — gera pacote JSON com todos os dados de um cliente (portabilidade)
- [ ] **`anonimizar_dados_cliente(cliente_id)`** — substitui dados pessoais por valores anônimos (direito ao esquecimento)
- [ ] **`verificar_aceite_lgpd(cliente_id) -> bool`** — checa se cliente aceitou termos

#### `shared/utils/audio_handler.py`
- [ ] **`converter_ogg_para_mp3(audio_bytes) -> bytes`** — converte áudio OGG do WhatsApp para MP3 (usando `pydub` + `ffmpeg`)
  - ⚠️ Dependências: `pydub` (Python) + `ffmpeg` (binário do SO — instalar via `apt install ffmpeg` no Dockerfile)
- [ ] **`transcrever_audio(audio_bytes) -> str`** — envia para OpenAI Whisper API, retorna transcrição em português
- [ ] **`validar_duracao_audio(audio_bytes) -> int`** — retorna duração em segundos, rejeita se > 120s
- [ ] Configurar timeout e retry para a API Whisper

---

### 1.7 Migrations

- [ ] **Criar migration inicial** com Alembic — `alembic revision --autogenerate -m "create_initial_tables"`
- [ ] **Validar migration** — `alembic upgrade head` no banco dev
- [ ] **Criar script `scripts/setup/init_db.py`** — roda migrations + cria tabelas
- [ ] **Criar script `scripts/setup/seed_data.py`** — insere dados de teste:
  - 1 escritório fictício
  - 3 clientes fictícios
  - 5 processos fictícios com números CNJ válidos
  - 2 usuários (admin + advogado)
- [ ] **Criar script `scripts/setup/create_admin.py`** — cria usuário admin via CLI interativo

---

## FASE 2 — FEATURE 1: API (FastAPI)

> Tudo em `feature_1_ia_personalizada/api/`
> ⚠️ Nota: o webhook WhatsApp depende do Celery (Fase 4) para processamento assíncrono. Na Fase 2, implementar com processamento **síncrono temporário** (chamar orchestrator direto). Na Fase 4, refatorar para `processar_mensagem_recebida.delay()`.

---

### 2.1 App Principal

#### `feature_1_ia_personalizada/api/app.py` (entry point)
- [ ] **Criar app FastAPI** com metadata (title, description, version)
- [ ] **Registrar routers**: auth, webhook_whatsapp, processos, chat, health
- [ ] **Registrar middlewares**: CORS, auth, rate_limit
- [ ] **Configurar event handlers**: startup (conectar DB, Redis) e shutdown (fechar conexões)
- [ ] **Configurar Sentry** se `SENTRY_DSN` presente
- [ ] **Configurar Prometheus** metrics endpoint (`/metrics`)

---

### 2.2 `feature_1_ia_personalizada/api/middleware/`

#### `auth.py`
- [ ] **Criar middleware de autenticação JWT** — intercepta requests, extrai token do header `Authorization: Bearer <token>`, valida usando `shared/security/jwt.py`
- [ ] Definir lista de rotas públicas (ex: `/webhook/whatsapp`, `/health`, `/docs`, `/auth/login`, `/auth/refresh`)
- [ ] Injetar `current_user` no request state

#### `rate_limit.py`
- [ ] **Criar middleware de rate limiting** usando Redis:
  - Webhook WhatsApp: 100 req/min por IP
  - API geral: 60 req/min por usuário
  - Endpoint chat: 30 req/min por usuário
- [ ] Retornar header `X-RateLimit-Remaining` e `429 Too Many Requests` quando exceder
- [ ] Usar sliding window com Redis (`INCR` + `EXPIRE`)

---

### 2.3 `feature_1_ia_personalizada/api/routes/`

#### `auth.py` ⚡ NOVA — Rotas de Autenticação

> Sem estas rotas, o middleware JWT não funciona (não há como obter token).

- [ ] **`POST /auth/login`** — autenticação de usuário
  - Body: `UsuarioLogin` (email, senha)
  - Buscar usuário por email no banco
  - Verificar senha com `verificar_senha()`
  - Se válido: gerar `access_token` + `refresh_token` via `shared/security/jwt.py`
  - Atualizar `ultimo_login` do usuário
  - Retornar `TokenResponse`
  - Se inválido: retornar 401
- [ ] **`POST /auth/refresh`** — renovar token expirado
  - Body: `{refresh_token: str}`
  - Validar refresh token
  - Gerar novo `access_token`
  - Retornar `TokenResponse`
- [ ] **`GET /auth/me`** — dados do usuário autenticado
  - Requer autenticação
  - Retornar `UsuarioResponse` do usuário do token

#### `health.py` ⚡ MOVIDA DA FASE 7 (básico aqui, detalhado na Fase 7)
- [ ] **`GET /health`** — health check básico (retorna 200 + `{"status": "ok"}`)
- [ ] **`GET /health/ready`** — verifica conexão DB + Redis (mínimo para saber se a API está funcional)

#### `webhook_whatsapp.py`
- [ ] **`POST /webhook/whatsapp`** — recebe mensagens da Evolution API
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
- [ ] **`POST /webhook/whatsapp/status`** — webhook de status de mensagem (entregue, lida)
  - Atualizar metadata da interação com status de entrega
- [ ] **`GET /webhook/whatsapp/health`** — health check do webhook

#### `processos.py`
- [ ] **`GET /processos`** — listar processos do escritório autenticado
  - Query params: `status`, `cliente_id`, `page`, `per_page`, `search` (busca por número CNJ ou nome cliente)
  - Filtrar por `escritorio_id` do token JWT (tenant isolation)
  - Retornar `PaginatedResponse[ProcessoResponse]`
- [ ] **`GET /processos/{id}`** — detalhes de um processo
  - Verificar que processo pertence ao escritório
  - Retornar `ProcessoComAndamentos` (com últimos 10 andamentos)
- [ ] **`POST /processos`** — cadastrar novo processo
  - Validar `numero_cnj` com `validar_numero_processo()`
  - Verificar que `cliente_id` pertence ao escritório
  - Buscar dados iniciais no Jusbrasil (tribunal, vara, tipo_ação)
  - ⚠️ **Dependência**: requer `jusbrasil_client.py` da Fase 3.3. Se implementar antes, usar dados manuais como fallback temporário.
  - Ativar monitoramento automático
  - Retornar `ProcessoResponse`
- [ ] **`PUT /processos/{id}`** — atualizar processo
  - Campos atualizáveis: polo_cliente, advogado_responsavel_id, monitoramento_ativo, frequencia_monitoramento
- [ ] **`DELETE /processos/{id}`** — soft delete (status = "encerrado", monitoramento_ativo = False)
- [ ] **`POST /processos/{id}/sincronizar`** — forçar sincronização com Jusbrasil agora

#### `chat.py`
- [ ] **`GET /chat/history/{cliente_id}`** — histórico de conversas com um cliente
  - Query params: `page`, `per_page`, `data_inicio`, `data_fim`
  - Retornar interações ordenadas por data
- [ ] **`POST /chat/send`** — enviar mensagem proativa para cliente
  - Body: `{cliente_id, mensagem, processo_id (opcional)}`
  - Enviar via WhatsApp (Evolution API)
  - Registrar interação (direção: saída, tipo: sistema)
- [ ] **`GET /chat/stats`** — estatísticas de interações do escritório
  - Total interações (mês), tempo médio resposta, custo total IA, NPS médio

---

## FASE 3 — FEATURE 1: SERVICES (Lógica de Negócio)

> Tudo em `feature_1_ia_personalizada/services/`

---

### 3.1 `services/ai/` — Orquestração de IA

#### `services/ai/prompts.py`
- [ ] **Criar `SYSTEM_PROMPT_BASE`** — prompt de sistema principal do Claude:
  - Persona: assistente jurídico digital do escritório {nome}
  - Tom: profissional mas acessível, empático, paciente
  - Idioma: português brasileiro, evitar juridiquês
  - Regras OAB: NUNCA dar pareceres, NUNCA prever resultados, NUNCA sugerir estratégias
  - Quando não souber: "Vou verificar com o advogado responsável e retorno"
  - Sempre incluir disclaimer quando relevante
  - Formato: mensagens curtas (WhatsApp), usar emojis com moderação (📋, ⚖️, 📅)
- [ ] **Criar `SYSTEM_PROMPT_STATUS_PROCESSO`** — prompt específico para consultas de status:
  - Contexto: dados do processo (número, tribunal, último andamento)
  - Instrução: traduzir andamento para linguagem leiga
  - Formato: resumo + explicação + próximos passos previstos
- [ ] **Criar `SYSTEM_PROMPT_TRADUZIR_TERMO`** — prompt para tradução de termos jurídicos:
  - Instrução: explicar como se fosse para uma pessoa sem formação jurídica
  - Usar analogias do cotidiano quando possível
- [ ] **Criar `SYSTEM_PROMPT_BOAS_VINDAS`** — prompt para onboarding de novo cliente
- [ ] **Criar `SYSTEM_PROMPT_SEM_MOVIMENTACAO`** — prompt para quando não há movimentação:
  - Contexto: dias sem movimentação, estágio atual
  - Instrução: explicar que inatividade é normal, contextualizar por que demora
- [ ] **Criar `SYSTEM_PROMPT_PESQUISA_SATISFACAO`** — prompt para NPS:
  - Perguntar de 1 a 5 como avalia o atendimento
  - Tom casual e rápido

#### `services/ai/claude_client.py`
- [ ] **Criar classe `ClaudeClient`**:
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
- [ ] **Criar classe `ConversationMemory`**:
  - `__init__(redis_client)` — conexão Redis
  - `async salvar_mensagem(escritorio_id, cliente_id, role, content)` — salva em Redis list `conv:{escritorio_id}:{cliente_id}`
  - `async buscar_historico(escritorio_id, cliente_id, limite=20) -> list[dict]` — retorna últimas N mensagens no formato `[{role, content}]`
  - `async limpar_historico(escritorio_id, cliente_id)` — deleta conversa
  - **TTL de 24 horas** por conversa (após 24h sem interação, histórico expira — nova conversa)
  - **Limite de 50 mensagens** por conversa (FIFO — remove as mais antigas)
  - Serialização: JSON compacto

#### `services/ai/translator.py`
- [ ] **Criar classe `JuridicalTranslator`**:
  - `__init__()` — carregar dicionário de `data/termos_juridicos/traducoes.json`
  - `traduzir_termo(termo: str) -> str | None` — busca no dicionário local (O(1) com dict)
  - `traduzir_andamento(texto_andamento: str) -> str` — usa Claude para traduzir andamento completo
  - `identificar_termos_tecnicos(texto: str) -> list[str]` — regex + NLP leve para achar termos jurídicos no texto
- [ ] **Criar arquivo `data/termos_juridicos/traducoes.json`** com 50 termos iniciais (MVP):
  - "sentença" → "Decisão final do juiz sobre o seu caso"
  - "agravo de instrumento" → "Recurso contra uma decisão parcial do juiz"
  - "tutela antecipada" → "Pedido para o juiz decidir algo antes do julgamento final"
  - "citação" → "Comunicação oficial informando que existe um processo"
  - "contestação" → "Resposta da parte contrária ao processo"
  - (+ 45 termos mais comuns)

#### `services/ai/fact_checker.py`
- [ ] **Criar classe `FactChecker`**:
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
- [ ] **Criar workflow LangGraph** com os seguintes nós (states):

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
  - [ ] Recebe mensagem do cliente
  - [ ] Usa Claude (prompt curto) para classificar intenção: status, duvida_termo, agendamento, saudacao, reclamacao, outro
  - [ ] Se intenção = saudacao → vai direto para `gerar_resposta` (sem consultar processo)
  - [ ] Se intenção tem a ver com processo → vai para `buscar_dados`
  - [ ] ⚡ **Se Claude falhar aqui**: usar classificação por keywords como fallback (regex simples: "status|andamento|processo" → status, "significa|quer dizer" → duvida_termo, etc.)

  **Nó 2: `buscar_dados`**
  - [ ] Identifica qual processo o cliente está perguntando:
    - Se cliente tem 1 processo → usa esse
    - Se cliente tem vários → pergunta qual
    - Se mencionou número → busca pelo número
    - ⚡ **Se cliente tem 0 processos** → responder: "Não encontrei processos vinculados ao seu cadastro. Entre em contato com o escritório para verificar." → pular para `enviar_resposta`
  - [ ] Consulta cache Redis primeiro
  - [ ] Se cache miss → chama Jusbrasil API
  - [ ] Salva no state `dados_processo`

  **Nó 3: `gerar_resposta`**
  - [ ] Monta system_prompt baseado na intenção
  - [ ] Injeta dados do processo no prompt (se houver)
  - [ ] Injeta histórico de conversa (memória Redis)
  - [ ] Chama Claude via `ClaudeClient`
  - [ ] Salva resposta no state
  - [ ] ⚡ **Se Claude estiver fora do ar** (após retries): ativar `usando_fallback = True`, usar mensagens pré-definidas de `constants.MENSAGENS_FALLBACK`:
    - status → "Recebemos sua mensagem sobre o processo {numero}. No momento estou com dificuldades técnicas, mas o escritório retornará em breve."
    - duvida_termo → "Obrigado pela pergunta! Estou com uma dificuldade técnica temporária. Encaminhei sua dúvida ao escritório."
    - saudacao → "Olá! No momento estou passando por uma manutenção rápida. O escritório entrará em contato em breve."
    - outro → mensagem genérica de indisponibilidade

  **Nó 4: `verificar_resposta`**
  - [ ] **Se `usando_fallback = True`**: pular verificação (mensagem pré-definida é segura), ir para `enviar_resposta`
  - [ ] Chama `FactChecker.verificar_status_processo()` se resposta mencionou dados do processo
  - [ ] Chama `FactChecker.filtrar_resposta()` para sanitizar
  - [ ] Se houve correção e `tentativas_correcao < 2` → incrementar contador, regenerar resposta
  - [ ] Se houve correção e `tentativas_correcao >= 2` → enviar mensagem de fallback

  **Nó 5: `enviar_resposta`**
  - [ ] Envia resposta final via WhatsApp (Evolution API)
  - [ ] Salva interação completa no banco (Interacao model)
  - [ ] Atualiza memória de conversa (Redis)
  - [ ] Emite métrica Prometheus
  - [ ] Se `usando_fallback = True`: registrar em metadata e disparar alerta para admin

  **Nó 6: `tratar_erro`** ⚡ NOVO — Implementação completa
  - [ ] Recebe o state com `erro` preenchido
  - [ ] Logar erro completo com stack trace (structlog)
  - [ ] Enviar mensagem genérica ao cliente: "Desculpe, estou com uma dificuldade técnica. Encaminhei sua mensagem para o escritório."
  - [ ] Disparar notificação para admin/advogado responsável:
    - Via WhatsApp (se configurado) ou log de alta prioridade
    - Conteúdo: cliente_id, mensagem original, erro ocorrido, timestamp
  - [ ] Salvar interação no banco com `metadata_json: {erro: true, tipo_erro: "...", stack: "..."}`
  - [ ] Emitir métrica Prometheus `ia_errors_total`

  **Edges (transições):**
  - [ ] `classificar_intencao` → `buscar_dados` (se precisa de dados)
  - [ ] `classificar_intencao` → `gerar_resposta` (se saudação/geral)
  - [ ] `buscar_dados` → `gerar_resposta` (se achou dados)
  - [ ] `buscar_dados` → `enviar_resposta` (se cliente tem 0 processos — resposta já definida)
  - [ ] `gerar_resposta` → `verificar_resposta`
  - [ ] `verificar_resposta` → `enviar_resposta` (se OK ou fallback)
  - [ ] `verificar_resposta` → `gerar_resposta` (se precisou corrigir, max 2 loops)
  - [ ] Qualquer nó com exceção não tratada → `tratar_erro`

---

### 3.2 `services/messaging/` — WhatsApp

#### `services/messaging/evolution_client.py`
- [ ] **Criar classe `EvolutionClient`**:
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
- [ ] **Criar classe `WhatsAppService`** (wrapper de alto nível):
  - `__init__(evolution_client, db_session)` — dependências
  - `async enviar_mensagem(escritorio_id, cliente_id, texto, processo_id=None)` — resolve instância do escritório, envia via EvolutionClient, salva Interacao
  - `async enviar_notificacao_andamento(processo_id, andamento)` — monta mensagem de atualização e envia para o cliente do processo
  - `async enviar_boas_vindas(escritorio_id, cliente_id)` — envia disclaimer OAB + mensagem de boas-vindas
  - `async enviar_pesquisa_satisfacao(escritorio_id, cliente_id)` — envia pesquisa NPS (botões 1-5)
  - `async enviar_sem_movimentacao(processo_id)` — mensagem explicando inatividade do processo
  - **Respeitar horário**: verificar `preferencia_horario_notificacao` do cliente — se "comercial", só enviar entre 8h-18h (agendar se fora)
  - **Rate limit por cliente**: máximo 5 mensagens/dia por cliente (exceto respostas a perguntas)

#### `services/messaging/templates.py`
- [ ] **Criar templates de mensagens** (strings formatáveis):
  - `TEMPLATE_BOAS_VINDAS` — com disclaimer OAB, apresentação, o que a IA pode fazer
  - `TEMPLATE_NOVO_ANDAMENTO` — "📋 Atualização no seu processo {numero}! {resumo_traduzido}"
  - `TEMPLATE_SEM_MOVIMENTACAO` — "Olá! Sobre o processo {numero}, informo que..."
  - `TEMPLATE_PESQUISA_NPS` — "Como você avalia nosso atendimento? (1-5)"
  - `TEMPLATE_ERRO_GENERICO` — "Desculpe, estou com dificuldade. Vou encaminhar para o escritório."
  - `TEMPLATE_CLIENTE_NAO_ENCONTRADO` — "Olá! Não encontrei seu cadastro..."
  - `TEMPLATE_AGENDAMENTO_CONFIRMADO` — "Consulta agendada com Dr(a). {nome} para {data}"
  - `TEMPLATE_CLIENTE_SEM_PROCESSO` — ⚡ NOVO — "Não encontrei processos vinculados ao seu cadastro..."

#### `services/messaging/scheduler.py`
- [ ] **Criar classe `MessageScheduler`**:
  - `agendar_mensagem(escritorio_id, cliente_id, texto, horario_envio: datetime)` — salva tarefa no Celery com ETA
  - `cancelar_agendamento(task_id)` — cancela tarefa Celery
  - `listar_agendamentos(escritorio_id) -> list` — lista mensagens pendentes
  - Lógica de horário comercial: se mensagem gerada fora do horário, agendar para próximo horário válido (ex: 20h → agenda para 8h do dia seguinte)

---

### 3.3 `services/legal_data/` — Dados Processuais

#### `services/legal_data/jusbrasil_client.py`
- [ ] **Criar classe `JusbrasilClient`**:
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
- [ ] **Criar classe `DataJudClient`** (fallback):
  - `__init__()` — sem API key (gratuito)
  - `async buscar_processo(numero_cnj: str) -> dict | None` — consulta DataJud CNJ
  - `async buscar_andamentos(numero_cnj: str) -> list[dict]`
  - Mesma interface que JusbrasilClient (Strategy Pattern)
  - Nota: dados menos ricos, mais lento

#### `services/legal_data/data_cleaner.py`
- [ ] **Criar classe `DataCleaner`**:
  - `limpar_andamento(texto_bruto: str) -> str` — remove HTML, caracteres especiais, normaliza espaços
  - `extrair_data_andamento(texto: str) -> datetime | None` — regex para achar datas no texto
  - `classificar_tipo_andamento(texto: str) -> str` — classifica: despacho, sentença, decisão, petição, certidão, audiência, outro
  - `detectar_urgencia(texto: str) -> bool` — detecta termos urgentes: "intimação", "prazo fatal", "citação"

#### `services/legal_data/cache_manager.py`
- [ ] **Criar classe `CacheManager`**:
  - `__init__(redis_client)` — conexão Redis
  - `async get_processo(numero_cnj: str) -> dict | None` — busca cache `proc:{numero_cnj}`
  - `async set_processo(numero_cnj: str, dados: dict)` — salva com TTL 1 hora
  - `async get_andamentos(numero_cnj: str) -> list | None` — busca cache `and:{numero_cnj}`
  - `async set_andamentos(numero_cnj: str, dados: list)` — salva com TTL 30 min
  - `async invalidar_processo(numero_cnj: str)` — deleta cache do processo e andamentos
  - Usar prefixos de chave para namespace: `f1:proc:{numero}`, `f1:and:{numero}`

---

## FASE 4 — FEATURE 1: WORKERS (Celery)

> Tudo em `feature_1_ia_personalizada/workers/`

---

#### `workers/celery_app.py`
- [ ] **Configurar Celery app**:
  - Broker: Redis (`CELERY_BROKER_URL`)
  - Result backend: Redis (`CELERY_RESULT_BACKEND`)
  - Serializer: JSON
  - Task routes: definir filas separadas (`monitoramento`, `notificacoes`, `ia`)
  - Beat schedule:
    - `monitorar-processos`: a cada 6 horas (06h, 12h, 18h, 00h)
    - `enviar-sem-movimentacao`: semanal (segunda, 10h)
    - `pesquisa-satisfacao`: mensal (dia 1, 14h)
    - `limpar-cache-expirado`: diário (03h)

#### `workers/monitor_processos.py`
- [ ] **Criar task `monitorar_todos_processos()`**:
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

- [ ] **Criar task `monitorar_processo_individual(processo_id)`**:
  - Mesma lógica, mas para um processo específico (chamado pelo endpoint `POST /processos/{id}/sincronizar`)

#### `workers/send_notifications.py`
- [ ] **Criar task `enviar_notificacao_andamento(processo_id, andamento_traduzido)`**:
  - Buscar processo + cliente
  - Verificar horário permitido (se fora, reagendar)
  - Montar mensagem usando `TEMPLATE_NOVO_ANDAMENTO`
  - Enviar via `WhatsAppService`
  - Registrar interação

- [ ] **Criar task `enviar_lote_sem_movimentacao()`**:
  - Buscar processos sem movimentação há mais de 30 dias
  - Para cada: enviar mensagem explicativa via `WhatsAppService`
  - Limite: 1 mensagem de "sem movimentação" por processo a cada 30 dias

- [ ] **Criar task `enviar_pesquisa_satisfacao_lote()`**:
  - Buscar clientes que interagiram no último mês e não responderam pesquisa
  - Enviar pesquisa NPS via WhatsApp (botões 1-5)
  - Limite: 1 pesquisa por cliente por mês

- [ ] **Criar task `processar_mensagem_recebida(escritorio_id, cliente_id, mensagem, tipo)`**:
  - Task principal chamada pelo webhook (após refatoração da Fase 2)
  - Instancia o orchestrator LangGraph
  - Executa workflow completo
  - Em caso de erro: envia mensagem genérica + notifica admin

#### Refatoração do Webhook ⚡ NOVA
- [ ] **Refatorar `webhook_whatsapp.py`** para usar Celery:
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
- [ ] Criar JSON com disclaimers:
  ```json
  {
    "primeiro_contato": "Olá! Sou a assistente digital do escritório {escritorio}...",
    "antes_informacao_processual": "Lembrando que sou uma assistente digital...",
    "quando_perguntam_conselho": "Entendo sua dúvida! Porém, como assistente digital, não posso dar orientações jurídicas..."
  }
  ```

#### `data/termos_juridicos/traducoes.json`
- [ ] Criar JSON com **50 termos** iniciais (MVP) e traduções — formato:
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
- [ ] Testar classificação de intenção (mock Claude): mensagem "qual o status?" → intenção "status"
- [ ] Testar classificação: "o que significa sentença?" → intenção "duvida_termo"
- [ ] Testar classificação: "bom dia" → intenção "saudacao"
- [ ] Testar fluxo completo com mocks (Claude + Jusbrasil + Redis)
- [ ] Testar comportamento quando Claude falha (retry + fallback para mensagem pré-definida)
- [ ] Testar loop de verificação (max 2 correções)
- [ ] ⚡ **Testar cliente com 0 processos** — deve retornar mensagem "não encontrei processos" sem chamar Claude
- [ ] ⚡ **Testar nó `tratar_erro`** — simular exceção em qualquer nó, verificar que mensagem genérica é enviada e admin notificado
- [ ] ⚡ **Testar fallback de classificação por keywords** — quando Claude está fora, regex classifica corretamente

#### `test_translator.py`
- [ ] Testar tradução de termo existente no dicionário
- [ ] Testar tradução de termo inexistente (fallback para Claude)
- [ ] Testar identificação de termos jurídicos em texto livre
- [ ] Testar com termos em maiúscula/minúscula

#### `test_fact_checker.py`
- [ ] Testar verificação de número de processo correto → `verificado: True`
- [ ] Testar verificação de número de processo incorreto → `verificado: False, correcoes: [...]`
- [ ] Testar filtro de linguagem proibida ("você deve fazer X" → removido)
- [ ] Testar que linguagem permitida passa sem alteração

#### `test_validators.py` (em shared)
- [ ] CPF válido → True; CPF inválido → False; CPF com pontuação → True
- [ ] CNPJ válido → True; CNPJ inválido → False
- [ ] Número processo CNJ válido → True; formato errado → False
- [ ] Telefone com 55+DDD+9 dígitos → True; sem 55 → False

#### `test_encryption.py` ⚡ NOVO (em shared)
- [ ] Testar `criptografar` → `descriptografar` retorna texto original
- [ ] Testar com texto vazio
- [ ] Testar com caracteres especiais (acentos, emojis)
- [ ] Testar `hash_senha` → `verificar_senha` retorna True
- [ ] Testar `verificar_senha` com hash errado → False
- [ ] Testar `mascarar_cpf` com CPF válido → formato `***.***.***-XX`
- [ ] Testar `mascarar_telefone` com telefone válido → formato `(**) *****-XXXX`

#### `test_evolution_client.py`
- [ ] Testar envio de texto (mock HTTP) → verifica payload correto
- [ ] Testar retry em caso de timeout
- [ ] Testar tratamento de erro 4xx/5xx

#### `test_jusbrasil_client.py`
- [ ] Testar busca de processo existente (mock) → retorna dados
- [ ] Testar busca de processo inexistente → retorna None
- [ ] Testar busca de andamentos → retorna lista
- [ ] Testar fallback para DataJud quando Jusbrasil falha

#### `test_memory.py` ⚡ NOVO
- [ ] Testar salvar e buscar mensagem → retorna corretamente
- [ ] Testar TTL de 24 horas → após expiração, histórico vazio
- [ ] Testar limite de 50 mensagens → FIFO, mais antigas removidas
- [ ] Testar `limpar_historico` → histórico vazio após limpeza
- [ ] Testar com múltiplos clientes → históricos isolados

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

#### `test_auth_flow.py` ⚡ NOVO
- [ ] Testar login com credenciais válidas → retorna tokens
- [ ] Testar login com senha errada → 401
- [ ] Testar login com email inexistente → 401
- [ ] Testar refresh token → novo access_token
- [ ] Testar acesso a rota protegida com token válido → 200
- [ ] Testar acesso a rota protegida sem token → 401
- [ ] Testar acesso com token expirado → 401

### 6.3 Configuração de Testes

#### `tests/conftest.py`
- [ ] Fixtures pytest:
  - `db_session` — sessão de banco de teste (transacional, rollback após cada teste)
  - `redis_client` — Redis de teste (flush após cada teste)
  - `mock_claude` — mock do ClaudeClient
  - `mock_evolution` — mock do EvolutionClient
  - `mock_jusbrasil` — mock do JusbrasilClient
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
- [ ] Registrar métricas:
  - `Counter: whatsapp_messages_received_total` (labels: escritorio_id, tipo)
  - `Counter: whatsapp_messages_sent_total` (labels: escritorio_id, tipo)
  - `Counter: ia_requests_total` (labels: intencao, sucesso)
  - `Counter: ia_errors_total` (labels: tipo_erro)
  - `Counter: ia_fallback_used_total` — ⚡ NOVO — conta vezes que fallback foi ativado
  - `Histogram: ia_response_time_seconds`
  - `Histogram: webhook_processing_time_seconds`
  - `Gauge: processos_monitorados_total`
  - `Counter: ia_tokens_consumed_total` (labels: tipo=input|output)
  - `Counter: jusbrasil_requests_total` (labels: endpoint, status)
  - `Counter: fact_check_corrections_total`

### 7.2 Logging Estruturado

- [ ] ⚡ Logging base já configurado na Fase 1 (`shared/config/logging.py`). Aqui, expandir:
- [ ] Adicionar middleware de request logging (log de cada request com request_id, método, path, status, latência)
- [ ] Logs obrigatórios (validar que todos estão presentes):
  - Toda interação com Claude (tokens, latência, modelo)
  - Todo acesso a dados de cliente (LGPD audit trail)
  - Toda mensagem WhatsApp enviada/recebida
  - Toda consulta Jusbrasil
  - Todos os erros com stack trace
  - Todo uso de fallback (quando Claude está fora)

### 7.3 Health Checks Detalhados

#### `feature_1_ia_personalizada/api/routes/health.py` (expandir o criado na Fase 2)
- [ ] **`GET /health/detailed`** — verifica:
  - Conexão PostgreSQL (SELECT 1)
  - Conexão Redis (PING)
  - Conectividade Claude API (HEAD)
  - Conectividade Evolution API (status da instância)
  - Status workers Celery

---

## FASE 8 — DEPLOY INICIAL

---

### 8.1 Docker

- [ ] Criar `Dockerfile.f1` otimizado (multi-stage build, inclui `ffmpeg`)
- [ ] Criar `docker-compose.yml` com todos os serviços
- [ ] Testar `docker compose up` funcionando localmente
- [ ] Criar `docker-compose.prod.yml` com variáveis de produção

### 8.2 Scripts de Setup

#### `scripts/setup/init_db.py`
- [ ] Roda Alembic migrations
- [ ] Verifica conexão com PostgreSQL
- [ ] Verifica conexão com Redis

#### `scripts/setup/seed_data.py`
- [ ] Popula dados de demonstração

#### `scripts/monitoring/health_check.py`
- [ ] Script standalone que verifica saúde de todos os serviços
- [ ] Retorna exit code 0 (OK) ou 1 (falha) — usável em CI/CD

---

## RESUMO: ORDEM DE EXECUÇÃO RECOMENDADA

| Fase | Prioridade | Estimativa | Descrição |
|------|-----------|------------|-----------|
| 0    | 🔴 Crítica | 1-2 dias   | Setup projeto, Docker, .env, deps, __init__.py |
| 1    | 🔴 Crítica | 3-4 dias   | Shared: models, schemas, security, utils, DB, logging base |
| 2    | 🔴 Crítica | 3-4 dias   | API: auth, webhook, processos, chat, health + middleware |
| 3.1  | 🔴 Crítica | **6-7 dias** | Services AI: orchestrator (6 nós), claude_client, prompts, memory, fact_checker, fallbacks |
| 3.2  | 🔴 Crítica | 2-3 dias   | Services Messaging: evolution_client, whatsapp, templates |
| 3.3  | 🟡 Alta    | 2-3 dias   | Services Legal Data: jusbrasil, datajud, cache |
| 4    | 🟡 Alta    | 2-3 dias   | Workers Celery: monitoramento, notificações, refatoração webhook |
| 5    | 🟢 Média   | 1 dia      | Dados estáticos: disclaimers, 50 termos jurídicos |
| 6    | 🟡 Alta    | **4-5 dias** | Testes unitários (12 arquivos) + integração (3 fluxos) |
| 7    | 🟢 Média   | 1-2 dias   | Monitoramento: Prometheus, logging expandido, health detalhado |
| 8    | 🟡 Alta    | 1-2 dias   | Deploy Docker local completo |
| **TOTAL** | | **~28-35 dias** | **Para 1 desenvolvedor senior full-time** |

---

> **Nota:** Estimativa revisada de 22-30 → **28-35 dias** após validação. A Fase 3.1 (orchestrator LangGraph com 6 nós + fallbacks + error handling) é a mais complexa e foi reestimada de 4-5 → 6-7 dias. Com 2 devs, as fases podem ser paralelizadas (ex: um faz Shared/API enquanto o outro faz Services AI). A ordem das fases é sequencial por dependência — não é possível fazer a Fase 3 sem a Fase 1 completa.
>
> **Dependências críticas entre fases:**
> - Fase 2 (API) depende de Fase 1 (Shared) completa
> - Fase 2 `POST /processos` depende de Fase 3.3 `jusbrasil_client.py` (usar stub temporário)
> - Fase 2 webhook depende de Fase 4 para processamento assíncrono (usar síncrono temporário)
> - Fase 3.1 orchestrator depende de Fase 3.2 (messaging) e 3.3 (legal_data)
> - Fase 4 (Workers) pode ser feita em paralelo com Fase 3.2/3.3
