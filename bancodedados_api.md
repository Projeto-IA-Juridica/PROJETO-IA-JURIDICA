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

### 1.5 Primeira Rota Realizada (Fase 2C)
*   **`api/routes/health.py`**: Criamos a rota de monitoramento real.
    *   Acessando o sistema, o endpoint de health faz **pings síncronos**: testa o SQLAlchemy batendo no Postgres via async, e testa o pool do Redis via `redis.asyncio` usando a ENV URL. Traz ms e logs.

### 1.6 Schemas, Utils e Alembic (Feito pelo Outro Dev)
O que entrou via `git pull`:
*   **Schemas (`shared/schemas/`)**: Scripts Pydantic (validação exata de entrada de dados da API).
*   **Utils (`shared/utils/`)**: Conversores de data, validadores de CPF nativos e funções atreladas ao Whisper (áudio).
*   **Alembic (`alembic/`) e Scripts**: Foi gerada a Migration 001 que traduz nossos Models (do item 1.1) em linguagem SQL.

---

## 2. O Que Vamos Fazer Pela Frente (Próximos Passos na FASE 2)

Agora o Banco de Dados, Segurança e Padrões estão finalizados. Nossa missão inteira foca puramente em rechear o servidor web.

**Etapas Futuras na API (`feature_1_ia_personalizada/api/`):**

1.  **Middlewares de Intercepção (Fase 2B)**
    *   *`auth.py`*: Plugar no nível global para interceptar toda e qualquer requisição. Ele varre o header antes da rota ser chamada para confirmar que o usuário enviou o token JWT e barrar acessos sem credencial.
    *   *`rate_limit.py`*: Um bloqueador de flodding para interagir com o Redis. Conta quantas vezes o cara chamou o nosso webhook para nós não explodirmos de custos de IA, jogando um `429 Too Many Requests`.

2.  **A Rota de Autenticação Real (`api/routes/auth.py`)**
    *   Fazer o `POST /auth/login`. O usuário baterá com email+senha -> A gente vai no `usuario.py` do banco -> Checa usando método `verificar_senha` que fizemos hoje -> Pega o `Access_Token` do `jwt.py` e devolve.

3.  **A Rota de Processos e CRUD (`api/routes/processos.py`)**
    *   Aqui nós leremos o `processo.py` do banco de dados e exporemos. Cadastrar um processo novo, deletar, puxar andamentos, e garantir o Multi-Tenant. (Se o JWT for do Escritório A, nunca retorna Processos do Escritório B).

4.  **A Rota do Chat Histórico (`api/routes/chat.py`)**
    *   Fazer o dashboard do cliente, devolvendo toda aquela listagem bruta armazenada da `interacao.py` que nós definimos hoje sobre tokens e conversa.

5.  **A Rota (Crucial) do Webhook do WhatsApp (`api/routes/webhook_whatsapp.py`)**
    *   É a boca receptora da Evolution API. Recebemos requisições POST.
    *   Vamos tratar áudio, ler o texto, e passar para o nosso orquestrador chamar o modelo Claude (A infraestrutura que virá depois).

---
> Elaborado via Pair Programming - Concierge Jurídico Digital.
