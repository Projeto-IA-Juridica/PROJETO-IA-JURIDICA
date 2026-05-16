RAILWAY DEPLOY — Guia rápido

1) Criar conta Railway
- Acesse https://railway.app e crie uma conta (GitHub recommended).

2) Conectar repositório
- No Railway, crie um novo Project → Connect GitHub repo → selecione este repositório.

3) Build settings
- O `railway.json` já aponta para `infrastructure/docker/Dockerfile.f1`.
- Se preferir, set `Build` → `Environment` e `Dockerfile` path conforme `railway.json`.

4) Variáveis de ambiente obrigatórias (adicionar no Project > Variables)
- DATABASE_URL
- REDIS_URL
- CELERY_BROKER_URL
- CELERY_RESULT_BACKEND
- ANTHROPIC_API_KEY
- OPENAI_API_KEY
- JWT_SECRET_KEY (gerar: `python -c "import secrets; print(secrets.token_hex(32))"`)
- ENCRYPTION_KEY (gerar: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`)

5) Variáveis opcionais/úteis
- EVOLUTION_API_URL / EVOLUTION_API_KEY
- EXPLORIUM_API_KEY
- SENTRY_DSN
- METRICS_TOKEN (proteger endpoint /metrics)
- DOCS_USERNAME / DOCS_PASSWORD (protege /docs em produção)

6) Serviços necessários
- Provisionar um PostgreSQL (Railway Plugin) e copiar a `DATABASE_URL` para as variables.
- Provisionar um Redis (Railway Plugin) e copiar a `REDIS_URL`.

7) Migrations e tarefas iniciais
- Execute uma `one-off` (Run → New Shell) para rodar migrações:
  - `alembic upgrade head`
- Criar um serviço separado para workers/Celery (opcional): use o mesmo Dockerfile e ajuste o comando.
  - Worker command exemplo: `celery -A feature_1_ia_personalizada.workers.celery_app worker --loglevel=info`

8) Healthcheck
- Railway já está configurado para checar `/health` (veja `railway.json`).

9) Testar localmente com Docker
- `docker build -f infrastructure/docker/Dockerfile.f1 -t concierge-f1 .`
- `docker run -e PORT=8000 -p 8000:8000 concierge-f1`
- Acesse `http://localhost:8000/health` e `http://localhost:8000/metrics`.

10) Observabilidade & métricas
- Defina `METRICS_TOKEN` para proteger `/metrics` em produção.
- Se quiser enviar métricas para Grafana Cloud, configure `GRAFANA_CLOUD_*` no .env.

11) Notas de segurança
- Nunca comitar chaves em repositórios.
- Use Railway Environment variables / Secrets.
- Considere usar um serviço de secrets (AWS Secrets Manager / Vault) para produção.

12) Suporte e troubleshooting
- Problemas comuns: build falhando por dependências do sistema (adicione pacotes em `infrastructure/docker/Dockerfile.f1`).
- Para logs: Project → Deployments → View build logs / live logs.

Se quer, eu posso:
- adicionar scripts de `railway up`/`railway run` com o Railway CLI (precisa confirmar que quer usar CLI),
- ou conectar e disparar o deploy aqui (me diga se quer que eu gere um `railway` CLI script).
