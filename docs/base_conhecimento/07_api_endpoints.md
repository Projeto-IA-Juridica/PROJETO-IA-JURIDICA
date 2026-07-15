# 07 — API / Endpoints

19 routers no produto. Auth por JWT, exceto webhooks (autenticados por HMAC/apikey)
e rotas públicas explícitas. Middlewares: JWT, CSRF, rate limit, request logging.

## Autenticação e conta
| Método | Rota | Descrição | Auth |
|---|---|---|---|
| POST | `/auth/login` | Gera JWT | email/senha |
| POST | `/auth/register` | Cadastro de escritório | — |
| POST | `/auth/refresh` | Renova JWT | JWT |
| POST | `/auth/logout` | Logout | JWT |
| GET | `/auth/csrf-token` | Emite token CSRF | — |
| GET | `/auth/me` | Usuário atual | JWT |
| POST | `/auth/change-password` | Troca senha | JWT |

## Rotas públicas (sem JWT)
`/health`, `/health/ready`, `/auth/login`, `/auth/refresh`, `/auth/csrf-token`,
`/webhook/whatsapp` (HMAC), `/billing/webhook` (Stripe HMAC), `/metrics`,
`/admin/import` (exato), `/onboarding/register` (exato),
`/google-calendar/callback` (state), `/vendas/webhook` (apikey — só existe com a
máquina de vendas ligada).

## Produto (JWT)
| Rota | Endpoints | Função |
|---|---|---|
| `/processos` | 6 | CRUD de processos + score |
| `/clientes` | 8 | CRUD, documentos, exportar/anonimizar (LGPD) |
| `/rag` | 5 | Upload/busca/remoção de documentos vetoriais |
| `/crm` | 5 | Score + análise narrativa |
| `/chat` | 4 | Histórico, NPS, analytics |
| `/onboarding` | 9 | Wizard de 6 etapas |
| `/escritorios` | 2 | Config do escritório |
| escalacoes (sem prefixo) | 3 | CRUD de escalações |
| hub_advogado (sem prefixo) | 8 | `/hub/*` — análise, consulta, sessões, métricas |
| prospeccao (sem prefixo) | 6 | DNA, descobrir, pipeline (F3 pausada) |
| `/admin/import` | 2 | Importação CSV/Sheets |

## Agendamento (JWT)
| Rota | Endpoints | Função |
|---|---|---|
| `/agenda` | 4 | disponibilidade, slots, eventos |
| `/agendamentos` | 6 | listar, stream SSE, confirmar, sugerir, cancelar |
| `/google-calendar` | 4 | auth-url, callback, status, disconnect |

## Billing (JWT, exceto webhook)
`/billing/checkout`, `/billing/portal`, `/billing/status`, `/billing/webhook` (HMAC). 4 endpoints.

## Infra
`/health` (3: básico, ready, detalhado) · `/metrics` (Prometheus).

## Endpoints LGPD (portabilidade/anonimização)
- `GET /clientes/{id}/exportar` — exporta dados pessoais (Art. 18, V)
- `DELETE /clientes/{id}` — anonimiza (Art. 18, IV)

## Rotas da máquina de vendas (só com flag ligada)
Prefixo `/vendas`. `/vendas/webhook` (público, apikey) + rotas internas de painel
(`/vendas/leads/*`: funil, quentes, exceção, importar) que exigem JWT do tenant
de vendas. Ver [09_maquina_de_vendas.md](09_maquina_de_vendas.md).

> Documentação viva: `/docs` (Swagger) e `/openapi.json` — em produção protegidos
> por HTTP Basic (`DOCS_USERNAME`/`DOCS_PASSWORD`) ou bloqueados.
