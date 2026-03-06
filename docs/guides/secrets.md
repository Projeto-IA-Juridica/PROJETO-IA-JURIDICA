# Secrets Management — Concierge Jurídico Digital

> Geração, rotação e injeção segura de credenciais em todos os ambientes.

---

## Índice

1. [Geração de Chaves](#1-geração-de-chaves)
2. [Onde os Secrets Vivem por Ambiente](#2-onde-os-secrets-vivem-por-ambiente)
3. [AWS Secrets Manager (produção)](#3-aws-secrets-manager-produção)
4. [HashiCorp Vault (alternativa)](#4-hashicorp-vault-alternativa)
5. [Rotação de Chaves](#5-rotação-de-chaves)
6. [Checklist de Segurança](#6-checklist-de-segurança)

---

## 1. Geração de Chaves

Execute os comandos abaixo uma única vez para cada ambiente. Guarde os valores em um gerenciador de senhas do time (Bitwarden, 1Password, etc.) **antes** de colocá-los no servidor.

### JWT_SECRET_KEY

Chave mínima de 32 caracteres, usada para assinar e verificar tokens JWT.

```bash
python -c "import secrets; print(secrets.token_hex(32))"
# Exemplo de saída: a3f8c2e1d4b6a9f2e5c8d1b4a7e0c3f6a9d2e5b8c1f4a7d0e3b6c9f2a5d8b1e4
```

### ENCRYPTION_KEY

Chave Fernet (AES-256-CBC + HMAC-SHA256). Usada para criptografar CPFs e dados sensíveis no banco.

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Exemplo de saída: 3bX8pLQzR1mNvK7dCjWoAeYhSfTgUiOx2qVnMrBuP9lHkJcZy4=
```

> **Aviso:** Perder esta chave significa perder acesso permanente aos dados criptografados no banco. Faça backup em dois locais separados antes de usar em produção.

### POSTGRES_PASSWORD e REDIS_PASSWORD

```bash
python -c "import secrets; print(secrets.token_urlsafe(24))"
```

Use saídas diferentes para cada senha.

### FLOWER_PASSWORD (UI do Celery)

```bash
python -c "import secrets; print(secrets.token_urlsafe(16))"
```

---

## 2. Onde os Secrets Vivem por Ambiente

| Ambiente | Fonte de Secrets | `.env` no servidor? |
|---|---|---|
| Desenvolvimento local | `.env` (não versionado) | Sim, gerado pelo dev |
| CI (GitHub Actions) | GitHub Secrets (Settings → Secrets → Actions) | Não |
| Staging | AWS Secrets Manager ou variáveis do servidor | Não |
| Produção | AWS Secrets Manager ou variáveis do servidor | Não |

### Regra de ouro

> Nenhum secret real entra em um arquivo versionado. O `.env` serve apenas para desenvolvimento local.

O arquivo `.env.example` no repositório contém **apenas placeholders** — nunca valores reais.

---

## 3. AWS Secrets Manager (produção)

### 3.1 Criar o secret

```bash
aws secretsmanager create-secret \
  --name "concierge/production" \
  --region sa-east-1 \
  --description "Secrets de producao do Concierge Juridico Digital" \
  --secret-string '{
    "ANTHROPIC_API_KEY": "sk-ant-...",
    "OPENAI_API_KEY": "sk-...",
    "JWT_SECRET_KEY": "<gerado no passo 1>",
    "ENCRYPTION_KEY": "<gerado no passo 1>",
    "EVOLUTION_API_KEY": "<chave da Evolution API>",
    "JUSBRASIL_API_KEY": "<chave da Jusbrasil>",
    "POSTGRES_PASSWORD": "<gerado no passo 1>",
    "REDIS_PASSWORD": "<gerado no passo 1>",
    "FLOWER_PASSWORD": "<gerado no passo 1>",
    "SENTRY_DSN": "https://...@sentry.io/..."
  }'
```

> Não coloque `DATABASE_URL` e `REDIS_URL` completas no secret — elas referenciam `POSTGRES_PASSWORD` e `REDIS_PASSWORD`. Monte as URLs no `docker-compose.prod.yml` usando as variáveis individuais.

### 3.2 Configurar a aplicação para usar o secret

Defina **apenas** estas duas variáveis no servidor (via painel do cloud provider, não em arquivo):

```bash
AWS_SECRET_NAME=concierge/production
AWS_REGION=sa-east-1
```

O loader em `shared/config/secrets.py` detecta `AWS_SECRET_NAME` e injeta automaticamente todos os valores em `os.environ` antes de `Settings()` ser instanciado.

### 3.3 Permissão IAM mínima

A EC2/ECS/Lambda que roda a aplicação precisa da seguinte policy IAM:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "secretsmanager:GetSecretValue",
      "Resource": "arn:aws:secretsmanager:sa-east-1:<ACCOUNT_ID>:secret:concierge/production-*"
    }
  ]
}
```

Use IAM Role (não access keys hardcoded). O boto3 resolve a role automaticamente quando rodando na AWS.

### 3.4 Verificar que está funcionando

```bash
# No servidor, antes de subir a aplicação:
aws secretsmanager get-secret-value \
  --secret-id concierge/production \
  --region sa-east-1 \
  --query SecretString \
  --output text | python -m json.tool
```

---

## 4. HashiCorp Vault (alternativa)

Use se o time já opera Vault ou prefere não depender de um cloud provider específico.

### 4.1 Armazenar o secret (KV v2)

```bash
# Habilitar engine KV v2
vault secrets enable -path=secret kv-v2

# Escrever os secrets
vault kv put secret/concierge/production \
  ANTHROPIC_API_KEY="sk-ant-..." \
  JWT_SECRET_KEY="..." \
  ENCRYPTION_KEY="..." \
  EVOLUTION_API_KEY="..." \
  JUSBRASIL_API_KEY="..."
```

### 4.2 Configurar a aplicação

```bash
VAULT_ADDR=https://vault.sua-empresa.com
VAULT_TOKEN=hvs.XXXXXXXXXXXXXXXXXX
VAULT_SECRET_PATH=secret/data/concierge/production
```

> Para KV v2, o path deve incluir `/data/` entre o mount e o nome do secret.

### 4.3 Gerar token com AppRole (recomendado para produção)

Evite usar tokens de desenvolvimento (`hvs.root`) em produção. Use AppRole:

```bash
# Criar policy
vault policy write concierge-read - <<EOF
path "secret/data/concierge/production" {
  capabilities = ["read"]
}
EOF

# Habilitar AppRole
vault auth enable approle

# Criar role
vault write auth/approle/role/concierge \
  policies="concierge-read" \
  token_ttl=1h \
  token_max_ttl=4h

# Obter RoleID e SecretID
vault read auth/approle/role/concierge/role-id
vault write -f auth/approle/role/concierge/secret-id

# Autenticar e obter token
vault write auth/approle/login \
  role_id="<ROLE_ID>" \
  secret_id="<SECRET_ID>"
```

---

## 5. Rotação de Chaves

### 5.1 Rotacionar JWT_SECRET_KEY

Impacto: todos os tokens JWT ativos são invalidados. Usuários precisarão fazer login novamente.

```bash
# 1. Gerar nova chave
NOVA_CHAVE=$(python -c "import secrets; print(secrets.token_hex(32))")

# 2. Atualizar no secrets manager
aws secretsmanager update-secret \
  --secret-id concierge/production \
  --secret-string "$(aws secretsmanager get-secret-value \
    --secret-id concierge/production \
    --query SecretString \
    --output text | python -c "
import json, sys
s = json.load(sys.stdin)
s['JWT_SECRET_KEY'] = '$NOVA_CHAVE'
print(json.dumps(s))
")"

# 3. Reiniciar a aplicação (zero-downtime rolling restart)
docker compose -f infrastructure/docker/docker-compose.prod.yml \
  up -d --no-deps --force-recreate app-f1

# 4. Validar
curl -f https://seu-dominio.com/health/ready
```

### 5.2 Rotacionar ENCRYPTION_KEY

> **Cuidado:** dados já criptografados no banco com a chave antiga não serão legíveis com a nova chave. Exige script de migração.

Procedimento:
1. Gerar nova chave
2. Escrever script que lê cada campo criptografado, descriptografa com a chave antiga e re-criptografa com a nova
3. Executar script com a aplicação em manutenção (ou com writes pausados)
4. Atualizar `ENCRYPTION_KEY` no secrets manager
5. Reiniciar aplicação

**Nunca troque `ENCRYPTION_KEY` sem executar a migração de dados primeiro.**

### 5.3 Rotacionar chaves de APIs externas (Anthropic, Evolution, etc.)

```bash
# 1. Gerar nova chave no painel do provider
# 2. Atualizar no secrets manager (sem downtime — a chave antiga ainda funciona)
# 3. Reiniciar a aplicação
# 4. Revogar a chave antiga no painel do provider
```

### Frequência de rotação recomendada

| Secret | Frequência | Gatilho extra |
|---|---|---|
| JWT_SECRET_KEY | A cada 90 dias | Suspeita de vazamento |
| ENCRYPTION_KEY | Anual (com migração) | Vazamento confirmado |
| POSTGRES_PASSWORD | A cada 90 dias | Acesso não autorizado |
| REDIS_PASSWORD | A cada 90 dias | — |
| Chaves de APIs externas | Conforme política do provider | Funcionário sai da empresa |

---

## 6. Checklist de Segurança

Verificar antes de cada deploy em produção:

- [ ] `git log --oneline --all -- .env` não retorna nenhum commit
- [ ] `git log --oneline --all -- "*.pem" "*.key"` não retorna nenhum commit
- [ ] `AWS_SECRET_NAME` ou `VAULT_ADDR` + `VAULT_TOKEN` estão configurados no servidor
- [ ] Nenhuma chave real aparece em variáveis de ambiente do `docker-compose.prod.yml`
- [ ] `ENCRYPTION_KEY` tem backup em dois locais (ex: cofre do time + AWS Backup)
- [ ] IAM role da EC2/ECS tem apenas `secretsmanager:GetSecretValue` no secret correto
- [ ] `JWT_SECRET_KEY` tem pelo menos 32 caracteres (validado no startup pela aplicação)
- [ ] `ENCRYPTION_KEY` é uma Fernet key válida (validada no startup pela aplicação)
- [ ] Rotação de chaves está agendada no calendário do time

---

> Dúvidas ou incidentes de segurança: abrir issue privada no repositório ou contactar o responsável de segurança diretamente.
