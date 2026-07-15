# 08 — Workers e Tarefas Agendadas

Celery 5.3 com Redis como broker e **RedBeat** como scheduler (schedules
dinâmicos no Redis). 11 workers no produto. Todos os workers que usam
`asyncio.run` usam a `worker_session_factory` global (NullPool) — nunca a factory
pooled da API — para não cruzar event loops ("Future attached to a different loop").

## Tarefas do produto e seus horários

| Task | Frequência | O que faz |
|---|---|---|
| `monitorar_processos` | a cada 6h (0,6,12,18h) | Varre processos ativos, busca andamento novo |
| `monitorar_processo_individual` | on-demand | Monitora um processo específico |
| `dispatcher_agendadas` | a cada 5 min | Despacha `mensagens_agendadas` fora da janela comercial |
| `mensagens_relacionamento` | diário/semanal | Aniversários, datas comemorativas |
| `crm_worker` | on-demand (debounce 1h) | Recalcula score CRM + análise Claude |
| `hub_worker` | on-demand | Processa análise/consulta do Hub |
| `ingest_documentos` | on-demand | Pipeline RAG (extração → embedding → pgvector) |
| `send_notifications` | on-demand | Notificações ao cliente |
| `dead_letter` (`processar_dlq`) | — | Dead Letter Queue |

## Tarefas do Agendamento Inteligente

| Task | Trigger | O que faz |
|---|---|---|
| `workers.agendamento.processar_resposta_advogado_wpp` | webhook (advogado) | Confirma/recusa via WhatsApp com lock Redis |
| `workers.agendamento.expirar_propostas` | a cada hora | `aguardando_cliente` com `expira_em` vencido → `expirado` |
| `workers.agendamento.enviar_lembretes` | diário 8h | Lembrete 24h antes (cliente e advogado) |
| `workers.agendamento.enviar_confirmacao_pre_reuniao` | a cada hora | Confirmação 3h antes (flag de idempotência) |
| `workers.agendamento.verificar_conflitos_prazos` | 7h30 + hook pós-andamento | Reuniões confirmadas vs. novos prazos → alerta o advogado |
| `workers.agendamento.enviar_mensagens_pos_acao` | on-demand | Mensagens após ação do fluxo |

## Tarefas da máquina de vendas (só com flag ligada)

Registradas por import guardado no `celery_app.py` (import de
`feature_vendas.workers.conversa_worker` e `maquina_vendas`). Ver
[09_maquina_de_vendas.md](09_maquina_de_vendas.md) para o detalhe:
- `vendas.responder_conversa` — a Clara responde ao lead (buffer → LLM → entrega humanizada → handoff).
- tarefas de enriquecimento/disparo/cadência da planilha de alvos.

## Padrão de robustez
- **DLQ:** falhas repetidas caem numa Dead Letter Queue para inspeção.
- **Idempotência:** flags por mensagem enviada impedem retries de duplicar envio
  (crítico nos lembretes de agendamento — sem isso, o worker horário poderia
  disparar dezenas de mensagens).
- **Best-effort em integrações:** Google Calendar, métricas e pub/sub Redis nunca
  quebram o fluxo principal se falharem.
