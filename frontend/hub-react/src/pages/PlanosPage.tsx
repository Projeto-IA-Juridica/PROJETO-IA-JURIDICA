import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { Check, ExternalLink, AlertTriangle, Clock, Loader2, CheckCircle } from 'lucide-react'
import {
  PLANOS,
  getBillingStatus,
  getPortalUrl,
  createCheckout,
  redirectToCheckout,
  redirectToPortal,
  labelStatus,
  isAssinaturaAtiva,
  precoComDesconto,
  seloDesconto,
  type PlanoId,
} from '../api/billing'

/* ── Features por plano ── */

const FEATURES: Record<PlanoId, string[]> = {
  basico: [
    'IA WhatsApp 24h com persona customizada',
    'Monitoramento de até 30 processos',
    'Base RAG de conhecimento jurídico',
    'CRM Inteligente com análise de risco',
    'Analytics básico',
    'Suporte por e-mail',
  ],
  profissional: [
    'Tudo do Starter',
    'Hub do Advogado com Claude Opus — 300K tokens/mês',
    'Prospecção Inteligente de Leads',
    'Analytics completo + exportação CSV',
    'Suporte prioritário',
  ],
  escritorio: [
    'Tudo do Profissional',
    'Hub do Advogado com Claude Opus — 1M tokens/mês',
    'Clientes ilimitados',
    'Suporte dedicado com SLA',
    'Onboarding assistido',
  ],
}

const LIMITE: Record<PlanoId, string> = {
  basico:       '1 advogado · 30 processos · 50 clientes · 500K tokens/mês',
  profissional: 'até 5 advogados · 300 processos · 500 clientes · 2M tokens/mês',
  escritorio:   'até 15 advogados · 500 processos · ilimitado · 5M tokens/mês',
}

/* ── Banner de status ── */

function StatusBanner({
  billing,
  onAbrirPortal,
  abrindoPortal,
}: {
  billing: Awaited<ReturnType<typeof getBillingStatus>>
  onAbrirPortal: () => void
  abrindoPortal: boolean
}) {
  const ativo     = isAssinaturaAtiva(billing.assinatura_status)
  const planoMeta = PLANOS.find(p => p.id === billing.plano)
  const trialStr  = billing.trial_expira_em
    ? new Date(billing.trial_expira_em).toLocaleDateString('pt-BR') : null
  const expStr = billing.assinatura_expira_em
    ? new Date(billing.assinatura_expira_em).toLocaleDateString('pt-BR') : null

  const isTrialing = billing.assinatura_status === 'trialing'
  const isPastDue  = !ativo

  const icon    = isPastDue ? <AlertTriangle size={13} /> : isTrialing ? <Clock size={13} /> : <CheckCircle size={13} />
  const bgColor = isPastDue ? 'rgba(200,48,48,0.05)' : 'rgba(12,30,48,0.03)'
  const bdColor = isPastDue ? 'rgba(200,48,48,0.18)' : 'var(--color-am-border)'
  const txColor = isPastDue ? '#C83030' : isTrialing ? 'var(--color-am-blue)' : '#1A9E78'

  const texto = isTrialing
    ? `Período de avaliação gratuito${trialStr ? ` · Expira em ${trialStr}` : ''}`
    : ativo
    ? `Plano ${planoMeta?.nome ?? billing.plano} ativo${expStr ? ` · Próxima cobrança em ${expStr}` : ''}`
    : `${labelStatus(billing.assinatura_status)} — ${billing.assinatura_status === 'past_due' ? 'atualize o método de pagamento.' : 'reative sua assinatura.'}`

  return (
    <div className="flex items-center justify-between gap-3 flex-wrap px-4 py-3 rounded-xl"
      style={{ background: bgColor, border: `1px solid ${bdColor}` }}>
      <div className="flex items-center gap-2" style={{ color: txColor }}>
        {icon}
        <span className="text-xs text-am-secondary">{texto}</span>
      </div>
      {billing.stripe_habilitado && billing.stripe_customer_id && (
        <button
          type="button" onClick={onAbrirPortal} disabled={abrindoPortal}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-bold transition-fast"
          style={{ color: 'var(--color-am-blue)', border: '1px solid rgba(18,72,190,0.22)', background: 'rgba(18,72,190,0.04)', opacity: abrindoPortal ? 0.7 : 1, cursor: abrindoPortal ? 'not-allowed' : 'pointer' }}
        >
          {abrindoPortal ? <Loader2 size={10} className="animate-spin" /> : <ExternalLink size={10} />}
          Gerenciar assinatura
        </button>
      )}
    </div>
  )
}

/* ── Card de plano ── */

