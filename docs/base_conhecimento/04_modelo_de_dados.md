# 04 — Modelo de Dados

12 tabelas, todas isoladas por `escritorio_id` (row-level multi-tenancy). ORM
SQLAlchemy em `shared/models/`. Mixins comuns: `TenantMixin` (escritorio_id),
`TimestampMixin` (created_at/updated_at).

## escritorios — o tenant raiz

Um escritório = um cliente pagante. Campos principais:
- Identidade: `nome`, `cnpj`, `email`, `telefone`, `endereco`, `oab_responsavel`, `nome_responsavel`
- Plano/limites: `plano`, `max_processos`, `max_clientes`, `ativo`
- Persona da IA: `persona_nome`, `persona_tom`, `template_boas_vindas`, `template_atualizacao`, `template_sem_novidade`
- Janela de envio: `horario_inicio`, `horario_fim`, `timezone`
- Onboarding: `onboarding_etapa`, `onboarding_completo`, `onboarding_at`
- Quota de tokens: `quota_tokens_mes`, `tokens_usados_mes`, `tokens_reset_em`
- WhatsApp: `webhook_whatsapp_instance`, `telefone_advogado`
- Stripe: `stripe_customer_id`, `stripe_subscription_id`, `stripe_price_id`, `assinatura_status`, `trial_expira_em`, `assinatura_expira_em`
- Google Calendar: `google_calendar_refresh_token` (Fernet), `google_calendar_id`, `google_calendar_conectado_em`
- Escalação (Hub): `escalacao_habilitada`, `escalacao_canal_advogado_numero`, `escalacao_quota_tokens_mes`, `escalacao_tokens_usados_mes`, `escalacao_confidence_threshold`
- Prospecção: `dna_prospeccao` (JSONB)

## usuarios — advogados e assistentes

`nome`, `email`, `senha_hash` (bcrypt), `role`, `oab`, `whatsapp_numero`,
`escalacao_ativa`, `ativo`, `ultimo_login`. Relaciona com processos
(`processos_responsavel`).

## clientes — o cliente final do escritório

- Pessoais: `nome`, `cpf` (criptografado AES-256, com `cpf_version` para rotação de chave), `email`, `telefone_whatsapp`, `data_nascimento`, `profissao`, `empresa_atual`, `cargo`
- LGPD: `aceite_lgpd`, `data_aceite_lgpd`
- Preferência: `preferencia_horario_notificacao`, `ativo`
- CRM: `crm_nivel`, `crm_score`, `crm_resumo`, `crm_acao_sugerida`, `crm_analisado_em`

## processos — o processo judicial

- Vínculo: `cliente_id`, `advogado_responsavel_id`
- Identificação: `numero_cnj`, `tribunal`, `vara`, `comarca`, `tipo_acao`, `polo_cliente`
- Andamento: `status`, `ultimo_andamento`, `data_ultimo_andamento`, `data_distribuicao`, `valor_causa`
- Estado: `estado_atual` (JSONB — guarda `ultimos_andamentos`), `fase_processual`
- Score de risco: `score_risco` (0–100), `score_nivel`, `score_componentes` (JSONB), `score_interpretacao`, `score_atualizado_em`
- Monitoramento: `jusbrasil_id`, `monitoramento_ativo`, `frequencia_monitoramento`

> Nota importante: **não existe tabela de prazos**. Prazos são extraídos por
> regex de `processo.estado_atual["ultimos_andamentos"]` pelo serviço de
> agendamento (`services/agendamento/prazos.py`).

## interacoes — o log de cada conversa IA↔cliente

`cliente_id`, `processo_id`, `tipo`, `direcao`, `mensagem_cliente`,
`mensagem_ia`, `audio_transcricao`, `modelo_ia` (qual Claude respondeu),
`tokens_input`, `tokens_output`, `custo_estimado`, `tempo_resposta_ms`,
`satisfacao` (NPS), `metadata_json`. É a base do analytics e do custo por interação.

## documentos_rag — base de conhecimento vetorizada

Documentos do escritório (petições, teses, modelos) em chunks com embedding
1024-dim (pgvector, HNSW). Isolado por `escritorio_id`.

## documentos_cliente — dossiê do cliente

Arquivos vinculados a um cliente (contrato, procuração, identidade, petição,
comprovante, outro), até 10 MB, salvos como BYTEA. **Não são vetorizados** — é
arquivo morto organizado, diferente de `documentos_rag`.

## agendamentos — reuniões marcadas pela IA

Máquina de estados: `aguardando_cliente → aguardando_advogado → confirmado |
cancelado | expirado`. Campos: `cliente_id`, `interacao_id`, `processo_id`,
`status`, `data_hora_inicio/fim`, `opcoes_propostas` (JSONB), `opcao_selecionada_pos`,
`canal_aprovacao` (hub/whatsapp), `motivo_cliente`, `nota_advogado`, flags de
idempotência por mensagem enviada, `expira_em`, `google_event_id`. Detalhe em
[06_funcionalidades.md](06_funcionalidades.md).

## disponibilidade_advogado — janelas de atendimento

Uma linha por dia ativo (0=segunda … 5=sábado): `dia_semana`, `hora_inicio`,
`hora_fim`, `ativo`. O detector de agendamento lê isto para gerar horários.

## mensagens_agendadas — fila de envio fora da janela comercial

Mensagens bloqueadas pela janela comercial ou rate limit ficam aqui e são
despachadas pelo worker `dispatcher_agendadas` a cada 5 minutos.

## sessoes_advogado — histórico do Hub

Cada consulta/análise no Hub do Advogado: modelo usado, tokens, custo estimado.
Base das métricas do Hub.

## leads_prospeccao — pipeline da Feature 3 (pausada)

Leads B2B/B2C descobertos pela prospecção. Deduplicação por CNPJ/CNJ. B2C **não
tem** campos `cpf`/`telefone`/`email` — proibido por design (LGPD). Feature
pausada (ver [01](01_visao_geral.md)).

> **A máquina de vendas usa uma tabela própria e separada, `alvos_vendas`**, no
> `feature_vendas/models/` — não se mistura com `leads_prospeccao`. Ver
> [09_maquina_de_vendas.md](09_maquina_de_vendas.md).
