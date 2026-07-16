/**
 * frontend/hub-react/src/pages/PlanoPage.tsx
 * ===========================================
 * Página de seleção de planos do Concierge Jurídico Digital.
 *
 * Usada em dois contextos:
 *   1. Landing / pré-onboarding — usuário escolhe o plano antes de cadastrar
 *   2. Upgrade — usuário logado quer mudar de plano
 *
 * Em modo de upgrade (prop `modo="upgrade"`), chama /billing/checkout
 * diretamente. Em modo landing (padrão), chama onSelect com o plano e
 * redireciona para o onboarding.
 */

import { useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { Loader2, CheckCircle, Zap, Building2, Crown } from 'lucide-react'
import {
  PLANOS,
  createCheckout,
  redirectToCheckout,
  precoComDesconto,
  seloDesconto,
  type PlanoId,
  type PlanoMeta,
} from '../api/billing'

/* ── Props ───────────────────────────────────────────────────────────────── */

interface Props {
  /** Chamado quando usuário escolhe um plano em modo landing */
  onSelect?: (plano: PlanoId) => void
  /** 'landing' (default) ou 'upgrade' (usuário já logado) */
  modo?: 'landing' | 'upgrade'
  /** Plano atual (para destacar em modo upgrade) */
  planoAtual?: PlanoId
}

/* ── Ícones por plano ────────────────────────────────────────────────────── */

const PLANO_ICONS: Record<PlanoId, ReactNode> = {
  basico:       <Zap size={20} />,
  profissional: <Building2 size={20} />,
  escritorio:   <Crown size={20} />,
}

/* ── Componente principal ────────────────────────────────────────────────── */

export default function PlanoPage({ onSelect, modo = 'landing', planoAtual }: Props) {
  const [carregando, setCarregando] = useState<PlanoId | null>(null)
  const [erro, setErro] = useState<string | null>(null)

  async function handleEscolher(plano: PlanoId) {
    setErro(null)

    if (modo === 'landing' && onSelect) {
      onSelect(plano)
      return
    }

    // Modo upgrade: cria checkout diretamente
    setCarregando(plano)
    try {
      const res = await createCheckout(plano)
      if (res.checkout_url) {
        redirectToCheckout(res.checkout_url)
      } else if (!res.stripe_habilitado) {
        setErro('Pagamento não está configurado neste ambiente. Contate o suporte.')
      }
    } catch {
      setErro('Erro ao redirecionar para o checkout. Tente novamente.')
    } finally {
      setCarregando(null)
    }
  }

  return (
    <div style={containerSt}>
      {/* Header */}
      <div style={{ textAlign: 'center', marginBottom: 40 }}>
        <AmicusLogo />
        <h1 style={h1St}>Escolha o plano ideal para o seu escritório</h1>
        <p style={subtitleSt}>
          7 dias grátis · Cancele quando quiser · Sem fidelidade
        </p>
      </div>

      {/* Cards */}
      <div style={gridSt}>
        {PLANOS.map(plano => (
          <PlanoCard
            key={plano.id}
            plano={plano}
            ativo={planoAtual === plano.id}
            carregando={carregando === plano.id}
            onEscolher={handleEscolher}
          />
        ))}
      </div>

      {/* Erro */}
      {erro && (
        <div style={erroSt}>{erro}</div>
      )}

      {/* Rodapé */}
      <div style={{ textAlign: 'center', marginTop: 32, fontSize: 12, color: 'var(--color-am-muted)' }}>
        Pagamento seguro via <strong>Stripe</strong> · Aceita cartão de crédito e PIX ·{' '}
        <a href="mailto:suporte@conciergejuridico.com" style={{ color: 'var(--color-am-blue)' }}>
          Dúvidas? Fale conosco
        </a>
      </div>
    </div>
  )
}

/* ── Card de plano ───────────────────────────────────────────────────────── */

interface CardProps {
  plano: PlanoMeta
  ativo: boolean
  carregando: boolean
  onEscolher: (plano: PlanoId) => void
}

function PlanoCard({ plano, ativo, carregando, onEscolher }: CardProps) {
  return (
    <div
      style={{
        position: 'relative',
        background: '#fff',
        borderRadius: 20,
        padding: '28px 24px',
        border: plano.destaque
          ? '2px solid var(--color-am-blue)'
          : ativo
          ? '2px solid var(--color-am-green)'
          : '1px solid var(--color-am-border)',
        boxShadow: plano.destaque
          ? '0 8px 32px rgba(18,72,190,0.12)'
          : '0 1px 4px rgba(12,30,48,0.06)',
        display: 'flex',
        flexDirection: 'column',
        gap: 0,
        transition: 'transform 0.15s, box-shadow 0.15s',
      }}
    >
      {/* Badge "Mais popular" */}
      {plano.destaque && (
        <div style={badgeSt}>⭐ Mais popular</div>
      )}
      {ativo && (
        <div style={{ ...badgeSt, background: 'var(--color-am-green)', color: '#fff' }}>
          Plano atual
        </div>
      )}

      {/* Header do card */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
        <div style={{
          width: 40, height: 40, borderRadius: 12, display: 'flex', alignItems: 'center',
          justifyContent: 'center',
          background: plano.destaque ? 'rgba(18,72,190,0.08)' : 'var(--color-am-bg)',
          color: plano.destaque ? 'var(--color-am-blue)' : 'var(--color-am-secondary)',
        }}>
          {PLANO_ICONS[plano.id]}
        </div>
        <div>
          <div style={{ fontSize: 15, fontWeight: 800, color: 'var(--color-am-ink)', letterSpacing: '-0.02em' }}>
            {plano.nome}
          </div>
          <div style={{ fontSize: 11, color: 'var(--color-am-muted)' }}>{plano.descricao}</div>
        </div>
      </div>

      {/* Preço */}
      <div style={{ marginBottom: 16 }}>
        {precoComDesconto(plano) && seloDesconto(plano) && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 2 }}>
            <span style={{ fontSize: 14, color: 'var(--color-am-muted)', textDecoration: 'line-through' }}>
              {plano.preco}
            </span>
            <span style={{ fontSize: 10, fontWeight: 700, color: '#fff', background: '#1A9E78', padding: '2px 6px', borderRadius: 4 }}>
              {seloDesconto(plano)}
            </span>
          </div>
        )}
        <span style={{ fontSize: 32, fontWeight: 900, color: 'var(--color-am-ink)', letterSpacing: '-0.04em' }}>
          {precoComDesconto(plano) ?? plano.preco}
        </span>
        <span style={{ fontSize: 13, color: 'var(--color-am-muted)', marginLeft: 4 }}>{plano.periodo}</span>
      </div>

      {/* Limites */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 16 }}>
        {[plano.limite_advogados, plano.limite_processos, plano.limite_clientes].map(l => (
          <span key={l} style={tagSt}>{l}</span>
        ))}
        <span style={tagSt}>{plano.tokens}</span>
      </div>

      {/* Features */}
      <ul style={{ margin: '0 0 20px', padding: 0, listStyle: 'none', flex: 1 }}>
        {plano.features.map(f => (
          <li key={f} style={{ display: 'flex', alignItems: 'flex-start', gap: 8, marginBottom: 7 }}>
            <CheckCircle size={14} style={{ color: 'var(--color-am-green)', flexShrink: 0, marginTop: 2 }} />
            <span style={{ fontSize: 12, color: 'var(--color-am-secondary)', lineHeight: 1.4 }}>{f}</span>
          </li>
        ))}
      </ul>

      {/* CTA */}
      <button
        onClick={() => onEscolher(plano.id)}
        disabled={carregando || ativo}
        style={{
          width: '100%',
          padding: '11px 20px',
          borderRadius: 12,
          fontFamily: 'var(--font-sans)',
          fontSize: 13,
          fontWeight: 700,
          cursor: carregando || ativo ? 'not-allowed' : 'pointer',
          opacity: ativo ? 0.6 : 1,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 8,
          background: plano.destaque
            ? 'linear-gradient(135deg, #1248BE 0%, #3A7AB8 100%)'
            : '#fff',
          color: plano.destaque ? '#fff' : 'var(--color-am-blue)',
          boxShadow: plano.destaque
            ? '0 4px 16px rgba(18,72,190,0.22)'
            : 'none',
          border: plano.destaque ? 'none' : '1.5px solid var(--color-am-blue)',
        } as CSSProperties}
      >
        {carregando && <Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} />}
        {ativo ? 'Plano atual' : carregando ? 'Aguardando…' : 'Começar grátis por 7 dias →'}
      </button>
    </div>
  )
}

