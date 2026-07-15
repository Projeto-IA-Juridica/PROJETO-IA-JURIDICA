# Base de Conhecimento — Concierge Jurídico Digital

Esta pasta é a fonte única de verdade sobre o projeto: o produto, a arquitetura,
o modelo de negócio e a máquina de vendas. Foi escrita para dois leitores:

1. **Uma pessoa** que precisa entender qualquer parte do sistema sem ler o código.
2. **Uma IA** que ingere estes arquivos (RAG) e passa a responder qualquer dúvida
   sobre o projeto como especialista.

> Última consolidação: 14/07/2026, a partir do código real (não de memória).
> Ao mudar o sistema, atualize o arquivo temático correspondente — a regra de
> ouro é: **este documento nunca promete o que o código não faz.**

## Como está organizada

Cada arquivo é um tema fechado, escrito para ser recuperável isoladamente (um
chunk de RAG não carrega o contexto dos outros). Por isso há repetição proposital
de definições entre arquivos — cada um se sustenta sozinho.

| Arquivo | Tema | Responde perguntas como |
|---|---|---|
| [01_visao_geral.md](01_visao_geral.md) | O que é, que problema resolve, para quem | "O que o produto faz?" "Quem é o público?" |
| [02_negocio_e_planos.md](02_negocio_e_planos.md) | Planos, preços, margens, projeção | "Quanto custa?" "Qual a margem do Essencial?" |
| [03_arquitetura_e_stack.md](03_arquitetura_e_stack.md) | Stack, multi-tenancy, fluxo, deploy | "Que banco usa?" "Como isola os escritórios?" |
| [04_modelo_de_dados.md](04_modelo_de_dados.md) | As 12 tabelas e seus campos | "Que campos tem o Processo?" |
| [05_motor_de_ia.md](05_motor_de_ia.md) | Orquestrador, nós, confidence, fact-check, RAG | "Como decide escalar?" "Qual modelo usa?" |
| [06_funcionalidades.md](06_funcionalidades.md) | Cada feature do produto em detalhe | "Como funciona o agendamento?" |
| [07_api_endpoints.md](07_api_endpoints.md) | Todas as rotas HTTP | "Qual endpoint sobe petição?" |
| [08_workers_e_agendados.md](08_workers_e_agendados.md) | Tasks Celery e seus horários | "De quanto em quanto monitora processo?" |
| [09_maquina_de_vendas.md](09_maquina_de_vendas.md) | feature_vendas: Clara, funil, humanização | "Como a Clara sabe de onde veio o lead?" |
| [10_seguranca_e_compliance.md](10_seguranca_e_compliance.md) | LGPD, OAB, JWT, criptografia | "Onde a IA respeita a OAB?" |
| [11_faq.md](11_faq.md) | Perguntas diretas com resposta curta | (pares pergunta→resposta para o RAG) |
| [12_glossario.md](12_glossario.md) | Termos do projeto e do domínio | "O que é confidence router?" |
| [MANIFESTO_RAG.md](MANIFESTO_RAG.md) | Como transformar esta pasta num RAG | (instruções de ingestão) |

## Resumo em 30 segundos

O **Concierge Jurídico Digital** é um SaaS B2B que coloca uma IA no WhatsApp de
escritórios de advocacia. A IA atende os clientes do escritório 24h, avisa
proativamente quando o processo anda (em linguagem simples), marca reuniões na
agenda do advogado e escala para o humano quando o assunto exige. Há um **Hub do
Advogado** (análise de petições e consulta com Claude Opus) e uma feature de
prospecção pausada. Cobrança via Stripe, 3 planos (R$ 997 / 1.997 / 4.997) mais
Enterprise, trial de 7 dias.

Em paralelo, existe uma **máquina de vendas interna** (`feature_vendas`) — uma
persona de IA chamada **Clara** que prospecta advogados pelo WhatsApp com
humanização extrema, qualifica o lead e passa o bastão para um sócio fechar. Ela
é isolada do produto principal por um feature-flag: desligada, o produto roda
idêntico.

## Números do projeto (14/07/2026)

- **12 tabelas** no banco · **31 migrations**
- **19 rotas** HTTP no produto + rotas isoladas de vendas
- **11 workers** Celery no produto + 2 de vendas
- **45 testes unitários + 18 de integração** no produto · **68 testes** em vendas
- **16 páginas** no Hub React (advogado) + **9** no Admin
- Cobertura mínima exigida no CI: **70%**
