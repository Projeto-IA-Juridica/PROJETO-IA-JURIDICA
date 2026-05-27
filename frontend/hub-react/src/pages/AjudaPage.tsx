import { useState } from 'react'

const WHATSAPP = import.meta.env.VITE_SUPORTE_WHATSAPP || '5500000000000'

interface Props { onBack: () => void }

interface FormState {
  nome: string; email: string; tel: string; empresa: string; msg: string
}

export default function AjudaPage({ onBack }: Props) {
  const [form, setForm]           = useState<FormState>({ nome: '', email: '', tel: '', empresa: '', msg: '' })
  const [submitted, setSubmitted] = useState(false)
  const [error, setError]         = useState(false)

  function maskTel(v: string) {
    const d = v.replace(/\D/g, '').slice(0, 11)
    if (d.length <= 10) return d.replace(/^(\d{2})(\d{4})(\d{0,4})/, '($1) $2-$3')
    return d.replace(/^(\d{2})(\d{5})(\d{0,4})/, '($1) $2-$3')
  }

  function handleSubmit(e: { preventDefault(): void }) {
    e.preventDefault()
    const { nome, email, tel, empresa, msg } = form
    if (!nome || !email || !tel || !empresa || !msg) { setError(true); return }
    setError(false)
    const texto = [
      'Olá! Recebi um contato pelo site amicus:', '',
      '👤 Nome: '        + nome,
      '📧 E-mail: '      + email,
      '📱 Telefone: '    + tel,
      '🏛️ Escritório: ' + empresa, '',
      '💬 Mensagem:', msg,
    ].join('\n')
    window.open(`https://wa.me/${WHATSAPP}?text=${encodeURIComponent(texto)}`, '_blank')
    setSubmitted(true)
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', fontFamily: 'var(--font-sans)' }}>

      {/* Navbar */}
      <nav style={{ padding: '16px 40px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--color-am-border)', background: '#fff', position: 'relative', zIndex: 10 }}>
        <button onClick={onBack} style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer' }}>
          <AmicusLogo />
        </button>
        <button onClick={onBack} style={{ fontSize: 13, color: 'var(--color-am-muted)', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'var(--font-sans)', fontWeight: 600, transition: 'color 0.14s' }}
          onMouseEnter={e => (e.currentTarget.style.color = 'var(--color-am-ink)')}
          onMouseLeave={e => (e.currentTarget.style.color = 'var(--color-am-muted)')}>
          ← Voltar ao login
        </button>
      </nav>

      {/* Split grid */}
      <div style={{ flex: 1, display: 'grid', gridTemplateColumns: '1fr 1.2fr', minHeight: 'calc(100vh - 57px)' }}>

        {/* Painel esquerdo */}
        <aside style={{ background: 'var(--color-am-ink)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '56px 44px' }}>
          <div style={{ maxWidth: 340 }}>
            <svg style={{ display: 'block', marginBottom: 28, opacity: 0.85 }} width="48" height="52" viewBox="0 0 68 72" fill="none">
              <rect x="10" y="0" width="48" height="6" rx="1" fill="white"/>
              <path d="M4 9 L64 9 L60 18 L8 18 Z" fill="white"/>
              <rect x="0" y="21" width="68" height="26" fill="white"/>
              <path d="M24 47 L24 36 Q24 27 34 27 Q44 27 44 36 L44 47 Z" fill="transparent"/>
              <rect x="7"  y="27" width="12" height="12" fill="transparent"/>
              <rect x="10" y="30" width="6"  height="6"  fill="white"/>
              <rect x="49" y="27" width="12" height="12" fill="transparent"/>
              <rect x="52" y="30" width="6"  height="6"  fill="white"/>
              <rect x="0"  y="47" width="24" height="25" fill="white"/>
              <rect x="44" y="47" width="24" height="25" fill="white"/>
            </svg>

            <h1 style={{ fontSize: 32, fontWeight: 800, color: '#fff', lineHeight: 1.15, letterSpacing: '-0.03em', marginBottom: 14 }}>
              Fale com<br />a gente.
            </h1>
            <p style={{ fontSize: 14, color: 'rgba(255,255,255,0.55)', lineHeight: 1.7, marginBottom: 28 }}>
              Nossa equipe está pronta para entender o seu escritório e mostrar como o amicus pode transformar seu atendimento.
            </p>
            <div style={{ width: 32, height: 1, background: 'rgba(255,255,255,0.18)', marginBottom: 22 }} />
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {['Resposta em até 24h', 'Demonstração gratuita', 'Sem compromisso'].map(item => (
                <div key={item} style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 13, color: 'rgba(255,255,255,0.70)' }}>
                  <span style={{ width: 16, height: 1.5, background: 'var(--color-am-blue)', flexShrink: 0, display: 'inline-block' }} />
                  {item}
                </div>
              ))}
            </div>
          </div>
        </aside>

        {/* Painel direito */}
        <section style={{ background: 'var(--color-am-surface)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '48px 52px' }}>
          <div style={{ width: '100%', maxWidth: 460 }}>
            {submitted ? <SuccessState /> : (
              <form onSubmit={handleSubmit} noValidate>

                <FGroup label="Nome completo" required>
                  <input type="text" value={form.nome} onChange={e => setForm(f => ({ ...f, nome: e.target.value }))} placeholder="Seu nome completo" className="am-input" />
                </FGroup>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                  <FGroup label="E-mail" required>
                    <input type="email" value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} placeholder="seu@escritorio.com.br" className="am-input" />
                  </FGroup>
                  <FGroup label="Telefone" required>
                    <input type="tel" value={form.tel} onChange={e => setForm(f => ({ ...f, tel: maskTel(e.target.value) }))} placeholder="(00) 00000-0000" className="am-input" />
                  </FGroup>
                </div>

                <FGroup label="Escritório / Empresa" required>
                  <input type="text" value={form.empresa} onChange={e => setForm(f => ({ ...f, empresa: e.target.value }))} placeholder="Nome do seu escritório" className="am-input" />
                </FGroup>

                <FGroup label="Mensagem" required>
                  <textarea value={form.msg} onChange={e => setForm(f => ({ ...f, msg: e.target.value }))} rows={5} placeholder="Como podemos ajudar você?" className="am-textarea" style={{ minHeight: 110 }} />
                </FGroup>

                {error && (
                  <p style={{ fontSize: 12, color: 'var(--color-am-red)', marginBottom: 12 }}>
                    Por favor preencha todos os campos obrigatórios.
                  </p>
                )}

                <button type="submit" className="btn-primary press"
                  style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: '100%', padding: '12px 0', marginBottom: 12, background: 'linear-gradient(135deg, #1248BE 0%, #3A7AB8 100%)', color: '#fff', fontFamily: 'var(--font-sans)', fontWeight: 700, fontSize: 13, border: 'none', borderRadius: 12, cursor: 'pointer', boxShadow: '0 4px 16px rgba(18,72,190,0.22), inset 0 1px 0 rgba(255,255,255,0.15)' }}>
                  Enviar pelo WhatsApp
                </button>

                <p style={{ fontSize: 11, color: 'var(--color-am-muted)', textAlign: 'center', lineHeight: 1.5 }}>
                  Seus dados são usados apenas para entrar em contato.{' '}
                  <a href="/privacidade" style={{ color: 'var(--color-am-blue)', textDecoration: 'none', fontWeight: 600 }}>Política de privacidade.</a>
                </p>
              </form>
            )}
          </div>
        </section>
      </div>
    </div>
  )
}

