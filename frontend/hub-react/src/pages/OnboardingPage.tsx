import { useState, useEffect, type CSSProperties, type Dispatch, type SetStateAction } from 'react'
import { useWaveCanvas } from '../hooks/useWaveCanvas'

/* ── Types ───────────────────────────────────────────────────────────────── */

interface S1 { email: string; pass: string; confirm: string }
interface S2 { nome: string; cnpj: string; oab: string; responsavel: string; advogados: string; areas: string[] }
interface S3 { inicio: string; fim: string; dias: string[] }
interface S4 { assistente: string; tom: string }

interface Props { onComplete: () => void }

/* ── Constants ───────────────────────────────────────────────────────────── */

const AREAS  = ['Civil','Trabalhista','Família','Previdenciário','Criminal','Tributário','Empresarial','Digital','Consumidor','Imobiliário']
const TONS   = ['Formal e técnico','Formal e acessível','Próximo e cordial','Neutro e objetivo']
const DAYS   = ['Seg','Ter','Qua','Qui','Sex','Sáb','Dom']
const LABELS = ['Acesso','Escritório','WhatsApp','Persona','OAB','Ativação']
const TITLES = [
  { h: 'Crie seu acesso',           p: 'Defina o e-mail e a senha para acessar a plataforma amicus.' },
  { h: 'Configure seu escritório',  p: 'Em poucos minutos sua IA estará pronta para atender clientes no WhatsApp 24h.' },
  { h: 'Conecte seu WhatsApp',      p: 'Leia o QR Code no WhatsApp do escritório para ativar o canal de atendimento.' },
  { h: 'Configure a persona da IA', p: 'Defina como sua assistente virtual vai se apresentar para os clientes.' },
  { h: 'Conformidade OAB',          p: 'Aceite os termos exigidos pelo Provimento 205/2021 para uso ético da IA.' },
  { h: 'Ativar o escritório',       p: 'Revise os dados e ative sua conta para começar a atender.' },
]

/* ── Password strength ───────────────────────────────────────────────────── */

function getStrength(pass: string) {
  if (!pass) return { score: 0, label: '', color: 'transparent' }
  let score = 0
  if (pass.length >= 8)           score++
  if (/[A-Z]/.test(pass))        score++
  if (/[0-9]/.test(pass))        score++
  if (/[^A-Za-z0-9]/.test(pass)) score++
  const map = [
    { label: '',         color: 'transparent' },
    { label: 'Fraca',    color: '#C83030' },
    { label: 'Razoável', color: '#D08010' },
    { label: 'Boa',      color: 'var(--color-am-blue)' },
    { label: 'Forte',    color: 'var(--color-am-green)' },
  ]
  return { score, ...map[score] }
}

/* ── Wave config ─────────────────────────────────────────────────────────── */

const WAVES = [
  { A: 55, f: 0.0032, s: 0.012, p: 0.0 },
  { A: 35, f: 0.0058, s: 0.019, p: 1.4 },
  { A: 22, f: 0.0094, s: 0.027, p: 2.9 },
  { A: 14, f: 0.0150, s: 0.021, p: 0.8 },
]

/* ── Main component ──────────────────────────────────────────────────────── */

