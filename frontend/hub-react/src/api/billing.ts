/**
 * frontend/hub-react/src/api/billing.ts
 * ======================================
 * API client para o módulo de billing (Stripe).
 *
 * Endpoints cobertos:
 *   POST /billing/checkout  → cria Checkout Session e retorna URL
 *   GET  /billing/portal    → cria Billing Portal Session e retorna URL
 *   GET  /billing/status    → retorna status da assinatura
 */

import { api } from './client'

/* ── Tipos ───────────────────────────────────────────────────────────────── */

export type PlanoId = 'basico' | 'profissional' | 'escritorio'

export interface CheckoutResponse {
  checkout_url: string | null
  stripe_habilitado: boolean
}

export interface PortalResponse {
  portal_url: string | null
  stripe_habilitado: boolean
}

export interface StatusAssinatura {
  plano: PlanoId
  assinatura_status: 'trialing' | 'active' | 'past_due' | 'canceled' | 'unpaid' | 'incomplete'
  stripe_habilitado: boolean
  stripe_customer_id: string | null
  trial_expira_em: string | null   // ISO 8601
  assinatura_expira_em: string | null
  acesso_ativo: boolean
}

/* ── Metadata dos planos (labels, preços, features para UI) ─────────────── */

export interface PlanoMeta {
  id: PlanoId
  nome: string
  preco: string           // ex: "R$ 497"
  periodo: string         // ex: "/mês"
  descricao: string
  destaque: boolean
  features: string[]
  limite_advogados: string
  limite_processos: string
  limite_clientes: string
  tokens: string
}

export const PLANOS: PlanoMeta[] = [
  {
    id: 'basico',
    nome: 'Starter',
    preco: 'R$ 497',
    periodo: '/mês',
    descricao: 'Ideal para advogados autônomos e escritórios boutique.',
    destaque: false,
    features: [
      'IA WhatsApp 24h',
      'Monitoramento de processos',
      'Base RAG de conhecimento',
      'CRM Inteligente',
      'Analytics básico',
    ],
    limite_advogados: '1 advogado',
    limite_processos: 'até 30 processos',
    limite_clientes: 'até 50 clientes',
    tokens: '500K tokens Claude/mês',
  },
  {
    id: 'profissional',
    nome: 'Profissional',
    preco: 'R$ 1.997',
    periodo: '/mês',
    descricao: 'Para escritórios em crescimento com múltiplas áreas.',
    destaque: true,
    features: [
      'Tudo do Starter',
      'Hub do Advogado (Claude Opus)',
      'Prospecção Inteligente de Leads',
      'Analytics completo + exportação',
      'Suporte prioritário',
    ],
    limite_advogados: 'até 5 advogados',
    limite_processos: 'até 300 processos',
    limite_clientes: 'até 500 clientes',
    tokens: '2M tokens Claude/mês',
  },
  {
    id: 'escritorio',
    nome: 'Escritório',
    preco: 'R$ 4.997',
    periodo: '/mês',
    descricao: 'Para escritórios consolidados com grande volume.',
    destaque: false,
    features: [
      'Tudo do Profissional',
      'Clientes ilimitados',
      'Suporte dedicado',
      'SLA de resposta',
      'Onboarding assistido',
    ],
    limite_advogados: 'até 15 advogados',
    limite_processos: 'até 500 processos',
    limite_clientes: 'clientes ilimitados',
    tokens: '5M tokens Claude/mês',
  },
]

/* ── API calls ───────────────────────────────────────────────────────────── */

/**
 * Cria uma Checkout Session no Stripe para o plano escolhido.
 * Retorna a URL para redirecionar o usuário ao checkout hospedado pelo Stripe.
 */
export async function createCheckout(plano: PlanoId): Promise<CheckoutResponse> {
  const res = await api.post<CheckoutResponse>('/billing/checkout', { plano })
  return res.data
}

/**
 * Cria uma Billing Portal Session.
 * Retorna a URL para o cliente gerenciar cartão, plano e cancelamento.
 */
export async function getPortalUrl(): Promise<PortalResponse> {
  const res = await api.get<PortalResponse>('/billing/portal')
  return res.data
}

/**
 * Retorna o status atual da assinatura do escritório autenticado.
 */
export async function getBillingStatus(): Promise<StatusAssinatura> {
  const res = await api.get<StatusAssinatura>('/billing/status')
  return res.data
}

/* ── Helpers ─────────────────────────────────────────────────────────────── */

/** Retorna true se o status permite acesso às features pagas. */
export function isAssinaturaAtiva(status: StatusAssinatura['assinatura_status']): boolean {
  return status === 'active' || status === 'trialing'
}

/** Retorna label legível para o status da assinatura. */
export function labelStatus(status: StatusAssinatura['assinatura_status']): string {
  const map: Record<StatusAssinatura['assinatura_status'], string> = {
    trialing:   'Em período de avaliação',
    active:     'Ativa',
    past_due:   'Pagamento pendente',
    canceled:   'Cancelada',
    unpaid:     'Inadimplente',
    incomplete: 'Incompleta',
  }
  return map[status] ?? status
}

/** Redireciona o usuário para o Checkout do Stripe. */
export function redirectToCheckout(checkoutUrl: string): void {
  window.location.href = checkoutUrl
}

/** Redireciona o usuário para o Billing Portal do Stripe. */
export function redirectToPortal(portalUrl: string): void {
  window.location.href = portalUrl
}
