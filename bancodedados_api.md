# Documentação do Backend: Banco de Dados e API (Fase 1 e Início da Fase 2)

Este documento centraliza tudo o que já foi construído até o momento para o backend do **Concierge Jurídico Digital**, detalhando a responsabilidade de cada arquivo e o planejamento dos próximos passos.

---

## 1. O Que Já Fizemos (Concluído)

Até agora, completamos a infraestrutura fundacional: O **Banco de Dados**, as **Conexões Assíncronas**, a **Segurança** e o esqueleto da **API FastAPI**.

### 1.1 Modelos do Banco de Dados (ORM SQLAlchemy)
A base do projeto, onde definimos as tabelas no PostgreSQL. Tudo feito em `shared/models/`.

*   **`shared/models/base.py`**: Define a classe `Base` do SQLAlchemy e dois mixins essenciais:
    *   `TimestampMixin`: Adiciona `created_at` e `updated_at` automaticamente.
    *   `TenantMixin`: Adiciona `escritorio_id` para garantir o isolamento dos dados (multi-tenant).
*   **`shared/models/escritorio.py`**: Tabela principal. Armazena os dados do escritório de advocacia, seus limites de plano e configurações de WhatsApp (Evolution API).
*   **`shared/models/usuario.py`**: Tabela para os advogados e assistentes (usuários internos do painel). Possui campo `senha_hash` (bcrypt) e controle de roles (admin, advogado, assistente).
*   **`shared/models/cliente.py`**: A tabela dos clientes finais (que usarão o bot). Tem campos essenciais para a IA como data de nascimento, profissão e o **CPF criptografado** usando AES-256 (Fernet).
*   **`shared/models/processo.py`**: Tabela que vincula o cliente aos processos reais com o identificador `numero_cnj`. Tem flags para o Celery saber quais processos monitorar ativamente.
*   **`shared/models/interacao.py`**: O coração do log da IA. Guarda todas as conversas, quantidade de tokens de I.A. consumidos, custos estimados, e o texto das mensagens.
*   **`shared/models/__init__.py`**: Junta todos os arquivos acima para que a biblioteca de migração (Alembic) consiga ler todas as tabelas de uma só vez.

### 1.2 Conexão com o Banco de Dados
A ponte assíncrona para que a API consiga fazer várias coisas ao mesmo tempo sem travar. Feito em `shared/database/`.

*   **`shared/database/connection.py`**: Configura a **Async Engine** usando o driver `asyncpg`. Define regras de performance como o pool de conexões (máximo de sessões aguardando, simultaneidade, etc).
*   **`shared/database/session.py`**: Contém o `get_db()`. É um recurso do FastAPI chamado *Dependency Tracker*. Sempre que a API precisa acessar o banco, ela pede esta sessão. Se a requisição der certo, ela faz `commit()` automático. Se der erro, faz `rollback()`.

### 1.3 Segurança e Autenticação
A blindagem da nossa API contra acessos indevidos. Feito em `shared/security/`.

*   **`shared/security/encryption.py`**: Módulo que traz o Bcrypt para hashear as senhas de usuários e o pacote Fernet para proteger dados como o CPF. Inclui métodos úteis para mascarar os dados na hora de enviar pro front (ex: `***.***.***-XX`).
*   **`shared/security/jwt.py`**: Motor que emite os `Access Tokens` (rápidos) e `Refresh Tokens` (longos) pro sistema logar os usuários assíncronamente.
*   **`shared/security/permissions.py`**: Os "guardas de trânsito" da API:
    *   `get_current_user`: Lê o JWT que o usuário envia e puxa do banco pra saber se ele ainda tem acesso válido.
    *   `require_role`: Bloqueia chamadas de rotas de acordo com a Hierarquia da Role do usuário logado.

### 1.4 API: Aplicativo Principal e Roteamento Preliminar
O servidor web propriamente dito usando FastAPI, feito na pasta `feature_1_ia_personalizada/api/`.

*   **`api/app.py`**: O arquivo mestre. Configura a inicialização, ajusta CORS para permitir acessos web, prepara o esqueleto do "Lifespan" (startup e shutdown commands para plugar no Redis/PostgreSQL).
*   **Roteadores Base**: Criamos os 5 roteadores vazios (apenas as URLs) em `api/routes/` para já deixar o app principal com a arquitetura final. São eles: `auth`, `chat`, `health`, `processos`, `webhook_whatsapp`.

