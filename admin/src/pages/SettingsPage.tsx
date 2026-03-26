import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { onboardingApi } from '../api'
import { Spinner, ErrorBox } from '../components/ui'

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<'persona' | 'templates' | 'status'>('persona')

  const { data: status, isLoading } = useQuery({
    queryKey: ['onboarding-status'],
    queryFn: onboardingApi.status,
  })

  const [persona, setPersona] = useState({ persona_nome: '', persona_tom: 'formal', horario_inicio: '08:00', horario_fim: '18:00' })
  const [templates, setTemplates] = useState({ template_boas_vindas: '', template_atualizacao: '', template_sem_novidade: '' })
  const [saved, setSaved] = useState('')

  const { mutate: savePersona, isPending: savingPersona, error: personaError } = useMutation({
    mutationFn: () => onboardingApi.configurarIA(persona),
    onSuccess: () => { setSaved('persona'); setTimeout(() => setSaved(''), 2000) },
  })
  const { mutate: saveTemplates, isPending: savingTemplates, error: templatesError } = useMutation({
    mutationFn: () => onboardingApi.configurarTemplates(templates),
    onSuccess: () => { setSaved('templates'); setTimeout(() => setSaved(''), 2000) },
  })

  if (isLoading) return <Spinner />

  const esc = status?.escritorio

  // Pre-fill com dados do backend
  if (esc && !persona.persona_nome && esc.persona_nome) {
    setPersona(p => ({ ...p, persona_nome: esc.persona_nome ?? '', persona_tom: esc.persona_tom ?? 'formal' }))
  }

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">Configurações</h1>
        <p className="page-subtitle">Persona da IA, templates e status do sistema</p>
      </div>

      <div style={{ borderBottom: '1px solid var(--surface-border)', marginBottom: 24, display: 'flex' }}>
        <button className={`tab ${activeTab === 'persona' ? 'active' : ''}`} onClick={() => setActiveTab('persona')}>🤖 Persona IA</button>
        <button className={`tab ${activeTab === 'templates' ? 'active' : ''}`} onClick={() => setActiveTab('templates')}>📝 Templates</button>
        <button className={`tab ${activeTab === 'status' ? 'active' : ''}`} onClick={() => setActiveTab('status')}>📊 Status</button>
      </div>

      {activeTab === 'persona' && (
        <div className="surface" style={{ padding: 24, maxWidth: 560 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 16 }}>Configurar Persona da IA</div>
          {personaError && <div style={{ marginBottom: 12 }}><ErrorBox message="Falha ao salvar persona." /></div>}
          {saved === 'persona' && <div style={{ marginBottom: 12, color: 'var(--success)', fontSize: 13 }}>✅ Persona salva com sucesso!</div>}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div>
              <label className="label">Nome da IA</label>
              <input className="input" value={persona.persona_nome} onChange={e => setPersona(p => ({ ...p, persona_nome: e.target.value }))} placeholder="Assistente Jurídico" />
            </div>
            <div>
              <label className="label">Tom de Voz</label>
              <select className="input" value={persona.persona_tom} onChange={e => setPersona(p => ({ ...p, persona_tom: e.target.value }))}>
                <option value="formal">Formal</option>
                <option value="amigavel">Amigável</option>
                <option value="neutro">Neutro</option>
              </select>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <div>
                <label className="label">Horário de Início</label>
                <input className="input" type="time" value={persona.horario_inicio} onChange={e => setPersona(p => ({ ...p, horario_inicio: e.target.value }))} />
              </div>
              <div>
                <label className="label">Horário de Fim</label>
                <input className="input" type="time" value={persona.horario_fim} onChange={e => setPersona(p => ({ ...p, horario_fim: e.target.value }))} />
              </div>
            </div>
            <button className="btn btn-primary" onClick={() => savePersona()} disabled={savingPersona || !persona.persona_nome}>
              {savingPersona ? <><Spinner size={12} /> Salvando...</> : 'Salvar Persona'}
            </button>
          </div>
        </div>
      )}

      {activeTab === 'templates' && (
        <div className="surface" style={{ padding: 24, maxWidth: 560 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 16 }}>Templates de Mensagem WhatsApp</div>
          {templatesError && <div style={{ marginBottom: 12 }}><ErrorBox message="Falha ao salvar templates." /></div>}
          {saved === 'templates' && <div style={{ marginBottom: 12, color: 'var(--success)', fontSize: 13 }}>✅ Templates salvos com sucesso!</div>}
          <p style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 16, lineHeight: 1.5 }}>
            Use <code>{'{{nome_cliente}}'}</code> e <code>{'{{resumo_andamento}}'}</code> como placeholders.
            Deixe vazio para manter o template atual.
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div>
              <label className="label">Boas-Vindas (requer {'{nome_cliente}'})</label>
              <textarea className="input" rows={3} value={templates.template_boas_vindas} onChange={e => setTemplates(t => ({ ...t, template_boas_vindas: e.target.value }))} placeholder="Olá {nome_cliente}! Bem-vindo ao escritório..." />
            </div>
            <div>
              <label className="label">Atualização de Processo</label>
              <textarea className="input" rows={3} value={templates.template_atualizacao} onChange={e => setTemplates(t => ({ ...t, template_atualizacao: e.target.value }))} placeholder="Olá {nome_cliente}! Novidades no seu processo: {resumo_andamento}" />
            </div>
            <div>
              <label className="label">Sem Novidade</label>
              <textarea className="input" rows={3} value={templates.template_sem_novidade} onChange={e => setTemplates(t => ({ ...t, template_sem_novidade: e.target.value }))} placeholder="Olá {nome_cliente}, consultamos seu processo e não há novidades." />
            </div>
            <button className="btn btn-primary" onClick={() => saveTemplates()} disabled={savingTemplates}>
              {savingTemplates ? <><Spinner size={12} /> Salvando...</> : 'Salvar Templates'}
            </button>
          </div>
        </div>
      )}

      {activeTab === 'status' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, maxWidth: 560 }}>
          <div className="surface" style={{ padding: 20 }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14 }}>Status do Onboarding</div>
            {status?.etapas.map(e => (
              <div key={e.numero} style={{ display: 'flex', gap: 10, marginBottom: 8, alignItems: 'center' }}>
                <span style={{ fontSize: 16 }}>{e.concluida ? '✅' : '⭕'}</span>
                <div>
                  <div style={{ fontSize: 13, color: e.concluida ? 'var(--text-primary)' : 'var(--text-muted)', fontWeight: 500 }}>{e.nome}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{e.descricao}</div>
                </div>
              </div>
            ))}
            <div style={{ marginTop: 12, fontSize: 12, color: 'var(--text-muted)' }}>
              {status?.onboarding_completo ? '🟢 Escritório operacional' : `⚠️ ${status?.percentual_completo}% concluído`}
            </div>
          </div>

          <div className="surface" style={{ padding: 20 }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14 }}>Dados do Escritório</div>
            {esc && (
              <div style={{ fontSize: 13, display: 'flex', flexDirection: 'column', gap: 6 }}>
                <div style={{ color: 'var(--text-muted)' }}>Nome: <span style={{ color: 'var(--text-primary)' }}>{esc.nome}</span></div>
                <div style={{ color: 'var(--text-muted)' }}>Persona: <span style={{ color: 'var(--text-primary)' }}>{esc.persona_nome ?? '—'}</span> · Tom: {esc.persona_tom ?? '—'}</div>
                <div style={{ color: 'var(--text-muted)' }}>WhatsApp: <span style={{ color: esc.whatsapp_conectado ? 'var(--success)' : 'var(--danger)' }}>{esc.whatsapp_conectado ? '✅ Conectado' : '❌ Desconectado'}</span></div>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  )
}