/* ── Sub-components ───────────────────────────────────────────────────────── */

function SuccessState() {
  return (
    <div style={{ textAlign: 'center', padding: '40px 0' }}>
      <div style={{ width: 60, height: 60, borderRadius: '50%', background: 'rgba(26,158,120,0.10)', border: '1.5px solid rgba(26,158,120,0.25)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 18px' }}>
        <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#2E9E6B" strokeWidth="2" strokeLinecap="round">
          <polyline points="20 6 9 12 4 9"/>
        </svg>
      </div>
      <h2 style={{ fontSize: 20, fontWeight: 800, color: 'var(--color-am-ink)', marginBottom: 8 }}>
        Mensagem enviada!
      </h2>
      <p style={{ fontSize: 13, color: 'var(--color-am-muted)', lineHeight: 1.6 }}>
        Recebemos seu contato e retornaremos em até 24h.
      </p>
    </div>
  )
}

function FGroup({ label, required, children }: { label: string; required?: boolean; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <label className="am-label">
        {label}{required && <span style={{ color: 'var(--color-am-blue)', marginLeft: 2 }}>*</span>}
      </label>
      {children}
    </div>
  )
}

function AmicusLogo() {
  return (
    <span style={{ fontSize: 22, fontWeight: 900, letterSpacing: '-0.04em', background: 'linear-gradient(135deg, #0C1E30 0%, #1248BE 100%)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text', fontFamily: 'var(--font-sans)' }}>
      amicus
    </span>
  )
}