export default function OnboardingPage({ onComplete }: Props) {
  const canvasRef = useWaveCanvas(WAVES)

  const [step, setStep]     = useState(1)
  const [done, setDone]     = useState(false)
  const [errors, setErrors] = useState<Record<string, string>>({})

  const [s1, setS1] = useState<S1>({ email: '', pass: '', confirm: '' })
  const [s2, setS2] = useState<S2>({ nome: '', cnpj: '', oab: '', responsavel: '', advogados: '1', areas: [] })
  const [s3, setS3] = useState<S3>({ inicio: '08:00', fim: '18:00', dias: ['Seg','Ter','Qua','Qui','Sex'] })
  const [s4, setS4] = useState<S4>({ assistente: '', tom: '' })
  const [aceite, setAceite] = useState(false)

  /* Enter → next */
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Enter' && (document.activeElement as HTMLElement)?.tagName !== 'TEXTAREA') next()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  })

  function validate(): Record<string, string> {
    const e: Record<string, string> = {}
    if (step === 1) {
      if (!s1.email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(s1.email)) e.email = 'E-mail inválido.'
      if (!s1.pass || getStrength(s1.pass).score < 2) e.pass = 'Senha fraca. Use maiúsculas, números e símbolos.'
      if (!s1.confirm)                 e.confirm = 'Confirme sua senha.'
      else if (s1.confirm !== s1.pass) e.confirm = 'As senhas não coincidem.'
    }
    if (step === 2) {
      if (!s2.nome.trim())        e.nome        = 'Nome do escritório obrigatório.'
      if (!s2.oab.trim())         e.oab         = 'OAB obrigatória.'
      if (!s2.responsavel.trim()) e.responsavel = 'Nome do responsável obrigatório.'
    }
    if (step === 3 && !s3.dias.length)  e.dias      = 'Selecione ao menos um dia.'
    if (step === 4 && !s4.assistente.trim()) e.assistente = 'Dê um nome para sua assistente.'
    if (step === 5 && !aceite)          e.aceite    = 'Aceite os termos para continuar.'
    return e
  }

  function next() {
    const errs = validate()
    setErrors(errs)
    if (Object.keys(errs).length > 0) return
    if (step < 6) setStep(s => s + 1)
    else setDone(true)
  }

  function prev() { setErrors({}); if (step > 1) setStep(s => s - 1) }

  /* Done screen */
  if (done) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--color-am-bg)', fontFamily: 'var(--font-sans)' }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{ width: 68, height: 68, borderRadius: '50%', background: 'rgba(26,158,120,0.10)', border: '1.5px solid rgba(26,158,120,0.25)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 18px' }}>
            <CheckIcon size={28} color="#2E9E6B" />
          </div>
          <h2 style={{ fontSize: 22, fontWeight: 800, color: 'var(--color-am-ink)', letterSpacing: '-0.02em', marginBottom: 8 }}>Escritório ativado!</h2>
          <p style={{ fontSize: 13, color: 'var(--color-am-muted)', marginBottom: 28 }}>Redirecionando para o dashboard…</p>
          <button onClick={onComplete} className="btn-primary press" style={primaryBtn}>
            Acessar o dashboard →
          </button>
        </div>
      </div>
    )
  }

  const progress = ((step - 1) / 5) * 100

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', fontFamily: 'var(--font-sans)' }}>
      <canvas ref={canvasRef} style={{ position: 'fixed', inset: 0, zIndex: 0, width: '100vw', height: '100vh', display: 'block' }} />

      <div style={{ position: 'relative', zIndex: 1, display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>

        {/* Header */}
        <div style={{ background: 'rgba(244,248,252,0.80)', backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)', borderBottom: '1px solid var(--color-am-border)' }}>
          <div style={{ maxWidth: 740, margin: '0 auto', padding: '14px 24px 0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: 12, color: 'var(--color-am-muted)', fontWeight: 600 }}>
              Etapa <strong style={{ color: 'var(--color-am-blue)', fontWeight: 800 }}>{step}</strong> de 6
            </span>
            <AmicusLogo />
          </div>

          {/* Step indicator */}
          <div style={{ maxWidth: 740, margin: '0 auto', padding: '14px 24px 6px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            {LABELS.map((label, i) => {
              const n = i + 1
              const isDone   = n < step
              const isActive = n === step
              return (
                <div key={label} style={{ display: 'flex', alignItems: 'center' }}>
                  {i > 0 && <div style={{ width: 32, height: 2, background: isDone || isActive ? 'var(--color-am-blue)' : 'var(--color-am-border)', transition: 'background 0.4s' }} />}
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
                    <div style={{ width: 30, height: 30, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', background: isDone ? 'var(--color-am-blue)' : isActive ? '#fff' : 'rgba(168,200,232,0.20)', border: `2px solid ${isDone || isActive ? 'var(--color-am-blue)' : 'var(--color-am-border)'}`, fontSize: 10, fontWeight: 800, color: isDone ? '#fff' : isActive ? 'var(--color-am-blue)' : 'var(--color-am-muted)', transition: 'all 0.3s', boxShadow: isActive ? '0 0 0 4px rgba(58,122,184,0.14)' : 'none' }}>
                      {isDone ? <CheckIcon /> : n}
                    </div>
                    <span style={{ fontSize: 9, color: isDone || isActive ? 'var(--color-am-blue)' : 'var(--color-am-muted)', fontWeight: isDone || isActive ? 700 : 500, letterSpacing: '0.04em', textTransform: 'uppercase' }}>
                      {label}
                    </span>
                  </div>
                </div>
              )
            })}
          </div>

          {/* Progress bar */}
          <div style={{ maxWidth: 740, margin: '0 auto', padding: '0 24px 0' }}>
            <div style={{ height: 2, background: 'var(--color-am-border)', borderRadius: 2 }}>
              <div style={{ height: '100%', background: 'linear-gradient(90deg, var(--color-am-blue), var(--color-am-blue-light))', borderRadius: 2, width: `${progress}%`, transition: 'width 0.4s ease' }} />
            </div>
          </div>
        </div>

        {/* Content */}
        <div style={{ padding: '32px 24px', display: 'flex', justifyContent: 'center', flex: 1 }}>
          <div style={{ width: '100%', maxWidth: 640 }}>

            {/* Step header */}
            <div style={{ marginBottom: 20 }}>
              <h1 style={{ fontSize: 22, fontWeight: 800, color: 'var(--color-am-ink)', letterSpacing: '-0.02em', lineHeight: 1.2, marginBottom: 6 }}>
                {TITLES[step - 1].h}
              </h1>
              <p style={{ fontSize: 13, color: 'var(--color-am-muted)', lineHeight: 1.6 }}>
                {TITLES[step - 1].p}
              </p>
            </div>

            {/* Step card */}
            <div style={{ background: '#fff', borderRadius: 20, padding: '24px 28px', boxShadow: '0 1px 3px rgba(12,30,48,.06), 0 1px 2px rgba(12,30,48,.04)', border: '1px solid var(--color-am-border)', marginBottom: 20 }}>
              {step === 1 && <Step1 s1={s1} setS1={setS1} errors={errors} />}
              {step === 2 && <Step2 s2={s2} setS2={setS2} errors={errors} />}
              {step === 3 && <Step3 s3={s3} setS3={setS3} errors={errors} />}
              {step === 4 && <Step4 s4={s4} setS4={setS4} />}
              {step === 5 && <Step5 aceite={aceite} setAceite={setAceite} errors={errors} />}
              {step === 6 && <Step6 s1={s1} s2={s2} s3={s3} s4={s4} aceite={aceite} />}
            </div>

            {/* Nav */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              {step > 1
                ? <button onClick={prev} style={ghostBtn}>← Anterior</button>
                : <div />}
              <button onClick={next} className="btn-primary press" style={primaryBtn}>
                {step === 6 ? 'Ativar escritório →' : step === 5 ? 'Aceitar e continuar →' : 'Próximo →'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

/* ── Step 1 ───────────────────────────────────────────────────────────────── */

function Step1({ s1, setS1, errors }: { s1: S1; setS1: Dispatch<SetStateAction<S1>>; errors: Record<string, string> }) {
  const [showPass, setShowPass]       = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)
  const strength = getStrength(s1.pass)

  return (
    <>
      <FGroup label="E-mail profissional" required error={errors.email}>
        <input type="email" value={s1.email} onChange={e => setS1(v => ({ ...v, email: e.target.value }))} placeholder="voce@escritorio.com.br" style={inp} onFocus={focusFn} onBlur={blurFn} />
      </FGroup>

      <FGroup label="Senha" required error={errors.pass}>
        <div style={{ position: 'relative' }}>
          <input type={showPass ? 'text' : 'password'} value={s1.pass} onChange={e => setS1(v => ({ ...v, pass: e.target.value }))} placeholder="Mínimo 8 caracteres" style={{ ...inp, paddingRight: 40 }} onFocus={focusFn} onBlur={blurFn} />
          <EyeBtn visible={showPass} onToggle={() => setShowPass(v => !v)} />
        </div>
        <div style={{ display: 'flex', gap: 4, margin: '6px 0 2px' }}>
          {[1,2,3,4].map(n => (
            <div key={n} style={{ flex: 1, height: 3, borderRadius: 2, background: n <= strength.score ? strength.color : 'var(--color-am-border)', transition: 'background 0.3s' }} />
          ))}
        </div>
        {strength.label && <span style={{ fontSize: 10, fontWeight: 700, color: strength.color }}>{strength.label}</span>}
      </FGroup>

      <FGroup label="Confirmar senha" required error={errors.confirm}>
        <div style={{ position: 'relative' }}>
          <input type={showConfirm ? 'text' : 'password'} value={s1.confirm} onChange={e => setS1(v => ({ ...v, confirm: e.target.value }))} placeholder="Repita a senha" style={{ ...inp, paddingRight: 40 }} onFocus={focusFn} onBlur={blurFn} />
          <EyeBtn visible={showConfirm} onToggle={() => setShowConfirm(v => !v)} />
        </div>
        {s1.confirm && s1.confirm === s1.pass && !errors.confirm && (
          <p style={{ fontSize: 11, color: 'var(--color-am-green)', marginTop: 4, fontWeight: 600 }}>Senhas coincidem ✓</p>
        )}
      </FGroup>

      <InfoBox>Seus dados são protegidos por <strong>AES-256</strong> e nunca compartilhados com terceiros.</InfoBox>
    </>
  )
}

/* ── Step 2 ───────────────────────────────────────────────────────────────── */

function Step2({ s2, setS2, errors }: { s2: S2; setS2: Dispatch<SetStateAction<S2>>; errors: Record<string, string> }) {
  return (
    <>
      <FGroup label="Nome do escritório" required error={errors.nome}>
        <input type="text" value={s2.nome} onChange={e => setS2(v => ({ ...v, nome: e.target.value }))} placeholder="Silva & Associados Advogados" style={inp} onFocus={focusFn} onBlur={blurFn} />
      </FGroup>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 14 }}>
        <FGroup label="CNPJ">
          <input type="text" value={s2.cnpj} onChange={e => setS2(v => ({ ...v, cnpj: e.target.value }))} placeholder="00.000.000/0001-81" style={inp} onFocus={focusFn} onBlur={blurFn} />
        </FGroup>
        <FGroup label="OAB do responsável" required error={errors.oab}>
          <input type="text" value={s2.oab} onChange={e => setS2(v => ({ ...v, oab: e.target.value }))} placeholder="SP 123.456" style={inp} onFocus={focusFn} onBlur={blurFn} />
        </FGroup>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 14 }}>
        <FGroup label="Nome do responsável" required error={errors.responsavel}>
          <input type="text" value={s2.responsavel} onChange={e => setS2(v => ({ ...v, responsavel: e.target.value }))} placeholder="Dr. João Silva" style={inp} onFocus={focusFn} onBlur={blurFn} />
        </FGroup>
        <FGroup label="Nº de advogados">
          <select value={s2.advogados} onChange={e => setS2(v => ({ ...v, advogados: e.target.value }))} style={inp} onFocus={focusFn} onBlur={blurFn}>
            {['1','2–5','6–15','15–50','50+'].map(o => <option key={o}>{o}</option>)}
          </select>
        </FGroup>
      </div>

      <FGroup label="Áreas de atuação">
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 2 }}>
          {AREAS.map(a => (
            <Pill key={a} active={s2.areas.includes(a)} onClick={() => setS2(v => ({ ...v, areas: v.areas.includes(a) ? v.areas.filter(x => x !== a) : [...v.areas, a] }))}>
              {a}
            </Pill>
          ))}
        </div>
      </FGroup>

      <InfoBox>Dados protegidos por <strong>AES-256</strong>. Conforme a Lei 13.709/2018 (LGPD).</InfoBox>
    </>
  )
}

/* ── Step 3 ───────────────────────────────────────────────────────────────── */

function Step3({ s3, setS3, errors }: { s3: S3; setS3: Dispatch<SetStateAction<S3>>; errors: Record<string, string> }) {
  const [hIni, mIni] = s3.inicio.split(':')
  const [hFim, mFim] = s3.fim.split(':')
  const diasOrdenados = DAYS.filter(d => s3.dias.includes(d)).join(', ')
  const hOpts = Array.from({ length: 24 }, (_, i) => String(i).padStart(2, '0'))
  const mOpts = ['00','15','30','45']

  return (
    <>
      <div style={{ textAlign: 'center', marginBottom: 20 }}>
        <div style={{ display: 'inline-block', padding: 14, background: 'var(--color-am-bg)', borderRadius: 14, border: '1px solid var(--color-am-border)', marginBottom: 10 }}>
          <svg width="120" height="120" viewBox="0 0 130 130">
            <rect x="0" y="0" width="40" height="40" rx="4" fill="var(--color-am-blue)" opacity="0.8"/><rect x="8" y="8" width="24" height="24" rx="2" fill="white"/><rect x="12" y="12" width="16" height="16" rx="1" fill="var(--color-am-blue)"/>
            <rect x="90" y="0" width="40" height="40" rx="4" fill="var(--color-am-blue)" opacity="0.8"/><rect x="98" y="8" width="24" height="24" rx="2" fill="white"/><rect x="102" y="12" width="16" height="16" rx="1" fill="var(--color-am-blue)"/>
            <rect x="0" y="90" width="40" height="40" rx="4" fill="var(--color-am-blue)" opacity="0.8"/><rect x="8" y="98" width="24" height="24" rx="2" fill="white"/><rect x="12" y="102" width="16" height="16" rx="1" fill="var(--color-am-blue)"/>
            <rect x="50" y="10" width="8" height="8" rx="1" fill="var(--color-am-blue)" opacity="0.5"/><rect x="62" y="10" width="8" height="8" rx="1" fill="var(--color-am-blue)" opacity="0.5"/>
            <rect x="10" y="50" width="8" height="8" rx="1" fill="var(--color-am-blue)" opacity="0.5"/><rect x="10" y="62" width="8" height="8" rx="1" fill="var(--color-am-blue)" opacity="0.5"/>
            <rect x="50" y="50" width="30" height="30" rx="4" fill="var(--color-am-blue)" opacity="0.12"/><rect x="56" y="56" width="18" height="18" rx="2" fill="var(--color-am-blue)" opacity="0.45"/>
          </svg>
        </div>
        <p style={{ fontSize: 12, color: 'var(--color-am-muted)', marginBottom: 8 }}>WhatsApp → Dispositivos vinculados → Vincular dispositivo</p>
        <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '4px 12px', background: 'rgba(26,158,120,0.08)', border: '1px solid rgba(26,158,120,0.22)', borderRadius: 20 }}>
          <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--color-am-green)', display: 'inline-block' }} />
          <span style={{ fontSize: 11, color: 'var(--color-am-green)', fontWeight: 700 }}>Aguardando conexão…</span>
        </div>
      </div>

      <div style={{ height: 1, background: 'var(--color-am-border)', margin: '4px 0 18px' }} />

      <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--color-am-ink)', marginBottom: 4 }}>Janela de envio de mensagens</div>
      <p style={{ fontSize: 12, color: 'var(--color-am-muted)', lineHeight: 1.6, marginBottom: 16 }}>
        Define quando a IA pode enviar mensagens. Fora desse horário as mensagens ficam em fila.
      </p>

      <FGroup label="Dias de atendimento" error={errors.dias}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 2 }}>
          {DAYS.map(d => (
            <Pill key={d} active={s3.dias.includes(d)} onClick={() => setS3(v => ({ ...v, dias: v.dias.includes(d) ? v.dias.filter(x => x !== d) : [...v.dias, d] }))}>
              {d}
            </Pill>
          ))}
        </div>
      </FGroup>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
        {([['Início', hIni, mIni, 'inicio'], ['Fim', hFim, mFim, 'fim']] as const).map(([lbl, h, m, field]) => (
          <div key={field}>
            <label style={labelSt}>{lbl}</label>
            <div style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '9px 12px', background: 'var(--color-am-bg)', border: '1px solid var(--color-am-border)', borderRadius: 12 }}>
              <select value={h} onChange={e => setS3(v => ({ ...v, [field]: e.target.value + ':' + m }))} style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-am-ink)', background: 'transparent', border: 'none', outline: 'none', cursor: 'pointer' }}>
                {hOpts.map(o => <option key={o} value={o}>{o}h</option>)}
              </select>
              <span style={{ color: 'var(--color-am-muted)', fontSize: 13 }}>:</span>
              <select value={m} onChange={e => setS3(v => ({ ...v, [field]: h + ':' + e.target.value }))} style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-am-ink)', background: 'transparent', border: 'none', outline: 'none', cursor: 'pointer' }}>
                {mOpts.map(o => <option key={o} value={o}>{o}min</option>)}
              </select>
            </div>
          </div>
        ))}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 12px', background: 'var(--color-am-bg)', border: '1px solid var(--color-am-border)', borderRadius: 12, fontSize: 12, color: 'var(--color-am-muted)' }}>
        A IA enviará mensagens de <strong style={{ color: 'var(--color-am-ink)', marginLeft: 3 }}>{s3.inicio}</strong>&nbsp;às&nbsp;<strong style={{ color: 'var(--color-am-ink)' }}>{s3.fim}</strong>&nbsp;nos dias:&nbsp;<strong style={{ color: 'var(--color-am-ink)' }}>{diasOrdenados}</strong>.
      </div>
    </>
  )
}

