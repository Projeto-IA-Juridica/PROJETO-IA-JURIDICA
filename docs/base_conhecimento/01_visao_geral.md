# 01 — Visão Geral

## O problema

Escritórios de advocacia perdem clientes por falta de comunicação, não por falta
de competência. O cliente não sabe o que acontece no processo dele, precisa ligar
para obter uma atualização básica, e o advogado gasta horas por semana respondendo
no WhatsApp as mesmas perguntas: "tem novidade?", "o que significa esse termo?",
"e agora?". Ao mesmo tempo, captar cliente novo é artesanal — indicação, anúncio
genérico, ou garimpo manual.

## A solução

O **Concierge Jurídico Digital** é uma IA que o escritório implanta no próprio
WhatsApp em menos de 30 minutos. A partir daí:

- **O cliente recebe atualização proativa** assim que o processo anda, em
  linguagem de gente, sem precisar perguntar.
- **Dúvidas frequentes são respondidas na hora** pela IA, com o nome e o tom do
  escritório.
- **A IA marca reuniões** sozinha: propõe horários livres, respeita prazos
  processuais e o Google Calendar, e o advogado só confirma.
- **O advogado é acionado só quando necessário** — parecer, estratégia, decisão
  de impacto, situação sensível.

Resultado: mais clientes atendidos, menos tempo operacional, relação mais próxima.

## Frase de elevador

> "Uma IA que conhece todos os seus processos, fala com seus clientes no WhatsApp
> 24h no seu tom, marca reuniões respeitando seus prazos e sua agenda, e nunca
> deixa um cliente sem resposta — chamando você só quando o assunto exige um
> advogado."

Para o advogado: menos tempo no WhatsApp, mais tempo faturando.
Para o cliente: transparência e proximidade.
Para o escritório: crescer sem contratar na mesma proporção.

## Público-alvo (ICP — Ideal Customer Profile)

| Segmento | Perfil | Dor principal |
|---|---|---|
| **Boutique** (2–15 advogados) | Cível, trabalhista, família, previdenciário | Sem estrutura para atendimento proativo |
| **Em crescimento** (15–50) | Mais de uma área | Escalar atendimento sem contratar na proporção |
| **Autônomo com carteira** | Qualquer área | Atendimento 24h sem custo fixo de funcionário |

**Fora do escopo hoje:** escritórios enterprise com sistema legado (Projuris, SAJ)
— dependem de integração ainda não construída.

## Como gera valor

Para o escritório: reduz ~70–80% das perguntas rotineiras sem escalar; estima-se
3–5h/semana economizadas por advogado; elimina o secretariado do agendamento;
o CRM identifica cliente esfriando antes do churn; o Hub analisa petição em
segundos.

Para o cliente final: sabe o que acontece sem ligar, recebe explicação simples,
tem canal disponível a qualquer hora.

## Estado do projeto (14/07/2026)

- **MVP (atendimento + monitoramento + RAG + CRM + analytics):** em produção.
- **Agendamento Inteligente:** em produção.
- **Hub do Advogado (Claude Opus):** funcional (~95%).
- **Billing (Stripe + trial):** em produção.
- **Prospecção (Feature 3):** ⏸️ **pausada** — o DataJud público não retorna o
  campo `partes`, então a descoberta de litigantes retorna zero. Retomada
  planejada com a API Escavador.
- **Máquina de vendas interna (Clara):** construída e testada, isolada por flag.
- **Backlog não iniciado:** Controladoria/Projuris, ML de prazos, app mobile,
  integração nativa com CRMs.

## Relação entre "o produto" e "a máquina de vendas"

São duas coisas distintas e não devem ser confundidas:

- **O produto** é o Concierge que os escritórios pagam para usar (`feature_1_ia_personalizada`).
- **A máquina de vendas** (`feature_vendas`) é uma ferramenta interna que usa a
  mesma tecnologia para *vender o produto*: a persona Clara prospecta advogados.
  É dogfooding — a IA de vendas é o próprio produto apontado para nós mesmos.

Ver [09_maquina_de_vendas.md](09_maquina_de_vendas.md) para o detalhe da Clara.
