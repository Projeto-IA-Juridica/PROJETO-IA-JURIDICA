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
      <main style={{ position: 'relative', zIndex: 10, flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '0 24px', gap: 48 }}>
        <AppPreview />
        <div style={{ width: '100%', maxWidth: 400, flexShrink: 0 }}>

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
                  onKeyDown={e => { if (e.key === 'Enter') handleLogin() }}
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

/* ── App Preview (mock dashboard) ────────────────────────────────────────── */

const MOCK_CLIENTES = [
  { nome: 'João Pedro Andrade',   processo: '0011223-44.2023.8.26.0001', nivel: 'baixo',    score: 28, status: 'Audiência marcada' },
  { nome: 'Maria Stella Fontes',  processo: '0022334-55.2022.5.02.0000', nivel: 'moderado', score: 54, status: 'Aguardando perícia' },
  { nome: 'Carlos Eduardo Mendes',processo: '0033445-66.2021.8.26.0100', nivel: 'alto',     score: 71, status: 'Recurso em análise'  },
  { nome: 'Luciana Martins Vaz',  processo: '0044556-77.2020.4.03.6100', nivel: 'baixo',    score: 19, status: 'Sentença transitada' },
]

const RISK_COLOR: Record<string, string> = {
  baixo: '#1A9E78', moderado: '#D08010', alto: '#C83030',
}
const RISK_LABEL: Record<string, string> = {
  baixo: 'Baixo', moderado: 'Moderado', alto: 'Alto',
}

const MOCK_MSGS = [
  { dir: 'in',  text: 'Bom dia! Tem novidade no meu processo?', time: '09:14' },
  { dir: 'out', text: 'Bom dia, João! Sua audiência foi marcada para 12/06 às 14h na 3ª Vara Cível.', time: '09:14' },
  { dir: 'in',  text: 'Preciso levar algum documento?', time: '09:15' },
  { dir: 'out', text: 'Apenas documento de identidade. Qualquer dúvida estou aqui!', time: '09:15' },
]

function AppPreview() {
  return (
    <div className="app-preview-panel" style={{ flex: '1 1 0', maxWidth: 560, minWidth: 0, pointerEvents: 'none', userSelect: 'none' }}>
      <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--color-am-blue)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 10 }}>
        Prévia do painel
      </div>

      {/* Métricas topo */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 8, marginBottom: 10 }}>
        {[
          { label: 'Clientes ativos', value: '47' },
          { label: 'Processos',       value: '63' },
          { label: 'Msgs hoje',       value: '128' },
        ].map(m => (
          <div key={m.label} style={{ background: '#fff', borderRadius: 12, padding: '10px 12px', border: '1px solid var(--color-am-border)', boxShadow: '0 1px 3px rgba(12,30,48,.05)' }}>
            <div style={{ fontSize: 18, fontWeight: 800, color: 'var(--color-am-ink)', lineHeight: 1 }}>{m.value}</div>
            <div style={{ fontSize: 10, color: 'var(--color-am-muted)', marginTop: 3 }}>{m.label}</div>
          </div>
        ))}
      </div>

      {/* Tabela clientes */}
      <div style={{ background: '#fff', borderRadius: 14, border: '1px solid var(--color-am-border)', boxShadow: '0 1px 3px rgba(12,30,48,.05)', marginBottom: 10, overflow: 'hidden' }}>
        <div style={{ padding: '10px 14px', borderBottom: '1px solid var(--color-am-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--color-am-ink)' }}>CRM — Clientes</span>
          <span style={{ fontSize: 10, color: 'var(--color-am-muted)' }}>Score de risco</span>
        </div>
        {MOCK_CLIENTES.map((c, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 14px', borderBottom: i < MOCK_CLIENTES.length - 1 ? '1px solid var(--color-am-border)' : 'none', background: i % 2 === 0 ? '#fff' : 'rgba(244,248,252,0.6)' }}>
            <div style={{ width: 28, height: 28, borderRadius: '50%', background: `${RISK_COLOR[c.nivel]}18`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
              <span style={{ fontSize: 10, fontWeight: 800, color: RISK_COLOR[c.nivel] }}>{c.nome.split(' ').map(w => w[0]).slice(0,2).join('')}</span>
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--color-am-ink)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{c.nome}</div>
              <div style={{ fontSize: 10, color: 'var(--color-am-muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{c.status}</div>
            </div>
            <div style={{ textAlign: 'right', flexShrink: 0 }}>
              <div style={{ fontSize: 11, fontWeight: 800, color: RISK_COLOR[c.nivel] }}>{c.score}</div>
              <div style={{ fontSize: 9, fontWeight: 600, color: RISK_COLOR[c.nivel], background: `${RISK_COLOR[c.nivel]}12`, borderRadius: 4, padding: '1px 5px' }}>{RISK_LABEL[c.nivel]}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Chat preview */}
      <div style={{ background: '#fff', borderRadius: 14, border: '1px solid var(--color-am-border)', boxShadow: '0 1px 3px rgba(12,30,48,.05)', overflow: 'hidden' }}>
        <div style={{ padding: '10px 14px', borderBottom: '1px solid var(--color-am-border)', display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ width: 24, height: 24, borderRadius: '50%', background: 'rgba(26,158,120,0.12)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <span style={{ fontSize: 9, fontWeight: 800, color: '#1A9E78' }}>JP</span>
          </div>
          <div>
            <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--color-am-ink)' }}>João Pedro Andrade</div>
            <div style={{ fontSize: 9, color: '#1A9E78', fontWeight: 600 }}>● online</div>
          </div>
          <div style={{ marginLeft: 'auto', fontSize: 9, color: 'var(--color-am-muted)' }}>Sofia (IA)</div>
        </div>
        <div style={{ padding: '10px 14px', display: 'flex', flexDirection: 'column', gap: 6 }}>
          {MOCK_MSGS.map((m, i) => (
            <div key={i} style={{ display: 'flex', justifyContent: m.dir === 'in' ? 'flex-start' : 'flex-end' }}>
              <div style={{
                maxWidth: '78%', padding: '6px 10px', borderRadius: m.dir === 'in' ? '4px 10px 10px 10px' : '10px 4px 10px 10px',
                background: m.dir === 'in' ? 'var(--color-am-bg)' : 'linear-gradient(135deg,#1248BE,#3A7AB8)',
                color: m.dir === 'in' ? 'var(--color-am-ink)' : '#fff',
                fontSize: 10, lineHeight: 1.4,
                boxShadow: '0 1px 2px rgba(12,30,48,.08)',
              }}>
                {m.text}
                <div style={{ fontSize: 8, opacity: 0.6, textAlign: 'right', marginTop: 2 }}>{m.time}</div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
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
