# Infrastructure — Concierge Jurídico Digital

Documentação da infraestrutura de produção do projeto.

---

## Plataforma de Deploy: Railway

O projeto usa **Railway** como plataforma de hospedagem em produção.
Railway substitui a necessidade de gerenciar servidores próprios, Docker Compose em produção, Nginx e certificados TLS manualmente.

### PIJ-211 — Resource Limits (Recursos por Serviço)

No Railway, os limites de CPU e memória são configurados diretamente no dashboard — sem necessidade de `docker-compose.yml` com `deploy.resources`.

**Configuração atual recomendada por serviço:**

| Serviço | RAM | vCPU |
|---------|-----|------|
| `app-f1` (FastAPI) | 512 MB | 0.5 vCPU |
| `celery-worker` | 256 MB | 0.25 vCPU |
| `celery-beat` | 128 MB | 0.1 vCPU |

**Como configurar no Railway:**
1. Acesse o projeto no [railway.app](https://railway.app)
2. Clique no serviço desejado → **Settings**
3. Seção **"Resource Limits"** → defina CPU e RAM
4. Salve — Railway reinicia o serviço automaticamente

> ℹ️ Railway cobra apenas pelos recursos **realmente consumidos** (não pelo limite máximo alocado).

---

### PIJ-212 — Reverse Proxy com TLS (HTTPS)

Railway fornece **HTTPS automático** para todos os serviços — sem necessidade de configurar Nginx ou gerenciar certificados Let's Encrypt manualmente.

**O que Railway faz automaticamente:**
- ✅ Certificado TLS (Let's Encrypt) provisionado e renovado automaticamente
- ✅ Redirecionamento HTTP → HTTPS forçado
- ✅ Proxy reverso com headers `X-Forwarded-For`, `X-Forwarded-Proto`
- ✅ HTTP/2 habilitado por padrão

**Domínio customizado (quando necessário):**
1. Acesse o serviço no Railway → **Settings → Domains**
2. Clique em **"Custom Domain"** e adicione seu domínio (ex: `api.concierge.com.br`)
3. Configure o DNS no seu provedor de domínio:
   ```
   CNAME  api  →  seu-app.railway.app
   ```
4. Railway gera e renova o certificado TLS automaticamente em minutos

**Domínio padrão Railway (sem configuração):**
```
https://seu-projeto-nomealeatorio.railway.app
```

---

## Arquivos Docker (Referência Local)

Os arquivos em `infrastructure/docker/` são usados pelo Railway e pelo CI para:

- **`Dockerfile.f1`** — imagem de produção da Feature 1 (FastAPI + Celery)
- **`docker-compose.prod.yml`** — referência do compose de produção (não usado em produção com Railway)
- **`docker-compose.dev.yml`** — ambiente de desenvolvimento local (opcional)

---

## Scripts

| Script | Descrição |
|--------|-----------|
| `scripts/backup.sh` | Backup manual do PostgreSQL via `pg_dump` |

O backup automático é executado diariamente pelo GitHub Actions (`.github/workflows/backup.yml`).