/* ── Step 4 ───────────────────────────────────────────────────────────────── */

function Step4({ s4, setS4 }: { s4: S4; setS4: Dispatch<SetStateAction<S4>> }) {
  const nome    = s4.assistente || 'Sofia'
  const preview = `Olá! Sou ${nome}, assistente virtual do escritório. Em que posso ajudar?`

  return (
    <>
      <FGroup label="Nome da assistente" required>
        <input type="text" value={s4.assistente} onChange={e => setS4(v => ({ ...v, assistente: e.target.value }))} placeholder="Ex: Sofia, Laura, Rafael, Bruno…" style={inp} onFocus={focusFn} onBlur={blurFn} />
      </FGroup>

      <FGroup label="Tom de comunicação">
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
          {TONS.map(t => (
            <Pill key={t} active={s4.tom === t} onClick={() => setS4(v => ({ ...v, tom: t }))} square>
              {t}
            </Pill>
          ))}
        </div>
      </FGroup>

      <div style={{ background: 'var(--color-am-surface)', borderRadius: 12, padding: '12px 14px', marginTop: 6 }}>
        <div style={labelSt}>Pré-visualização</div>
        <div style={{ display: 'inline-block', background: '#fff', borderRadius: '4px 12px 12px 12px', padding: '9px 13px', maxWidth: '85%', boxShadow: '0 1px 3px rgba(12,30,48,0.08)' }}>
          <p style={{ fontSize: 13, color: 'var(--color-am-ink)', margin: 0, lineHeight: 1.5 }}>{preview}</p>
          <p style={{ fontSize: 10, color: 'var(--color-am-muted)', textAlign: 'right', margin: '3px 0 0' }}>08:00 ✓✓</p>
        </div>
      </div>
    </>
  )
}

