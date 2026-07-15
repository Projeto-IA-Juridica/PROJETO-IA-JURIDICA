# 05 — Motor de IA

O coração do produto. Um orquestrador **LangGraph** executa, para cada mensagem
recebida, um pipeline de nós desacoplados em
`feature_1_ia_personalizada/services/ai/nodes/`.

## Pipeline de nós

```
classificar_intencao → buscar_dados → gerar_resposta
    → confidence_router → verificar_resposta (fact-check) → enviar_resposta
```

Arquivos: `intent.py`, `data.py`, `generation.py`, `verification.py`,
`delivery.py`, `agendamento.py`, `_helpers.py`. O grafo é montado em
`orchestrator.py`; o estado trafega em `state.py` (`ConversationState`,
`NodeDeps`, `QuotaExcedidaError`).

## Intenções detectadas

`status`, `perspectivas`, `duvida_termo`, `duvida_geral`, `saudacao`,
`reclamacao`, `desabafo`, `agendar_reuniao`, `parecer_juridico`,
`estrategia_processual`, `negociacao`, `decisao_judicial_impacto_alto`, `outro`.

- `agendar_reuniao` tem threshold próprio: se detectada com confiança, desvia
  para o Agendamento Inteligente; abaixo do threshold segue o fluxo normal.
- Intenções que **exigem escalação obrigatória**: `parecer_juridico`,
  `estrategia_processual`, `negociacao`, `decisao_judicial_impacto_alto` — vão
  direto para Claude Opus via `EscalationClient`.

## Confidence Router

Cada resposta recebe um score ponderado (0.0–1.0):
- intenção: 25%
- match do RAG: 35%
- tamanho da resposta: 20%
- contexto de processo: 20%

Abaixo do threshold do escritório (padrão **0.70**), a resposta é roteada para
Claude Opus. Não depende de LLM para calcular — é heurística barata.

## Fact-checker (anti-alucinação)

Antes de enviar, a resposta do Claude é validada contra os dados reais do banco
(`verification.py`). Se houver divergência, a resposta é corrigida ou descartada.
É o que impede a IA de inventar andamento ou prazo.

## Memória de conversa

`services/ai/memory.py` — histórico por cliente no Redis (lista, últimas ~100
mensagens, TTL 7 dias renovado a cada interação). A IA lembra o contexto da sessão.

## Modelos Claude (qual, para quê)

| Modelo | ID | Uso |
|---|---|---|
| Sonnet | `claude-sonnet-5` | Resposta padrão do orquestrador |
| Opus | `claude-opus-4-6` | Escalação premium + Hub do Advogado |
| Haiku | `claude-haiku-4-5-20251001` | DNA de prospecção, títulos de conversa, tarefas baratas |

`MODELO_ESCALACAO` nas settings define o modelo de escalação. Wrapper com retries
e controle de quota em `claude_client.py`; escalação em `escalation_client.py`.

## RAG — base de conhecimento do escritório

- Upload de PDF → extração (PyMuPDF) → chunks de 512 tokens (overlap 50) →
  embedding **Voyage `voyage-law-2`** (1024D; fallback OpenAI) → pgvector (HNSW).
- Busca semântica com re-ranking MMR (diversidade).
- Warm-up no startup: as 6 queries mais comuns são pré-aquecidas no Redis (TTL 24h).
- O conteúdo relevante é injetado no system prompt de cada resposta.
- Isolado por `escritorio_id`.

## Personas e tradução

- **Persona configurável:** cada escritório define nome, tom e especialidades.
- **Tradutor jurídico** (`juridical_translator.py`): converte termo técnico em
  linguagem acessível ao cliente.
- **Tracking de fase processual** (`processo_state.py`): conhecimento → instrução
  → saneamento → julgamento → recurso → execução → encerrado.

## Quota de tokens

Cada plano tem limite mensal (ver [02](02_negocio_e_planos.md)). Ao atingir,
o fluxo retorna mensagem de limite e **não chama a API** (`QuotaExcedidaError`).

## Canais de entrada

- Texto (WhatsApp via Evolution).
- Áudio → transcrição via Whisper antes do processamento.
- Imagens e documentos → recebidos e catalogados.

## Controle de envio

- Respeita janela comercial por escritório (ex.: só 8h–18h).
- Rate limit de 5 mensagens proativas/dia/cliente.
- Mensagens bloqueadas vão para `mensagens_agendadas`, despachadas a cada 5 min.
- Escrita humanizada no produto: sem emoji, sem travessão (mesma filosofia que a
  máquina de vendas leva ao extremo — ver [09](09_maquina_de_vendas.md)).