function PlanoCard({
  plano,
  isAtual,
  isAtivo,
  onEscolher,
  carregando,
  index,
}: {
  plano: typeof PLANOS[number]
  isAtual: boolean
  isAtivo: boolean
  onEscolher: (id: PlanoId) => void
  carregando: boolean
  index: number
}) {
  const features = FEATURES[plano.id]
  const limite   = LIMITE[plano.id]
  const destaque = plano.destaque && !isAtual

  // Desconto promocional: preço final e selo (null quando o plano não tem desconto)
  const precoFinal = precoComDesconto(plano)
  const selo       = seloDesconto(plano)

  const accentColor  = isAtual ? '#1A9E78' : 'var(--color-am-blue)'
  const shadowBase   = destaque
    ? '0 4px 24px rgba(18,72,190,0.1)'
    : isAtual
    ? '0 4px 24px rgba(26,158,120,0.1)'
    : '0 1px 6px rgba(12,30,48,0.06)'
  const shadowHover  = destaque
    ? '0 20px 48px rgba(18,72,190,0.18)'
    : isAtual
    ? '0 20px 48px rgba(26,158,120,0.16)'
    : '0 16px 40px rgba(12,30,48,0.12)'

  return (
    <motion.div
      initial={{ opacity: 0, y: 48 }}
      animate={{ opacity: 1, y: 0, boxShadow: shadowBase }}
      whileHover={{ y: -8, boxShadow: shadowHover }}
      transition={{ type: 'spring', stiffness: 280, damping: 22, delay: index * 0.1 }}
      className="bg-white rounded-2xl flex flex-col overflow-hidden relative"
      style={{
        border: isAtual
          ? '1.5px solid #1A9E78'
          : destaque
          ? '1.5px solid var(--color-am-blue)'
          : '1px solid var(--color-am-border)',
      }}
    >
      {/* Faixa superior colorida */}
      <div style={{
        height: 3,
        background: isAtual
          ? 'linear-gradient(90deg,#1A9E78,#25C896)'
          : destaque
          ? 'linear-gradient(90deg,#1248BE,#6B7CFF)'
          : 'transparent',
      }} />

      {/* Header */}
      <div className="flex items-center justify-between px-5 py-4"
        style={{ borderBottom: '1px solid var(--color-am-border)', background: (destaque || isAtual) ? `${isAtual ? 'rgba(26,158,120,0.03)' : 'rgba(18,72,190,0.03)'}` : 'rgba(12,30,48,0.02)' }}>
        <span className="text-[10px] font-bold uppercase tracking-wider text-am-secondary">{plano.nome}</span>
        {isAtual && (
          <span className="text-[10px] font-bold px-2 py-0.5 rounded-full"
            style={{ color: '#1A9E78', background: 'rgba(26,158,120,0.1)', border: '1px solid rgba(26,158,120,0.2)' }}>
            Plano atual
          </span>
        )}
        {destaque && (
          <span className="text-[10px] font-bold px-2 py-0.5 rounded-full"
            style={{ color: 'var(--color-am-blue)', background: 'rgba(18,72,190,0.08)', border: '1px solid rgba(18,72,190,0.18)' }}>
            Mais popular
          </span>
        )}
      </div>

      <div className="flex flex-col flex-1 px-5 pt-5 pb-6 gap-5">

        {/* Preço + descrição */}
        <div>
          {precoFinal && selo && (
            <div className="flex items-center gap-2 mb-0.5">
              <span className="text-sm text-am-muted line-through">{plano.preco}</span>
              <span className="text-[10px] font-bold px-1.5 py-0.5 rounded"
                style={{ color: '#fff', background: '#1A9E78' }}>
                {selo}
              </span>
            </div>
          )}
          <div className="flex items-baseline gap-1.5">
            <span className="text-3xl font-black tracking-tight"
              style={{ color: (destaque || isAtual) ? accentColor : 'var(--color-am-ink)' }}>
              {precoFinal ?? plano.preco}
            </span>
            <span className="text-xs text-am-muted">{plano.periodo}</span>
          </div>
          <p className="text-[11px] text-am-muted mt-1.5 leading-snug">{plano.descricao}</p>
        </div>

        {/* Limites */}
        <p className="text-[10px] text-am-muted leading-relaxed pb-4"
          style={{ borderBottom: '1px solid var(--color-am-border)' }}>
          {limite}
        </p>

        {/* Features */}
        <ul className="flex-1 space-y-2.5">
          {features.map(f => (
            <li key={f} className="flex items-start gap-2.5">
              <Check size={12} className="flex-shrink-0 mt-0.5" style={{ color: '#1A9E78' }} />
              <span className="text-[11px] text-am-secondary leading-snug">{f}</span>
            </li>
          ))}
        </ul>

        {/* CTA */}
        <motion.button
          type="button"
          onClick={() => !isAtual && !carregando && onEscolher(plano.id)}
          disabled={isAtual || carregando}
          whileTap={{ scale: isAtual ? 1 : 0.97 }}
          whileHover={isAtual ? {} : { opacity: 0.88 }}
          transition={{ duration: 0.15 }}
          className="w-full py-3 rounded-xl text-xs font-bold flex items-center justify-center gap-2 mt-1"
          style={
            isAtual
              ? { background: 'rgba(26,158,120,0.07)', color: '#1A9E78', border: '1px solid rgba(26,158,120,0.22)', cursor: 'default' }
              : destaque
              ? { background: 'var(--color-am-blue)', color: '#fff', cursor: carregando ? 'not-allowed' : 'pointer', opacity: carregando ? 0.7 : 1 }
              : { background: 'white', color: 'var(--color-am-blue)', border: '1px solid rgba(18,72,190,0.28)', cursor: carregando ? 'not-allowed' : 'pointer', opacity: carregando ? 0.7 : 1 }
          }
        >
          {carregando && <Loader2 size={12} className="animate-spin" />}
          {isAtual ? 'Plano atual' : isAtivo ? 'Fazer upgrade' : 'Começar grátis por 7 dias'}
        </motion.button>

      </div>
    </motion.div>
  )
}