/* ── Step 5 ───────────────────────────────────────────────────────────────── */

const COMPLIANCE = [
  ['A IA não emite pareceres jurídicos',      'Respostas informativas; estratégias são escaladas ao advogado.'],
  ['Score de risco exclusivo para advogados', 'Probabilidade de resultado nunca é exibida ao cliente.'],
  ['Prospecção B2C sem dados pessoais',        'Sem CPF, telefone ou e-mail via fontes processuais.'],
  ['Disclaimer na 1ª interação',              'Configurado automaticamente em cada conversa iniciada.'],
  ['Escalação automática fora de escopo',     'Pareceres e situações sensíveis vão diretamente ao advogado.'],
]

function Step5({ aceite, setAceite, errors }: { aceite: boolean; setAceite: Dispatch<SetStateAction<boolean>>; errors: Record<string, string> }) {
  return (
    <>
      {COMPLIANCE.map(([title, sub]) => (
        <div key={title} style={{ display: 'flex', gap: 10, padding: '10px 12px', background: 'var(--color-am-bg)', border: '1px solid var(--color-am-border)', borderRadius: 12, marginBottom: 7 }}>
          <div style={{ width: 20, height: 20, borderRadius: 6, flexShrink: 0, background: 'rgba(26,158,120,0.10)', border: '1px solid rgba(26,158,120,0.25)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginTop: 1 }}>
            <CheckIcon color="#2E9E6B" size={12} />
          </div>
          <div>
            <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--color-am-ink)', marginBottom: 1 }}>{title}</div>
            <div style={{ fontSize: 11, color: 'var(--color-am-muted)' }}>{sub}</div>
          </div>
        </div>
      ))}

      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10, marginTop: 14, padding: '12px 14px', borderRadius: 12, background: aceite ? 'rgba(26,158,120,0.05)' : 'rgba(200,48,48,0.04)', border: `1px solid ${aceite ? 'rgba(26,158,120,0.22)' : 'rgba(200,48,48,0.15)'}`, transition: 'all 0.2s' }}>
        <input type="checkbox" id="aceite-cb" checked={aceite} onChange={e => setAceite(e.target.checked)} style={{ width: 14, height: 14, marginTop: 2, accentColor: 'var(--color-am-blue)', flexShrink: 0, cursor: 'pointer' }} />
        <label htmlFor="aceite-cb" style={{ fontSize: 12, color: 'var(--color-am-ink)', lineHeight: 1.5, cursor: 'pointer' }}>
          Declaro que li e concordo com os termos de uso ético da IA conforme o Provimento 205/2021 do Conselho Federal da OAB.{' '}
          <span style={{ color: 'var(--color-am-blue)' }}>*</span>
        </label>
      </div>
      {errors.aceite && <p style={{ fontSize: 11, color: 'var(--color-am-muted)', marginTop: 5 }}>⚠ Obrigatório para avançar.</p>}
    </>
  )
}