### 1.5 Rota Realizada (Fase 2C)
*   **`api/routes/health.py`**: Criamos a rota de monitoramento real.
    *   Acessando o sistema, o endpoint de health faz **pings síncronos**: testa o SQLAlchemy batendo no Postgres via async, e testa o pool do Redis via `redis.asyncio` usando a ENV URL. Traz ms e logs.

### 1.6 Middlewares Globais da API (Fase 2B)
Os "porteiros" do nosso backend, implementados em `api/middleware/`:
*   **`auth.py (JWTAuthMiddleware)`**: Intercepta as requisições, exige o Header `Authorization: Bearer <token>` em rotas protegidas e injeta o Payload do usuário.
*   **`rate_limit.py (RateLimitMiddleware)`**: Limita acesso por IP (rotas públicas) ou Usuário (rotas privadas) usando o Redis em memória, prevenindo spam e ataques de força bruta.

### 1.7 Schemas, Utils, Alembic e Configs Adicionais (Git Pull Anterior)
Arquivos complementares vindos do repositório:
*   **Logging (`shared/config/logging.py`)**: Estrutura avançada com `structlog` para logs estruturados em JSON.
*   **Base de Conhecimento (`data/`)**: JSONs com regras de negócio da IA (datas comemorativas, dicas, traduções de juridiquês e disclaimers obrigatórios).
*   **Schemas (`shared/schemas/`)**: Pydantic para validação de entrada de dados da API.
*   **Utils (`shared/utils/`)**: Conversores de data, formatadores, etc.
*   **Alembic (`alembic/`) e Scripts**: Migration 001 gerada para os nossos Models.

### 1.8 Processamento Assíncrono e Workers Inteligentes (Git Pull Recente)
A base para as automações (Phase 4) foi incluída através da stack do **Celery**, localizada em `feature_1_ia_personalizada/workers/`:
*   **`celery_app.py`**: O inicializador do Celery que conecta no Redis para enfileirar tarefas pesadas.
*   **`mensagens_relacionamento.py`**: Disparo de felicitações e lembretes baseados nos dados dos clientes (LGPD, Perfil).
*   **`monitor_processos.py`**: Robô que acorda de tempos em tempos para bater nos sites de tribunais e buscar o `ultimo_andamento`.
*   **`send_notifications.py`**: Carteiro eletrônico da API (mandará o aviso final via WhatsApp).
*   **`webhook_whatsapp.py` (Worker)**: Task dedicada para desovar requisições síncronas de webhook para a fila assíncrona.

---

### 1.9 Rotas API de Negócio (Fase 2C - Em andamento/Concluído)
*   **A Rota de Autenticação Real (`auth.py`)**: Valida credenciais (Email+Bcrypt) no banco gerando Access e Refresh Tokens JWT. Conta também com rota de revalidação `/refresh` e consulta de perfil `/me`.
*   **A Rota de Processos e CRUD (`processos.py`)**: Lista de forma paginada e cadastra novos processos vinculados ao cliente, amarrando sempre o `escritorio_id` do Advogado logado (Isolamento Multi-Tenant). Inicia automaticamente o robô de monitoramento de instâncias na criação.
*   **A Rota do Webhook do WhatsApp (`webhook_whatsapp.py`)**: A porta receptora da Evolution API. Recebe mensagens, filtra apenas mensagens úteis de clientes cadastrados, formata a string/caption e insere no Celery garantindo resposta HTTP 200 hiper-rápida.

---

*   **A Rota do Chat Histórico (`chat.py`)**: Fornece endpoints analíticos e proativos. Traz o histórico de mensagens de um cliente (`/chat/history`), permite que o advogado dispare uma mensagem manualmente que vai pra fila do Celery (`/chat/send`) e traz os KPIs daquele escritório como custo total em USD e tokens consumidos (`/chat/stats/dashboard`).

---

## 🎉 CONCLUSÃO: FASE 1 e FASE 2 FINALIZADAS! (100% do App Base)

O backend web (`FastAPI`), o banco de dados (`PostgreSQL/SQLAlchemy`), as validações de input (`Pydantic`), a segurança (`JWT/Bcrypt`) e todas as esteiras principais de rotas estão prontas!

**Próximo Grande Marco (Fase 3 & 4):**
Entraremos no core da Inteligência Artificial. A API Web e os Workers vão parar de trafegar strings vazias e começar a chamar a API da Anthropic (Claude) e o Jusbrasil conectando nossa arquitetura de RAG local.

---
> Elaborado via Pair Programming - Concierge Jurídico Digital.