/* ── Page ── */

export default function PlanosPage() {
  const [carregando, setCarregando]       = useState<PlanoId | null>(null)
  const [erro, setErro]                   = useState<string | null>(null)
  const [abrindoPortal, setAbrindoPortal] = useState(false)
  const [portalErro, setPortalErro]       = useState<string | null>(null)

  const { data: billing, isLoading: billingLoading } = useQuery({
    queryKey: ['billing-status'],
    queryFn: getBillingStatus,
    staleTime: 60_000,
  })

  async function handleEscolher(plano: PlanoId) {
    setErro(null)
    setCarregando(plano)
    try {
      const res = await createCheckout(plano)
      if (res.checkout_url) {
        redirectToCheckout(res.checkout_url)
      } else {
        setErro('Pagamento não configurado neste ambiente. Contate o suporte.')
        setCarregando(null)
      }
    } catch {
      setErro('Erro ao redirecionar para o checkout. Tente novamente.')
      setCarregando(null)
    }
  }

  async function handleAbrirPortal() {
    setPortalErro(null)
    setAbrindoPortal(true)
    try {
      const res = await getPortalUrl()
      if (res.portal_url) {
        redirectToPortal(res.portal_url)
      } else {
        setPortalErro('Portal de pagamento não configurado neste ambiente.')
      }
    } catch {
      setPortalErro('Erro ao abrir o portal. Tente novamente.')
    } finally {
      setAbrindoPortal(false)
    }
  }

  const planoAtual      = billing?.plano as PlanoId | undefined
  const assinaturaAtiva = billing ? isAssinaturaAtiva(billing.assinatura_status) : false

  return (
    <div className="flex-1 overflow-y-auto flex flex-col">
      <div className="flex-1 flex flex-col items-center justify-center px-6 py-10">
        <div className="w-full max-w-5xl space-y-6">

          {/* Header */}
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, ease: 'easeOut' }}
          >
            <h2 className="text-sm font-bold text-am-ink tracking-tight">Planos & Preços</h2>
            <p className="text-xs text-am-muted mt-0.5">7 dias grátis · Cancele quando quiser · Sem fidelidade</p>
          </motion.div>

          {/* Status banner */}
          {billingLoading ? (
            <div className="flex items-center gap-2 px-4 py-3 rounded-xl"
              style={{ background: 'rgba(12,30,48,0.03)', border: '1px solid var(--color-am-border)' }}>
              <Loader2 size={12} className="animate-spin text-am-muted" />
              <span className="text-xs text-am-muted">Verificando assinatura…</span>
            </div>
          ) : billing ? (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.3, delay: 0.1 }}
            >
              <StatusBanner billing={billing} onAbrirPortal={handleAbrirPortal} abrindoPortal={abrindoPortal} />
            </motion.div>
          ) : null}

          {portalErro && (
            <p className="text-xs" style={{ color: '#C83030' }}>{portalErro}</p>
          )}

          {/* Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-5">
            {PLANOS.map((plano, i) => (
              <PlanoCard
                key={plano.id}
                plano={plano}
                isAtual={planoAtual === plano.id}
                isAtivo={assinaturaAtiva}
                onEscolher={handleEscolher}
                carregando={carregando === plano.id}
                index={i}
              />
            ))}
          </div>

          {erro && (
            <div className="flex items-center gap-2 px-4 py-3 rounded-xl text-xs"
              style={{ background: 'rgba(200,48,48,0.05)', border: '1px solid rgba(200,48,48,0.18)', color: '#C83030' }}>
              <AlertTriangle size={12} />
              {erro}
            </div>
          )}

          {/* Rodapé */}
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.3, delay: 0.45 }}
            className="text-center text-[11px] text-am-muted"
          >
            Pagamento seguro via <strong className="text-am-ink">Stripe</strong> · Cartão de crédito e PIX ·{' '}
            <a href="mailto:suporte@amicus.com.br" style={{ color: 'var(--color-am-blue)' }}>
              Dúvidas? Fale conosco
            </a>
          </motion.p>

        </div>
      </div>
    </div>
  )
}