/* ── Step 6 ───────────────────────────────────────────────────────────────── */

function Step6({ s1, s2, s3, s4, aceite }: { s1: S1; s2: S2; s3: S3; s4: S4; aceite: boolean }) {
  const diasOrdenados = DAYS.filter(d => s3.dias.includes(d)).join(', ')
  const rows = [
    { label: 'E-mail',          value: s1.email       || '—', filled: !!s1.email,       hi: false },
    { label: 'Escritório',      value: s2.nome         || '—', filled: !!s2.nome,        hi: false },
    { label: 'OAB',             value: s2.oab          || '—', filled: !!s2.oab,         hi: false },
    { label: 'WhatsApp',        value: 'Conectado ✓',          filled: true,              hi: true  },
    { label: 'Janela de envio', value: `${s3.inicio}–${s3.fim} · ${diasOrdenados}`, filled: true, hi: false },
    { label: 'Assistente',      value: s4.assistente ? `${s4.assistente}${s4.tom ? ' · ' + s4.tom : ''}` : '—', filled: !!s4.assistente, hi: false },
    { label: 'Conformidade',    value: aceite ? 'OAB + LGPD ✓' : 'Pendente', filled: aceite, hi: aceite },
  ]

  return (
    <>
      <div style={{ textAlign: 'center', marginBottom: 20 }}>
        <div style={{ width: 52, height: 52, borderRadius: '50%', background: 'rgba(26,158,120,0.10)', border: '1.5px solid rgba(26,158,120,0.25)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 12px' }}>
          <CheckIcon size={24} color="#2E9E6B" />
        </div>
        <div style={{ fontSize: 18, fontWeight: 800, color: 'var(--color-am-ink)', letterSpacing: '-0.02em', marginBottom: 4 }}>Tudo pronto!</div>
        <div style={{ fontSize: 13, color: 'var(--color-am-muted)' }}>Revise os dados e ative seu escritório.</div>
      </div>

      {rows.map(r => (
        <div key={r.label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '9px 12px', background: r.hi ? 'rgba(26,158,120,0.04)' : 'var(--color-am-bg)', border: `1px solid ${r.hi ? 'rgba(26,158,120,0.20)' : 'var(--color-am-border)'}`, borderRadius: 10, marginBottom: 6 }}>
          <span style={{ fontSize: 12, color: 'var(--color-am-muted)' }}>{r.label}</span>
          <span style={{ fontSize: 12, fontWeight: r.filled ? 700 : 400, color: r.hi ? 'var(--color-am-green)' : r.filled ? 'var(--color-am-ink)' : 'var(--color-am-muted)' }}>{r.value}</span>
        </div>
      ))}

      <InfoBox>Enviaremos uma mensagem de teste no WhatsApp configurado assim que você ativar.</InfoBox>
    </>
  )
}

