# 10 — Segurança e Compliance

## OAB (Provimento 205/2021)
- A IA **nunca emite parecer jurídico nem prevê resultado** de processo.
- Disclaimer obrigatório na primeira interação de cada cliente (fala com um
  assistente do escritório).
- Assuntos que exigem advogado são escalados automaticamente (`parecer_juridico`,
  `estrategia_processual`, `negociacao`, `decisao_judicial_impacto_alto`).
- **Score de risco visível só para o advogado**, nunca para o cliente.
- Prospecção B2C restrita a canais processuais — sem cold call com dado de litígio.

## LGPD (Lei 13.709/2018)
- Criptografia **AES-256 (Fernet)** em repouso para CPF e dados sensíveis; campo
  `cpf_version` no cliente permite **rotação de chave** (`ENCRYPTION_KEY_PREVIOUS`).
- TLS em trânsito.
- Isolamento por `escritorio_id` (row-level) — nenhum escritório vê dado de outro.
- Mascaramento: CPF → `***.***.***-XX`, telefone → `(**)****-XXXX`.
- Retenção: dados de processos arquivados removidos após 5 anos.
- Lead B2C da prospecção: campos `cpf`/`telefone`/`email` **não existem no modelo**
  — proibido por design.
- Portabilidade/anonimização: `GET /clientes/{id}/exportar` (Art. 18, V) e
  `DELETE /clientes/{id}` (Art. 18, IV).
- Sentry com `send_default_pii=False` — nenhum dado pessoal ao rastreador de erros.

## Autenticação e autorização
- **JWT** (python-jose) com access + refresh; expiração configurável.
- Senhas com **bcrypt** (`hash_senha`/`verificar_senha`); hash dummy no login para
  evitar enumeração por timing.
- **CSRF**: token em cookie + header nas requisições mutantes de browser; webhooks
  isentos (não têm sessão de browser).
- Rate limit por middleware.
- Rotas públicas são uma lista explícita e auditável (ver [07](07_api_endpoints.md)).

## Webhooks (autenticados sem JWT)
- `/webhook/whatsapp` — HMAC da Evolution.
- `/billing/webhook` — `stripe-signature` HMAC.
- `/vendas/webhook` — apikey da instância de vendas via `compare_digest`. Isento
  de JWT/CSRF declaradamente nos middlewares (visível para auditoria), e só existe
  com a máquina de vendas ligada.

## Anti-alucinação (segurança do output)
O fact-checker valida cada resposta contra os dados reais do banco antes de
enviar. Quando a confiança é baixa, escala para o humano em vez de chutar. É
segurança de conteúdo: impede a IA de afirmar andamento/prazo que não existe.

## Segredos e configuração
Todos os segredos em env vars (nunca no código): `ANTHROPIC_API_KEY`,
`DATABASE_URL`, `JWT_SECRET_KEY`, `ENCRYPTION_KEY` (Fernet 44 chars),
`EVOLUTION_API_KEY`, `STRIPE_SECRET_KEY`, etc. Docs de gestão em
`docs/guides/secrets.md`. `/docs` protegido por Basic Auth em produção.

## Máquina de vendas — postura ética
A humanização é legítima (conversa que não parece robô beneficia também o cliente
do escritório no produto). O limite é a **transparência quando perguntada**: a
Clara nunca nega ser IA. Opt-out é eterno e cumprido em código (não só prometido
no prompt). Volume baixo e personalizado (5–10/dia) — não é disparo em massa.
Ver [09](09_maquina_de_vendas.md).
