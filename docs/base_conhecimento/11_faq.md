# 11 — FAQ

Pares pergunta→resposta curta. Formato pensado para recuperação em RAG: cada
entrada é autocontida.

**O que é o Concierge Jurídico Digital?**
Um SaaS B2B que coloca uma IA no WhatsApp de escritórios de advocacia. A IA atende
os clientes do escritório 24h, avisa quando o processo anda em linguagem simples,
marca reuniões e escala para o advogado quando o assunto exige.

**Para quem é?**
Escritórios boutique (2–15 advogados), em crescimento (15–50) e advogados
autônomos com carteira. Áreas cível, trabalhista, previdenciário, família.

**Quanto custa?**
Essencial R$ 997/mês, Profissional R$ 1.997, Escritório R$ 4.997, Enterprise sob
consulta. Anual com 20% de desconto. Trial de 7 dias em qualquer plano.

**Qual a diferença entre os planos?**
Essencial: 1 advogado, RAG até 20 docs, analytics básico, sem CRM/Hub.
Profissional: até 5 advogados, RAG ilimitado, CRM e Hub (300K tokens Opus).
Escritório: até 15 advogados, Hub 1M tokens, implantação dedicada + SLA.

**A margem é boa?**
Sim: ~78% no Essencial, ~72% Profissional, ~71% Escritório (lucro líquido de
R$ 773 / R$ 1.432 / R$ 3.550 por cliente).

**Que modelos de IA usa?**
Claude Sonnet (`claude-sonnet-5`) no orquestrador, Claude Opus (`claude-opus-4-6`)
no Hub e escalação, Claude Haiku (4.5) em tarefas baratas. Embeddings via Voyage
`voyage-law-2` (fallback OpenAI). Áudio via Whisper.

**Como a IA evita inventar informação?**
Um fact-checker valida cada resposta contra os dados reais do banco antes de
enviar. Se a confiança é baixa, escala para o advogado em vez de chutar.

**Como decide escalar para o advogado?**
Dois caminhos: automático (Confidence Router — score ponderado abaixo de 0.70) ou
forçado (intenções como parecer_jurídico, estratégia, negociação).

**Como funciona o agendamento?**
A IA detecta o pedido, propõe 3 horários livres (evitando prazos e horários
ocupados no Google Calendar), o cliente escolhe, o advogado confirma (Hub ou
WhatsApp), vira evento no Google Calendar, com lembrete 24h e confirmação 3h antes.

**Como isola os dados entre escritórios?**
Row-level multi-tenancy: todas as tabelas têm `escritorio_id` e toda query filtra
por ele. Não há schema separado; nenhum escritório vê dado de outro.

**Que banco e infra usa?**
PostgreSQL 13 (asyncpg) + pgvector para RAG + Redis (cache/filas) + Celery/RedBeat
+ FastAPI. Deploy no Railway. WhatsApp via Evolution API self-hosted.

**A prospecção funciona?**
A Feature 3 está pausada: o DataJud público não retorna o campo `partes`, então a
descoberta de litigantes retorna zero. Retomada planejada com a API Escavador.
Não vender essa feature enquanto pausada.

**O que é a máquina de vendas / a Clara?**
Uma ferramenta interna (`feature_vendas`) que usa a tecnologia do produto para
prospectar advogados. A Clara é a persona de IA que conversa no WhatsApp, qualifica
o lead e passa para um sócio fechar. É isolada do produto por feature-flag.

**A Clara esconde que é uma IA?**
Não. Ela soa natural, mas se perguntada se é IA/robô/pessoa, responde a verdade
sempre — e usa isso como fechamento de venda. Nunca nega ser IA.

**Como a Clara sabe de onde veio o lead?**
Pelo `origem` do alvo (planilha) ou detectando na primeira mensagem o texto
pré-preenchido do link wa.me de cada canal ("recebi seu currículo", "vim pelo
site"). Isso vira contexto injetado no prompt, com roteiro por canal.

**A máquina de vendas exige novos serviços no Railway?**
Não. Pega carona na mesma API, worker, beat, Postgres e Redis. Só precisa de env
vars `VENDAS_*` e instâncias novas na Evolution (chips diferentes).

**Como garantir que a máquina de vendas não afeta o produto?**
Feature-flag: sem `VENDAS_TENANT_ID`, o produto boota idêntico (75 rotas, zero de
vendas, beat sem tasks de vendas). Os pontos de contato são guardados por try/except.

**O que ainda falta / não está pronto?**
Integração com Projuris/SAJ/Astrea, ML de prazos, app mobile, e a descoberta de
leads (Escavador). Bloqueador de produção: validar `alembic upgrade head` em
staging com dados reais.

**Qual o maior risco do negócio?**
A Evolution API é não-oficial: um número pode ser banido pela Meta. A migração
para a WhatsApp Business Cloud API oficial é prioridade quando houver cliente
pagante de verdade.