/* ── Shared helpers ───────────────────────────────────────────────────────── */

function FGroup({ label, required, error, children }: { label: string; required?: boolean; error?: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <label style={labelSt}>
        {label}{required && <span style={{ color: 'var(--color-am-blue)', marginLeft: 2 }}>*</span>}
      </label>
      {error && <p style={{ fontSize: 11, color: 'var(--color-am-red)', marginBottom: 4 }}>{error}</p>}
      {children}
    </div>
  )
}

function Pill({ active, onClick, children, square }: { active: boolean; onClick: () => void; children: React.ReactNode; square?: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{ padding: square ? '9px 12px' : '5px 13px', borderRadius: square ? 10 : 20, cursor: 'pointer', fontFamily: 'var(--font-sans)', fontSize: 12, fontWeight: active ? 700 : 500, background: active ? 'rgba(58,122,184,0.08)' : '#fff', border: `1px solid ${active ? 'var(--color-am-blue)' : 'var(--color-am-border)'}`, color: active ? 'var(--color-am-blue)' : 'var(--color-am-secondary)', transition: 'all 0.15s', textAlign: 'left' }}
    >
      {children}
    </button>
  )
}

function InfoBox({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ padding: '10px 14px', background: 'rgba(58,122,184,0.05)', border: '1px solid rgba(58,122,184,0.15)', borderRadius: 12, marginTop: 10, fontSize: 12, color: 'var(--color-am-secondary)', lineHeight: 1.6 }}>
      {children}
    </div>
  )
}