/* ── Logo ─────────────────────────────────────────────────────────────────── */

function AmicusLogo() {
  return (
    <span style={{
      display: 'inline-block',
      marginBottom: 20,
      fontSize: 28, fontWeight: 900, letterSpacing: '-0.04em',
      background: 'linear-gradient(135deg, #0C1E30 0%, #1248BE 100%)',
      WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent',
      backgroundClip: 'text', fontFamily: 'var(--font-sans)',
    }}>
      amicus
    </span>
  )
}

/* ── Estilos ─────────────────────────────────────────────────────────────── */

const containerSt: CSSProperties = {
  minHeight: '100vh',
  background: 'var(--color-am-bg)',
  fontFamily: 'var(--font-sans)',
  padding: '48px 24px',
  maxWidth: 1100,
  margin: '0 auto',
}

const h1St: CSSProperties = {
  fontSize: 28,
  fontWeight: 900,
  color: 'var(--color-am-ink)',
  letterSpacing: '-0.03em',
  lineHeight: 1.2,
  marginBottom: 10,
}

const subtitleSt: CSSProperties = {
  fontSize: 14,
  color: 'var(--color-am-muted)',
  lineHeight: 1.6,
}

const gridSt: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
  gap: 20,
  alignItems: 'start',
}

const badgeSt: CSSProperties = {
  position: 'absolute',
  top: -12,
  left: '50%',
  transform: 'translateX(-50%)',
  background: 'var(--color-am-blue)',
  color: '#fff',
  fontSize: 11,
  fontWeight: 700,
  padding: '3px 14px',
  borderRadius: 20,
  whiteSpace: 'nowrap',
  letterSpacing: '0.02em',
}

const tagSt: CSSProperties = {
  fontSize: 10,
  fontWeight: 600,
  padding: '3px 9px',
  borderRadius: 20,
  background: 'rgba(58,122,184,0.07)',
  color: 'var(--color-am-blue)',
  border: '1px solid rgba(58,122,184,0.15)',
  whiteSpace: 'nowrap',
}

const erroSt: CSSProperties = {
  marginTop: 20,
  padding: '12px 16px',
  background: 'rgba(200,48,48,0.06)',
  border: '1px solid rgba(200,48,48,0.20)',
  borderRadius: 12,
  fontSize: 13,
  color: '#B02020',
  textAlign: 'center',
}
