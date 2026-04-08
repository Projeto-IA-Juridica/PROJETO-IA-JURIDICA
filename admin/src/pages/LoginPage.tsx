import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { Spinner, ErrorBox } from '../components/ui'
import { Scale, ShieldCheck, ArrowRight } from 'lucide-react'

type Tab = 'login' | 'register'

type ApiValidationError = {
  msg?: string
  loc?: Array<string | number>
}

type ApiErrorShape = {
  response?: {
    data?: {
      detail?: string | ApiValidationError[] | ApiValidationError
    }
    status?: number
  }
  message?: string
}

function toErrorMessage(err: unknown, fallback: string): string {
  const axiosErr = err as ApiErrorShape
  const detail = axiosErr?.response?.data?.detail

  if (Array.isArray(detail)) {
    return detail
      .map((d) => {
        const field = d?.loc?.length ? String(d.loc[d.loc.length - 1]) : ''
        const msg = d?.msg ?? 'Erro de validação'
        return field ? `${field}: ${msg}` : msg
      })
      .join('; ')
  }

  if (detail && typeof detail === 'object') {
    const msg = detail.msg ?? 'Erro de validação'
    const field = detail.loc?.length ? String(detail.loc[detail.loc.length - 1]) : ''
    return field ? `${field}: ${msg}` : msg
  }

  if (typeof detail === 'string' && detail.trim()) return detail

  if (axiosErr?.response?.status) return `Erro ${axiosErr.response.status}: Falha na comunicação`

  return axiosErr?.message ?? fallback
}

export default function LoginPage() {
  const { login, register } = useAuth()
  const navigate = useNavigate()
  const [tab, setTab] = useState<Tab>('login')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const [email, setEmail] = useState('')
  const [senha, setSenha] = useState('')

  const [reg, setReg] = useState({
    nome_escritorio: '', cnpj: '', email_admin: '', senha: '',
    nome_responsavel: '', oab_responsavel: '',
  })

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await login(email.trim(), senha)
      navigate('/hub')
    } catch (err: unknown) {
      setError(toErrorMessage(err, 'E-mail ou senha incorretos'))
    } finally { setLoading(false) }
  }

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await register({ ...reg, email_admin: reg.email_admin.trim() })
      navigate('/settings')
    } catch (err: unknown) {
      setError(toErrorMessage(err, 'Falha no cadastro'))
    } finally { setLoading(false) }
  }

  return (
    <div className="login-viewport">
      <div className="login-shell">
        <section className="login-panel login-panel-copy surface">
          <div className="login-brand">
            <div className="login-logo" aria-hidden>
              <Scale size={22} />
            </div>
            <div>
              <div className="login-title">Hub Jurídico</div>
              <div className="login-subtitle">Painel administrativo</div>
            </div>
          </div>

          <div className="login-copy-block">
            <div className="login-eyebrow">Operação interna</div>
            <h1 className="login-heading">Uma interface discreta, séria e orientada à operação.</h1>
            <p className="login-copy">
              Gestão do escritório, processos, CRM e prospecção com visual limpo, leitura rápida e foco no que importa.
            </p>
          </div>

          <div className="login-points">
            <div className="login-point"><ShieldCheck size={14} /> Acesso restrito por perfil</div>
            <div className="login-point"><ShieldCheck size={14} /> Fluxo enxuto para operação diária</div>
            <div className="login-point"><ShieldCheck size={14} /> Navegação simples e consistente</div>
          </div>
        </section>

        <section className="login-panel login-card surface">
          <div className="tab-row" role="tablist" aria-label="Autenticação">
            <button type="button" className={`tab ${tab === 'login' ? 'active' : ''}`} onClick={() => { setTab('login'); setError('') }}>Entrar</button>
            <button type="button" className={`tab ${tab === 'register' ? 'active' : ''}`} onClick={() => { setTab('register'); setError('') }}>Criar conta</button>
          </div>

          {error && <div style={{ marginTop: 14 }}><ErrorBox message={error} /></div>}

          {tab === 'login' ? (
            <form onSubmit={handleLogin} className="login-form">
              <label className="label">E-mail</label>
              <input className="input" type="email" required autoFocus value={email} onChange={e => setEmail(e.target.value)} placeholder="admin@escritorio.com" />

              <label className="label" style={{ marginTop: 8 }}>Senha</label>
              <input className="input" type="password" required value={senha} onChange={e => setSenha(e.target.value)} placeholder="••••••••" />

              <button className="btn btn-primary btn-lg" type="submit" disabled={loading} style={{ marginTop: 10 }}>
                {loading ? <Spinner size={14} /> : <ArrowRight size={14} />} Entrar
              </button>
            </form>
          ) : (
            <form onSubmit={handleRegister} className="login-form register-form">
              <div className="register-grid">
                <div>
                  <label className="label">Escritório</label>
                  <input className="input" required value={reg.nome_escritorio} onChange={e => setReg(r => ({ ...r, nome_escritorio: e.target.value }))} placeholder="Souza Advogados" />
                </div>
                <div>
                  <label className="label">CNPJ</label>
                  <input className="input" required value={reg.cnpj} onChange={e => setReg(r => ({ ...r, cnpj: e.target.value }))} placeholder="11.222.333/0001-81" />
                </div>
                <div>
                  <label className="label">Responsável</label>
                  <input className="input" required value={reg.nome_responsavel} onChange={e => setReg(r => ({ ...r, nome_responsavel: e.target.value }))} placeholder="Dr. João Silva" />
                </div>
                <div>
                  <label className="label">OAB</label>
                  <input className="input" required value={reg.oab_responsavel} onChange={e => setReg(r => ({ ...r, oab_responsavel: e.target.value }))} placeholder="SP123456" />
                </div>
                <div style={{ gridColumn: '1/-1' }}>
                  <label className="label">E-mail</label>
                  <input className="input" type="email" required value={reg.email_admin} onChange={e => setReg(r => ({ ...r, email_admin: e.target.value }))} placeholder="admin@escritorio.com" />
                </div>
                <div style={{ gridColumn: '1/-1' }}>
                  <label className="label">Senha (mín. 8)</label>
                  <input className="input" type="password" required minLength={8} value={reg.senha} onChange={e => setReg(r => ({ ...r, senha: e.target.value }))} placeholder="••••••••" />
                </div>
              </div>
              <button className="btn btn-primary btn-lg" type="submit" disabled={loading} style={{ marginTop: 10 }}>
                {loading ? <Spinner size={14} /> : <ArrowRight size={14} />} Criar conta
              </button>
            </form>
          )}
        </section>
      </div>
    </div>
  )
}
