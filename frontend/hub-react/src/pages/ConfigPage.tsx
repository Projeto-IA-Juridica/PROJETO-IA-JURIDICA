import { useState } from 'react'
import { Settings, Save, Bot, Clock, MessageSquare, Building2, CheckCircle } from 'lucide-react'
import type { Configuracoes } from '../types'

const DEFAULT_CFG: Configuracoes = {
  nome:                 'Escritório Amicus',
  cnpj:                 '',
  email:                'contato@amicus.adv.br',
  telefone:             '',
  persona_nome:         'Dra. Camila',
  persona_tom:          'formal',
  horario_inicio:       '08:00',
  horario_fim:          '18:00',
  template_boas_vindas: 'Olá {{nome}}, seja bem-vindo(a) ao {{escritorio}}! Sou a {{persona}} e estou aqui para auxiliá-lo(a). Como posso ajudar?',
  template_atualizacao: 'Olá {{nome}}, temos uma atualização importante sobre o seu processo {{processo}}. {{mensagem}}',
  template_sem_novidade:'Olá {{nome}}, verificamos o andamento do seu processo {{processo}} e não há novidades para informar no momento. Seguimos acompanhando de perto.',
}

const TOM_OPTS: { value: Configuracoes['persona_tom']; label: string; desc: string }[] = [
  { value: 'formal',   label: 'Formal',   desc: 'Linguagem técnica e protocolar'     },
  { value: 'amigavel', label: 'Amigável', desc: 'Tom próximo e acolhedor'            },
  { value: 'tecnico',  label: 'Técnico',  desc: 'Foco em precisão e detalhamento'   },
]

function SectionTitle({ icon, label, desc }: { icon: React.ReactNode; label: string; desc: string }) {
  return (
    <div className="flex items-center gap-3 mb-4">
      <div className="w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0"
        style={{ background: 'rgba(58,122,184,0.1)', border: '1px solid rgba(58,122,184,0.2)' }}>
        <span className="text-am-blue">{icon}</span>
      </div>
      <div>
        <div className="text-sm font-bold text-am-ink">{label}</div>
        <div className="text-[10px] text-am-muted">{desc}</div>
      </div>
    </div>
  )
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <label className="text-[10px] font-bold text-am-secondary uppercase tracking-wider block">
        {label}
      </label>
      {children}
      {hint && <p className="text-[10px] text-am-muted">{hint}</p>}
    </div>
  )
}