function EyeBtn({ visible, onToggle }: { visible: boolean; onToggle: () => void }) {
  return (
    <button type="button" onClick={onToggle} style={{ position: 'absolute', right: 11, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', padding: 0, display: 'flex', alignItems: 'center' }}>
      {visible
        ? <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="var(--color-am-muted)" strokeWidth="1.8" strokeLinecap="round"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/></svg>
        : <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="var(--color-am-muted)" strokeWidth="1.8" strokeLinecap="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
      }
    </button>
  )
}

function CheckIcon({ size = 14, color = 'white' }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="4 12 9 17 20 7"/>
    </svg>
  )
}

function AmicusLogo() {
  return (
    <span style={{ fontSize: 20, fontWeight: 900, letterSpacing: '-0.04em', background: 'linear-gradient(135deg, #0C1E30 0%, #1248BE 100%)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text', fontFamily: 'var(--font-sans)' }}>
      amicus
    </span>
  )
}

/* ── Style constants ──────────────────────────────────────────────────────── */

const labelSt: CSSProperties = {
  display: 'block', fontSize: 10, fontWeight: 700,
  color: 'var(--color-am-secondary)', textTransform: 'uppercase',
  letterSpacing: '0.08em', marginBottom: 6,
}

const inp: CSSProperties = {
  width: '100%', boxSizing: 'border-box', padding: '10px 12px',
  fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--color-am-ink)',
  background: 'var(--color-am-bg)', border: '1px solid var(--color-am-border)',
  borderRadius: 12, outline: 'none', resize: 'vertical',
  transition: 'border-color 0.14s ease, box-shadow 0.14s ease',
}

