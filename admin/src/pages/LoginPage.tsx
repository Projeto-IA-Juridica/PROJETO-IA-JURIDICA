import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { Spinner, ErrorBox } from '../components/ui'
import { Scale } from 'lucide-react'

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
    <div style={{
      minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'var(--surface-base)',
    }}>
      <div style={{ width: '100%', maxWidth: 380, padding: 20 }}>
        {/* Logo */}
        <div style={{ textAlign: 'center', marginBottom: 28 }}>
          <div style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 48, height: 48, borderRadius: 12, background: 'var(--accent-glow)', marginBottom: 12 }}>
            <Scale size={24} style={{ color: 'var(--accent)' }} />
          </div>
          <div style={{ fontSize: 18, fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '-0.02em' }}>Hub Jurídico</div>
          <div style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 2 }}>Painel de Administração</div>
        </div>

        {/* Tabs */}
        <div style={{ display: 'flex', borderBottom: '1px solid var(--surface-border)', marginBottom: 20 }}>
          <button className={`tab ${tab === 'login' ? 'active' : ''}`} onClick={() => { setTab('login'); setError('') }}>Entrar</button>
          <button className={`tab ${tab === 'register' ? 'active' : ''}`} onClick={() => { setTab('register'); setError('') }}>Criar conta</button>
        </div>

        {error && <div style={{ marginBottom: 14 }}><ErrorBox message={error} /></div>}

        {tab === 'login' ? (
          <form onSubmit={handleLogin} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div>
              <label className="label">E-mail</label>
              <input className="input" type="email" required autoFocus value={email} onChange={e => setEmail(e.target.value)} placeholder="admin@escritorio.com" />
            </div>
            <div>
              <label className="label">Senha</label>
              <input className="input" type="password" required value={senha} onChange={e => setSenha(e.target.value)} placeholder="••••••••" />
            </div>
            <button className="btn btn-primary btn-lg" type="submit" disabled={loading} style={{ marginTop: 2, justifyContent: 'center' }}>
              {loading ? <Spinner size={14} /> : null} Entrar
            </button>
          </form>
        ) : (
          <form onSubmit={handleRegister} style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
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
            <button className="btn btn-primary btn-lg" type="submit" disabled={loading} style={{ marginTop: 2, justifyContent: 'center' }}>
              {loading ? <Spinner size={14} /> : null} Criar conta
            </button>
          </form>
        )}
      </div>
    </div>
  )
}