const inputCls = "w-full px-3 py-2.5 text-xs border border-am-border rounded-xl bg-am-bg text-am-ink outline-none transition-fast placeholder:text-am-muted"
const focusInput = (e: React.FocusEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
  (e.target.style.borderColor = 'var(--color-am-blue)')
const blurInput = (e: React.FocusEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
  (e.target.style.borderColor = 'var(--color-am-border)')

export default function ConfigPage() {
  const [cfg, setCfg]       = useState<Configuracoes>(DEFAULT_CFG)
  const [saved, setSaved]   = useState(false)

  function update<K extends keyof Configuracoes>(key: K, value: Configuracoes[K]) {
    setCfg((prev) => ({ ...prev, [key]: value }))
    setSaved(false)
  }

  function handleSave(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setSaved(true)
    setTimeout(() => setSaved(false), 3000)
  }

  return (
    <div className="flex-1 overflow-y-auto">
      <form onSubmit={handleSave}>
        <div className="p-4 sm:p-6 max-w-3xl mx-auto space-y-6 page-enter">

          {/* Header */}
          <div className="flex items-center justify-between flex-wrap gap-4">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0"
                style={{ background: 'rgba(58,122,184,0.1)', border: '1px solid rgba(58,122,184,0.2)' }}>
                <Settings size={16} className="text-am-blue" />
              </div>
              <div>
                <h2 className="text-lg font-extrabold text-am-ink tracking-tight">Configurações</h2>
                <p className="text-xs text-am-muted mt-0.5">Personalize o escritório e a IA</p>
              </div>
            </div>
            <button type="submit"
              className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-white text-xs font-bold transition-fast"
              style={{ background: saved ? '#1A9E78' : 'var(--color-am-blue)' }}
              onMouseEnter={(e) => { if (!saved) e.currentTarget.style.background = 'var(--color-am-blue-hover)' }}
              onMouseLeave={(e) => { if (!saved) e.currentTarget.style.background = 'var(--color-am-blue)' }}>
              {saved ? <><CheckCircle size={13} /> Salvo</> : <><Save size={13} /> Salvar</>}
            </button>
          </div>

          {/* Dados do escritório */}
          <div className="bg-white rounded-2xl card-shadow border border-am-border p-5 card-border-hover">
            <SectionTitle icon={<Building2 size={14} />} label="Dados do Escritório" desc="Informações básicas do seu escritório" />
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="sm:col-span-2">
                <Field label="Nome do escritório">
                  <input type="text" value={cfg.nome}
                    onChange={(e) => update('nome', e.target.value)}
                    className={inputCls} onFocus={focusInput} onBlur={blurInput} />
                </Field>
              </div>
              <Field label="CNPJ">
                <input type="text" value={cfg.cnpj} placeholder="00.000.000/0001-00"
                  onChange={(e) => update('cnpj', e.target.value)}
                  className={inputCls} onFocus={focusInput} onBlur={blurInput} />
              </Field>
              <Field label="E-mail">
                <input type="email" value={cfg.email}
                  onChange={(e) => update('email', e.target.value)}
                  className={inputCls} onFocus={focusInput} onBlur={blurInput} />
              </Field>
              <Field label="Telefone / WhatsApp">
                <input type="tel" value={cfg.telefone ?? ''} placeholder="(11) 9 9999-9999"
                  onChange={(e) => update('telefone', e.target.value)}
                  className={inputCls} onFocus={focusInput} onBlur={blurInput} />
              </Field>
            </div>
          </div>

          {/* Persona da IA */}
          <div className="bg-white rounded-2xl card-shadow border border-am-border p-5 card-border-hover">
            <SectionTitle icon={<Bot size={14} />} label="Persona da IA" desc="Como a Dra. Camila se apresentará aos clientes" />
            <div className="space-y-4">
              <Field label="Nome da persona">
                <input type="text" value={cfg.persona_nome}
                  onChange={(e) => update('persona_nome', e.target.value)}
                  className={inputCls} onFocus={focusInput} onBlur={blurInput} />
              </Field>

              <Field label="Tom de comunicação">
                <div className="grid grid-cols-3 gap-2 mt-1">
                  {TOM_OPTS.map((opt) => {
                    const active = cfg.persona_tom === opt.value
                    return (
                      <button key={opt.value} type="button"
                        onClick={() => update('persona_tom', opt.value)}
                        className="flex flex-col items-start gap-1 px-3 py-2.5 rounded-xl border transition-fast text-left"
                        style={active
                          ? { background: 'var(--color-am-surface)', border: '1px solid var(--color-am-blue)', borderLeft: '3px solid var(--color-am-blue)' }
                          : { background: 'var(--color-am-bg)', border: '1px solid var(--color-am-border)' }}>
                        <span className="text-xs font-bold" style={{ color: active ? 'var(--color-am-blue)' : 'var(--color-am-ink)' }}>
                          {opt.label}
                        </span>
                        <span className="text-[10px] text-am-muted leading-tight">{opt.desc}</span>
                      </button>
                    )
                  })}
                </div>
              </Field>
            </div>
          </div>

          {/* Horários */}
          <div className="bg-white rounded-2xl card-shadow border border-am-border p-5 card-border-hover">
            <SectionTitle icon={<Clock size={14} />} label="Horário de Atendimento" desc="Janela de respostas automáticas" />
            <div className="grid grid-cols-2 gap-4">
              <Field label="Início">
                <input type="time" value={cfg.horario_inicio}
                  onChange={(e) => update('horario_inicio', e.target.value)}
                  className={inputCls} onFocus={focusInput} onBlur={blurInput} />
              </Field>
              <Field label="Fim">
                <input type="time" value={cfg.horario_fim}
                  onChange={(e) => update('horario_fim', e.target.value)}
                  className={inputCls} onFocus={focusInput} onBlur={blurInput} />
              </Field>
            </div>
            <p className="text-[10px] text-am-muted mt-3">
              Fora desse horário, a IA responde informando que o escritório está fechado e que entrará em contato em breve.
            </p>
          </div>

          {/* Templates */}
          <div className="bg-white rounded-2xl card-shadow border border-am-border p-5 card-border-hover">
            <SectionTitle icon={<MessageSquare size={14} />} label="Mensagens Automáticas" desc="Templates enviados via WhatsApp" />
            <div className="space-y-4">
              {([
                { key: 'template_boas_vindas',  label: 'Boas-vindas',        hint: 'Enviado quando um novo cliente inicia contato.' },
                { key: 'template_atualizacao',  label: 'Atualização de processo', hint: 'Enviado ao detectar novo andamento.' },
                { key: 'template_sem_novidade', label: 'Sem novidades',      hint: 'Enviado quando o processo não tem andamentos recentes.' },
              ] as const).map(({ key, label, hint }) => (
                <Field key={key} label={label} hint={hint}>
                  <textarea rows={3} value={cfg[key]}
                    onChange={(e) => update(key, e.target.value)}
                    className={`${inputCls} resize-none leading-relaxed`}
                    onFocus={focusInput} onBlur={blurInput}
                  />
                </Field>
              ))}
              <div className="rounded-xl px-4 py-3 text-[10px] text-am-secondary leading-relaxed"
                style={{ background: 'rgba(58,122,184,0.05)', border: '1px solid rgba(58,122,184,0.18)' }}>
                <strong className="text-am-ink">Variáveis disponíveis:</strong>
                {' '}{'{{nome}}'} — nome do cliente,
                {' '}{'{{escritorio}}'} — nome do escritório,
                {' '}{'{{persona}}'} — nome da IA,
                {' '}{'{{processo}}'} — número CNJ,
                {' '}{'{{mensagem}}'} — texto do andamento
              </div>
            </div>
          </div>

          {/* Salvar fixo */}
          <div className="flex justify-end pb-2">
            <button type="submit"
              className="flex items-center gap-2 px-6 py-3 rounded-xl text-white text-xs font-bold transition-fast"
              style={{ background: saved ? '#1A9E78' : 'var(--color-am-blue)' }}
              onMouseEnter={(e) => { if (!saved) e.currentTarget.style.background = 'var(--color-am-blue-hover)' }}
              onMouseLeave={(e) => { if (!saved) e.currentTarget.style.background = 'var(--color-am-blue)' }}>
              {saved ? <><CheckCircle size={14} /> Configurações salvas</> : <><Save size={14} /> Salvar configurações</>}
            </button>
          </div>
        </div>
      </form>
    </div>
  )
}
