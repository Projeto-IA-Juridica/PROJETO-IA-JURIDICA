# 12 — Glossário

**Agendamento Inteligente** — feature que faz a IA marcar reuniões pelo WhatsApp:
propõe horários livres, respeita prazos e Google Calendar, o advogado só confirma.

**Alvo (alvos_vendas)** — um advogado/escritório-prospecto na máquina de vendas.
Tabela própria, separada de `leads_prospeccao`.

**Buffer de mensagens** — mecanismo que espera a pessoa terminar de falar: junta
uma rajada de mensagens picadas em uma entrada só antes de a IA responder.

**Chunker** — divide a resposta da IA em 1–3 balões curtos de WhatsApp e remove
tiques de LLM (emoji, markdown, travessão).

**Clara** — a persona de IA da máquina de vendas, que prospecta advogados.

**Confidence Router** — heurística (sem LLM) que dá um score 0–1 à resposta;
abaixo de 0.70 (padrão), roteia para Claude Opus.

**DataJud** — API pública do CNJ com dados processuais. Gratuita, usada como
backup. Não retorna o campo `partes` (por isso a prospecção está bloqueada).

**Design partner** — cliente inicial que ajuda a validar o produto (com desconto,
nunca de graça).

**DNA do advogado** — perfil de especialidades/setores do escritório extraído do
histórico de processos, usado na prospecção. Persistido em `escritorio.dna_prospeccao`.

**Escalação** — quando a IA passa o atendimento para o advogado humano.

**Escavador** — API (`api.escavador.com`) planejada para destravar a descoberta de
leads da Feature 3.

**Evolution API** — gateway self-hosted (não-oficial) que conecta o sistema ao
WhatsApp. Trabalha com múltiplas instâncias (parâmetro `instance`).

**Fact-checker** — valida a resposta da IA contra os dados reais do banco antes de
enviar (anti-alucinação).

**Feature 3 (F3)** — a Prospecção Inteligente. Pausada.

**feature_1_ia_personalizada** — o código do produto (o Concierge que os
escritórios pagam).

**feature_vendas** — o código da máquina de vendas interna (a Clara).

**Handoff** — a passagem do lead quente para um sócio humano fechar.

**Hub do Advogado** — interface exclusiva do advogado (análise de petição,
consulta jurídica) com Claude Opus.

**ICP (Ideal Customer Profile)** — o perfil de cliente-alvo; também o score A/B/C
de filtragem de alvos na prospecção.

**Lead quente** — lead pronto para handoff (pediu preço/trial/reunião, ou 5+
advogados engajado, ou qualificação completa).

**LangGraph** — biblioteca de orquestração; monta o grafo de nós que processa cada
mensagem.

**Mensagem-espelho** — abordagem que mostra ao advogado a notificação que o
cliente dele teria recebido, a partir de um processo real dele.

**Moat** — vantagem competitiva defensável (base RAG própria, persona treinada,
dados acumulados).

**Multi-tenancy** — arquitetura em que vários escritórios compartilham o sistema,
isolados por `escritorio_id` (row-level).

**Número-vitrine** — número de WhatsApp de demonstração onde o advogado conversa
com a Clara como se fosse cliente dele.

**Opt-out** — pedido do lead para não ser mais contatado; respeitado para sempre
em código.

**pgvector** — extensão do PostgreSQL para busca vetorial (RAG), dim 1024, HNSW.

**Persona** — nome, tom e estilo que cada escritório configura para sua IA.

**Provimento 205/2021** — norma da OAB sobre publicidade/atuação; base do
compliance da IA (não dá parecer, escala para humano, disclaimer).

**Quota de tokens** — limite mensal de tokens Claude por plano; ao atingir, o
fluxo para de chamar a API.

**RAG (Retrieval-Augmented Generation)** — a IA responde usando os documentos do
próprio escritório (petições, teses) recuperados por busca vetorial.

**RedBeat** — scheduler do Celery com schedules dinâmicos no Redis.

**Score de risco** — pontuação 0–100 de risco de um processo; visível só ao
advogado (compliance OAB).

**SSE (Server-Sent Events)** — stream em tempo real; usado para o card de
aprovação de reunião aparecer instantâneo no Hub.

**Tenant** — um escritório (no produto) ou o escritório de vendas
(`VENDAS_TENANT_ID`, na máquina de vendas).

**Trial** — 7 dias grátis com quotas reduzidas (~20% do plano).

**Voyage / voyage-law-2** — modelo de embeddings especializado em jurídico usado
no RAG (fallback OpenAI).
