# 02 — Negócio e Planos

Modelo: **SaaS B2B**, cobrança mensal recorrente por escritório, via Stripe.
Baixo churn estrutural — dados, persona e base RAG ficam no sistema, tornando a
troca custosa. Assinatura self-service (checkout + portal), trial de 7 dias.

## Tabela de planos (v2 — comercial)

| | Essencial (`basico`) | Profissional | Escritório | Enterprise |
|---|---|---|---|---|
| **Preço mensal** | R$ 997 | R$ 1.997 | R$ 4.997 | sob consulta |
| **Anual (–20%)** | R$ 797/mês | R$ 1.597/mês | R$ 3.997/mês | contratual |
| **Advogados** | 1 | até 5 | até 15 | ilimitado |
| **Processos** | 50 | 300 | 500 | ilimitado |
| **Clientes** | 100 | 500 | 10.000 | ilimitado |
| **Tokens Sonnet/mês** | 750K | 2M | 5M | ilimitado |
| **IA WhatsApp + agendamento** | ✅ | ✅ | ✅ | ✅ |
| **Monitoramento de processos** | ✅ | ✅ | ✅ | ✅ |
| **RAG (base de conhecimento)** | até 20 docs | ilimitado | ilimitado | ilimitado |
| **Analytics** | básico | completo + exportação | completo | completo |
| **CRM Inteligente** | ❌ | ✅ | ✅ | ✅ |
| **Hub do Advogado (Opus)** | ❌ | 300K tokens/mês | 1M tokens/mês | ilimitado |
| **Suporte/implantação** | self-service, email | prioritário | dedicada + SLA | SLA contratual |

> **IDs internos no código:** `basico`, `profissional`, `escritorio`, `enterprise`.
> "Essencial" é apenas o nome de exibição (display name) do plano `basico`.
> Ver `feature_1_ia_personalizada/services/billing/stripe_service.py`.

### Racional da estrutura
- **RAG limitado no Essencial** (não removido): garante que todo cliente acumula
  o moat (base de conhecimento própria) desde o dia 1, e preserva o upsell.
- **Analytics básico no Essencial:** a métrica "horas economizadas" é o que
  sustenta a renovação — precisa estar no plano de entrada.
- **Escada 2x → 2,5x:** cada upgrade é "engolível".

## Trial de 7 dias

Quotas reduzidas a ~20% do plano durante o trial (protege contra abuso sem
prejudicar a avaliação). Ao converter, os limites cheios são aplicados
automaticamente pelo webhook do Stripe.

Quotas de trial (código): Essencial 150K tokens / 10 processos / 20 clientes ·
Profissional 400K / 60 / 100 · Escritório 1M / 100 / 500.

Estados de assinatura rastreados: `trialing`, `active`, `past_due`, `canceled`,
`unpaid`, `incomplete`.

## Margens por cliente (com prompt caching ativo)

Custos variáveis: Claude API + infra Railway pro-rata + Stripe 2,5% + impostos
~15% (Simples Nacional). DataJud é gratuito.

| | Essencial | Profissional | Escritório |
|---|---|---|---|
| Receita | R$ 997 | R$ 1.997 | R$ 4.997 |
| Claude Sonnet (com caching) | R$ 22 | R$ 58 | R$ 145 |
| Claude Opus (Hub) | — | R$ 77 | R$ 255 |
| Infra Railway | R$ 25 | R$ 50 | R$ 100 |
| Enriquecimento CNPJ | — | R$ 25 | R$ 60 |
| Whisper (áudio) | R$ 2 | R$ 5 | R$ 12 |
| Stripe 2,5% | R$ 25 | R$ 50 | R$ 125 |
| Impostos ~15% | R$ 150 | R$ 300 | R$ 750 |
| **Lucro líquido/cliente** | **R$ 773** | **R$ 1.432** | **R$ 3.550** |
| **Margem líquida** | **78%** | **72%** | **71%** |

No plano anual (–20%), a margem cai ~2 p.p., compensada pelo caixa antecipado e
churn menor.

## Plano de 12 meses (jul/2026 → jul/2027)

Premissas: 3 sócios como equipe (sem folha fixa até o T3); 10 primeiros clientes
como design partners com desconto até dez/2026; ~8% do MRR em aquisição a partir
do T2; 1 pessoa de CS a partir de ~50 clientes.

| Trimestre | Foco | Clientes | MRR | Por sócio/mês |
|---|---|---|---|---|
| T1 set/2026 | Provar valor: 10 design partners; migração p/ WhatsApp Cloud API | 10 | ~R$ 9k | ~R$ 1,8k |
| T2 dez/2026 | Destravar captação (Escavador); cases; onboarding self-service | 28 | ~R$ 43k | ~R$ 9,7k |
| T3 mar/2027 | Distribuição (referral, OAB, contadores); contratar CS | 55 | ~R$ 92k | ~R$ 18k |
| T4 jun/2027 | Decisão bootstrapped × seed | 90 | ~R$ 155k | ~R$ 32k |

Run-rate fim do ano 1: ARR ~R$ 1,9M, lucro anualizado ~R$ 1,1M (~R$ 380k/sócio/ano).

### Sinais de alerta
- Churn > 5%/mês sustentado → parar de vender e corrigir produto.
- Ban de número WhatsApp → acelerar migração para a Cloud API oficial.
- Escavador não destravar a F3 → reposicionar pitch em retenção/atendimento.

## Riscos estruturais do negócio

1. **Evolution API** (não-oficial) é o maior risco: número pode ser banido pela
   Meta. Migração para a WhatsApp Business Cloud API oficial é prioridade.
2. **Dependência do Jusbrasil** como fonte primária de dados processuais.
3. **Prospecção (diferencial vendável) está bloqueada** até integrar o Escavador.
4. **Distribuição:** o produto está pronto para 100 clientes; o gargalo é o
   canal de venda, não a tecnologia.
