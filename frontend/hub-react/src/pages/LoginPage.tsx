import { useState, type CSSProperties } from 'react'
import { Sparkles, Loader2 } from 'lucide-react'
import { useWaveCanvas } from '../hooks/useWaveCanvas'
import { login } from '../api/auth'

const WAVES = [
  { A: 55, f: 0.0032, s: 0.012, p: 0.0 },
  { A: 35, f: 0.0058, s: 0.019, p: 1.4 },
  { A: 22, f: 0.0094, s: 0.027, p: 2.9 },
  { A: 14, f: 0.0150, s: 0.021, p: 0.8 },
]

interface Props {
  onLogin: () => void
  onRegister: () => void
  onAjuda: () => void
}

export default function LoginPage({ onLogin, onRegister, onAjuda }: Props) {
  const canvasRef = useWaveCanvas(WAVES)
  const [email, setEmail]       = useState('')
  const [pass, setPass]         = useState('')
  const [showPass, setShowPass] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError]         = useState<string | null>(null)

  async function handleLogin() {
    if (!email || !pass) { setError('Preencha e-mail e senha.'); return }
    setError(null)
    setIsLoading(true)
    try {
      await login(email, pass)
      onLogin()
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status
      if (status === 401) setError('E-mail ou senha incorretos.')
      else if (status === 429) setError('Conta bloqueada temporariamente. Tente em 15 minutos.')
      else setError('Erro ao conectar. Verifique sua conexão e tente novamente.')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', fontFamily: 'var(--font-sans)' }}>
      <canvas ref={canvasRef} style={{ position: 'fixed', inset: 0, width: '100vw', height: '100vh', display: 'block', zIndex: 0 }} />

      {/* Navbar */}
      <nav style={{ position: 'relative', zIndex: 10, padding: '16px 36px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <AmicusLogo />
        <button
          onClick={onAjuda}
          style={{ background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--color-am-muted)' }}
        >
          Precisa de ajuda?{' '}
          <span style={{ color: 'var(--color-am-blue)', fontWeight: 700 }}>Fale conosco →</span>
        </button>
      </nav>

      {/* Main */}
      <main style={{ position: 'relative', zIndex: 10, flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '0 24px' }}>
        <div style={{ width: '100%', maxWidth: 400 }}>

          {/* Hero */}
          <div style={{ textAlign: 'center', marginBottom: 24 }}>
            <ArchLogo />
            <h1 style={{ fontSize: 20, fontWeight: 800, color: 'var(--color-am-ink)', letterSpacing: '-0.02em', marginBottom: 6 }}>
              Otimizando o tempo do seu escritório.
            </h1>
            <p style={{ fontSize: 13, color: 'var(--color-am-muted)' }}>Em qualquer lugar. A qualquer hora.</p>
          </div>

          {/* Card */}
          <div style={{ background: '#fff', borderRadius: 20, padding: '28px 26px', boxShadow: '0 1px 3px rgba(12,30,48,.06), 0 1px 2px rgba(12,30,48,.04)', border: '1px solid var(--color-am-border)' }}>

            {/* E-mail */}
            <div style={{ marginBottom: 14 }}>
              <label style={labelSt}>E-mail profissional</label>
              <div style={{ position: 'relative' }}>
                <FieldIcon focused={false}>
                  <rect x="2" y="4" width="20" height="16" rx="2"/>
                  <path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/>
                </FieldIcon>
                <input
                  type="email"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  onFocus={e => { e.target.style.borderColor = 'var(--color-am-blue)'; e.target.style.boxShadow = '0 0 0 3px rgba(58,122,184,0.12)' }}
                  onBlur={e =>  { e.target.style.borderColor = 'var(--color-am-border)'; e.target.style.boxShadow = 'none' }}
                  placeholder="advogado@escritorio.com.br"
                  autoComplete="email"
                  style={iconInput}
                />
              </div>
            </div>

            {/* Senha */}
            <div style={{ marginBottom: 16 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                <label style={{ ...labelSt, display: 'inline' }}>Senha</label>
                <a href="#" style={{ fontSize: 11, color: 'var(--color-am-blue)', textDecoration: 'none', fontWeight: 600 }}>Esqueceu?</a>
              </div>
              <div style={{ position: 'relative' }}>
                <FieldIcon focused={false}>
                  <rect x="3" y="11" width="18" height="11" rx="2"/>
                  <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
                </FieldIcon>
                <input
                  type={showPass ? 'text' : 'password'}
                  value={pass}
                  onChange={e => setPass(e.target.value)}
                  onFocus={e => { e.target.style.borderColor = 'var(--color-am-blue)'; e.target.style.boxShadow = '0 0 0 3px rgba(58,122,184,0.12)' }}
                  onBlur={e =>  { e.target.style.borderColor = 'var(--color-am-border)'; e.target.style.boxShadow = 'none' }}
                  placeholder="••••••••"
                  autoComplete="current-password"
                  style={{ ...iconInput, paddingRight: 40 }}
                />
                <button
                  type="button"
                  onClick={() => setShowPass(v => !v)}
                  aria-label="Mostrar senha"
                  style={{ position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', padding: 0, display: 'flex' }}
                >
                  <EyeIcon visible={showPass} />
                </button>
              </div>
            </div>

            {/* Erro de autenticação */}
            {error && (
              <p style={{ fontSize: 12, color: '#D63B3B', background: '#FEF2F2', border: '1px solid #FECACA', borderRadius: 10, padding: '8px 12px', marginBottom: 10 }}>
                {error}
              </p>
            )}

            {/* Botões */}
            <button
              onClick={handleLogin}
              disabled={isLoading}
              className="spkbtn"
              style={{ width: '100%', marginBottom: 10, opacity: isLoading ? 0.7 : 1, cursor: isLoading ? 'not-allowed' : 'pointer' }}
            >
              {isLoading
                ? <Loader2 size={16} className="spkbtn-sparkle" style={{ animation: 'spin 1s linear infinite' }} />
                : <Sparkles size={16} className="spkbtn-sparkle" />}
              <span className="spkbtn-text">{isLoading ? 'Entrando…' : 'Entrar na plataforma'}</span>
            </button>

            <button
              onClick={onRegister}
              className="press"
              style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: '100%', padding: '10px 0', background: 'rgba(12,30,48,0.03)', color: 'var(--color-am-secondary)', fontFamily: 'var(--font-sans)', fontSize: 13, border: '1px solid var(--color-am-border)', borderRadius: 12, cursor: 'pointer', transition: 'background 0.14s, border-color 0.14s, box-shadow 0.14s' }}
              onMouseEnter={e => {
                e.currentTarget.style.background = 'rgba(18,72,190,0.05)'
                e.currentTarget.style.borderColor = 'var(--color-am-blue)'
                e.currentTarget.style.boxShadow = '0 0 0 3px rgba(18,72,190,0.08)'
              }}
              onMouseLeave={e => {
                e.currentTarget.style.background = 'rgba(12,30,48,0.03)'
                e.currentTarget.style.borderColor = 'var(--color-am-border)'
                e.currentTarget.style.boxShadow = 'none'
              }}
            >
              Novo escritório? &nbsp;<span style={{ color: 'var(--color-am-blue)', fontWeight: 700 }}>Criar conta gratuita →</span>
            </button>
          </div>

          {/* Badges */}
          <div style={{ display: 'flex', justifyContent: 'center', gap: 20, marginTop: 16 }}>
            {['OAB 205/2021', 'LGPD', 'AES-256'].map(b => (
              <div key={b} style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: 'var(--color-am-muted)' }}>
                <span style={{ width: 5, height: 5, borderRadius: '50%', background: 'var(--color-am-green)', display: 'inline-block' }} />
                {b}
              </div>
            ))}
          </div>
        </div>
      </main>
    </div>
  )
}

/* ── Components ───────────────────────────────────────────────────────────── */

function AmicusLogo() {
  return (
    <span
      style={{
        fontSize: 22, fontWeight: 900, letterSpacing: '-0.04em',
        background: 'linear-gradient(135deg, #0C1E30 0%, #1248BE 100%)',
        WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text',
        fontFamily: 'var(--font-sans)',
      }}
    >
      amicus
    </span>
  )
}

function ArchLogo() {
  return (
    <img
      src="/logo.png"
      alt="amicus"
      style={{ display: 'block', margin: '0 auto 16px', width: 56, height: 56, objectFit: 'contain' }}
    />
  )
}

function FieldIcon({ children }: { focused: boolean; children: React.ReactNode }) {
  return (
    <svg style={{ position: 'absolute', left: 11, top: '50%', transform: 'translateY(-50%)', width: 14, height: 14, pointerEvents: 'none' }}
      viewBox="0 0 24 24" fill="none" stroke="var(--color-am-muted)" strokeWidth="1.8" strokeLinecap="round">
      {children}
    </svg>
  )
}

function EyeIcon({ visible }: { visible: boolean }) {
  return visible ? (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--color-am-muted)" strokeWidth="1.8" strokeLinecap="round">
      <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/>
    </svg>
  ) : (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--color-am-muted)" strokeWidth="1.8" strokeLinecap="round">
      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/>
      <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/>
      <line x1="1" y1="1" x2="23" y2="23"/>
    </svg>
  )
}

/* ── Styles ───────────────────────────────────────────────────────────────── */

const labelSt: CSSProperties = {
  display: 'block', fontSize: 10, fontWeight: 700,
  color: 'var(--color-am-secondary)', textTransform: 'uppercase',
  letterSpacing: '0.08em', marginBottom: 6,
}

const iconInput: CSSProperties = {
  width: '100%', boxSizing: 'border-box', padding: '10px 12px 10px 34px',
  fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--color-am-ink)',
  background: 'var(--color-am-bg)', border: '1px solid var(--color-am-border)',
  borderRadius: 12, outline: 'none',
  transition: 'border-color 0.14s ease, box-shadow 0.14s ease',
}
