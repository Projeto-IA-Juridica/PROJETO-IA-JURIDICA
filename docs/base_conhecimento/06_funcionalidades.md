# 06 — Funcionalidades do Produto

## Monitoramento de processos
- Consulta Jusbrasil (primário) + DataJud CNJ (backup gratuito) a cada 6h por
  processo ativo. Cache Redis 1h contra requisição duplicada.
- Tracking de fase: conhecimento → instrução → saneamento → julgamento → recurso
  → execução → encerrado.
- Ao detectar movimentação, dispara notificação proativa ao cliente em linguagem
  simples.

## Score de risco processual
Pontuação 0–100 por processo, 5 componentes: idade do processo (20%), perfil do
juiz (25%), tipo de ação (20%), prazos pendentes (20%), histórico do escritório
no tribunal (15%). **Nunca exibido ao cliente** (compliance OAB). Atualizado a
cada 6h pelo worker de monitoramento. Serviço: `score_risco.py`.

## CRM Inteligente
- Score de relacionamento por cliente (0–100): frequência de interação, NPS,
  nº de escalações, dias desde último contato.
- Classificação: `excelente / satisfeito / neutro / em_risco / critico`.
- Análise narrativa gerada pelo Claude (diagnóstico + ação sugerida).
- Debounce: máx. 1 análise/hora/cliente. Alerta de risco de churn.

## Analytics & Dashboard
NPS com tendências 7/30/90 dias + gráfico semanal; taxa de resposta autônoma
(% sem escalação); custo por interação (por tokens); exportação CSV/Excel.

## Escalação para advogado
Detecta requisição fora de escopo (parecer, estratégia, situação sensível). Dois
caminhos: automático pelo Confidence Router, ou forçado por intenção. Notifica o
advogado responsável via WhatsApp; registra abertura/resposta/resolução.
Configurável por escritório.

## Agendamento Inteligente de reuniões
Fluxo completo pelo WhatsApp, sem secretária:

```
Cliente pede reunião → IA detecta intenção agendar_reuniao
IA propõe 3 horários livres → cliente escolhe (1/2/3)
   → status aguardando_advogado
Advogado aprova (Hub em tempo real via SSE, ou responde no WhatsApp)
   → status confirmado → evento no Google Calendar + confirmação ao cliente
Lembrete 24h antes + confirmação 3h antes
```

- **Detector** (`services/agendamento/detector.py`): varre até 30 dias, evita
  conflito com reuniões confirmadas/pendentes, evita dia de prazo (e véspera),
  filtra horários ocupados no Google Calendar (freeBusy).
- **Consciência de prazos** (`prazos.py`): extrai prazos dos andamentos —
  explícitos ("contestação até 15/08") e relativos ("prazo de 15 dias" = dias
  úteis, CPC art. 219). Calendário forense embutido: feriados nacionais + recesso
  (CPC art. 220: 20/12–20/01). Conflito de prazo **avisa, nunca bloqueia**.
- **Google Calendar** bidirecional (OAuth2 por escritório, refresh token Fernet):
  reunião confirmada vira evento; cancelamento remove. Tudo best-effort.
- **Tempo real:** `GET /agendamentos/stream` (SSE via Redis pub/sub); o card de
  aprovação aparece/some em milissegundos.
- **Robustez:** lock Redis "primeiro canal ganha" (impede dupla confirmação
  Hub+WhatsApp); idempotência por flags; persistência antes de notificar;
  reproposta automática quando o slot escolhido já passou/foi ocupado.

## Hub do Advogado (Claude Opus)
Interface exclusiva do advogado, sem as restrições do canal do cliente. Endpoints
`/hub/*`: análise de petição PDF (pontos fortes/fracos/riscos/sugestões),
consulta jurídica livre, sessões e métricas. Classificação de intenção:
análise_petição, pesquisa_jurisprudência, resumo_processo, insight_cliente,
pergunta_jurídica. Cada sessão gravada em `sessoes_advogado` (modelo, tokens,
custo). Quota própria de tokens; pode ser desabilitado por escritório.

## Billing (Stripe)
`/billing/checkout` (Checkout Session), `/billing/portal` (trocar cartão/plano/
cancelar), `/billing/webhook` (eventos HMAC → atualiza plano e quotas),
`/billing/status`. Trial 7 dias. Sem `STRIPE_SECRET_KEY`, opera em modo degradado
sem quebrar o resto.

## Documentos do cliente
Dossiê por cliente (contrato, procuração, etc.), até 10 MB, vinculável a
processo. Não vetorizado. Endpoints em `/clientes/{id}/documentos`.

## Onboarding Wizard
6 etapas para ficar operacional em < 30 min: dados do escritório → conexão
WhatsApp (QR Evolution) → importação de clientes (CSV/Sheets) → persona →
disclaimers OAB → ativação e teste.

## Prospecção Inteligente (Feature 3) — ⏸️ PAUSADA
Motor completo (DNA do advogado, matching B2B/B2C, pipeline, compliance LGPD),
**mas a descoberta está bloqueada**: o DataJud público não retorna o campo
`partes`, então a busca de litigantes retorna zero. Retomada planejada com a API
**Escavador**, mantendo a interface `buscar_litigantes(tipo_acao, tribunal)`.
Não vender esta feature enquanto pausada.

## Painéis web
- **Hub React** (16 páginas): HubIA (chat do advogado), Painel (dashboard +
  Agenda), CRM, Captação, Documentos, Planos, Plano, Whatsapp, Config, Onboarding,
  etc.
- **Admin** (9 páginas): Hub, ClientDetail, Processos, CRM, Analytics, Operations,
  RAG, Settings, Login.
- Frontends vanilla: login, cadastro-onboarding, ajuda-contato.