const focusFn = (e: React.FocusEvent<HTMLInputElement | HTMLSelectElement>) => {
  e.target.style.borderColor = 'var(--color-am-blue)'
  e.target.style.boxShadow   = '0 0 0 3px rgba(58,122,184,0.12)'
}
const blurFn = (e: React.FocusEvent<HTMLInputElement | HTMLSelectElement>) => {
  e.target.style.borderColor = 'var(--color-am-border)'
  e.target.style.boxShadow   = 'none'
}

const primaryBtn: CSSProperties = {
  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
  padding: '10px 24px', background: 'linear-gradient(135deg, #1248BE 0%, #3A7AB8 100%)',
  color: '#fff', fontFamily: 'var(--font-sans)', fontWeight: 700, fontSize: 13,
  border: 'none', borderRadius: 12, cursor: 'pointer',
  boxShadow: '0 4px 16px rgba(18,72,190,0.22), inset 0 1px 0 rgba(255,255,255,0.15)',
}

const ghostBtn: CSSProperties = {
  padding: '9px 18px', background: '#fff',
  border: '1px solid var(--color-am-border)', borderRadius: 12,
  fontFamily: 'var(--font-sans)', fontSize: 13, color: 'var(--color-am-muted)',
  cursor: 'pointer', transition: 'border-color 0.14s, color 0.14s',
}
