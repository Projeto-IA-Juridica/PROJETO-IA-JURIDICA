import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { adminImportApi, onboardingApi } from '../api'
import { useAuth } from '../context/AuthContext'
import { Spinner, ErrorBox } from '../components/ui'
import { AlertTriangle } from 'lucide-react'

type Tab = 'profile' | 'persona' | 'templates' | 'onboarding' | 'status'

export default function SettingsPage() {
  const qc = useQueryClient()
  const { user, logout } = useAuth()
  const [activeTab, setActiveTab] = useState<Tab>('profile')

  const { data: status, isLoading, error: statusError } = useQuery({
    queryKey: ['onboarding-status'],
    queryFn: onboardingApi.status,
    retry: 0,
  })

  const [persona, setPersona] = useState({ persona_nome: '', persona_tom: 'formal', horario_inicio: '08:00', horario_fim: '18:00' })
  const [templates, setTemplates] = useState({ template_boas_vindas: '', template_atualizacao: '', template_sem_novidade: '' })
  const [csvFile, setCsvFile] = useState<File | null>(null)
  const [saved, setSaved] = useState('')
  const [importResult, setImportResult] = useState<string>('')
  const [whatsappFeedback, setWhatsappFeedback] = useState<string>('')
  const [whatsappError, setWhatsappError] = useState<string>('')
  const [whatsappQr, setWhatsappQr] = useState<string | null>(null)

  useEffect(() => {
    const esc = status?.escritorio
    if (!esc) return
    setPersona((prev) => {
      if (prev.persona_nome) return prev
      return { ...prev, persona_nome: esc.persona_nome ?? '', persona_tom: esc.persona_tom ?? 'formal' }
    })
  }, [status])

  const { mutate: savePersona, isPending: savingPersona, error: personaError } = useMutation({
    mutationFn: () => onboardingApi.configurarIA(persona),
    onSuccess: () => { setSaved('persona'); qc.invalidateQueries({ queryKey: ['onboarding-status'] }); setTimeout(() => setSaved(''), 2000) },
  })

  const { mutate: saveTemplates, isPending: savingTemplates, error: templatesError } = useMutation({
    mutationFn: () => onboardingApi.configurarTemplates(templates),
    onSuccess: () => { setSaved('templates'); qc.invalidateQueries({ queryKey: ['onboarding-status'] }); setTimeout(() => setSaved(''), 2000) },
  })

  const { mutate: importPreview, isPending: previewing } = useMutation({
    mutationFn: () => onboardingApi.importProcessos(csvFile!, true),
    onSuccess: (res: Record<string, unknown>) => setImportResult(`Preview: ${Number(res.importados ?? 0) + Number(res.atualizados ?? 0)} validada(s).`),
  })

  const { mutate: importReal, isPending: importing } = useMutation({
    mutationFn: () => onboardingApi.importProcessos(csvFile!, false),
    onSuccess: (res: Record<string, unknown>) => {
      setImportResult(`Importação: ${res.importados} novo(s), ${res.atualizados} atualizado(s).`)
      qc.invalidateQueries({ queryKey: ['onboarding-status'] })
    },
  })

  const { mutate: importClientesAdmin, isPending: importingClientes } = useMutation({
    mutationFn: () => adminImportApi.importarClientes(csvFile!, false),
    onSuccess: (res) => {
      setImportResult(`Clientes: ${res.importados}. Processos: ${res.processos_novos}.`)
      qc.invalidateQueries({ queryKey: ['onboarding-status'] })
    },
  })

  const { mutate: connectWhatsapp, isPending: connectingWhatsapp } = useMutation({
    mutationFn: onboardingApi.connectWhatsapp,
    onSuccess: (res: any) => {
      setWhatsappError('')
      setWhatsappFeedback('Solicitação enviada. Aguarde e acompanhe o status.')
      // Try to extract QR code if provided
      const q = res?.qr_code ?? res?.qrcode ?? null
      let src = null
      if (q) {
        if (typeof q === 'string') src = q
        else if (q.data) src = q.data
        else if (q.base64) src = `data:image/png;base64,${q.base64}`
        else if (q.png) src = `data:image/png;base64,${q.png}`
      }
      setWhatsappQr(src)
      qc.invalidateQueries({ queryKey: ['onboarding-status'] })
      qc.invalidateQueries({ queryKey: ['whatsapp-status'] })
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setWhatsappFeedback('')
      setWhatsappError(detail ?? 'Falha ao conectar WhatsApp. Verifique EVOLUTION_API_URL e EVOLUTION_API_KEY no backend.')
      setWhatsappQr(null)
    },
  })

  const { data: whatsappStatus } = useQuery({
    queryKey: ['whatsapp-status'],
    queryFn: onboardingApi.whatsappStatus,
    refetchInterval: 30_000, // Reduzido polling de 15s para 30s para melhorar performance
    retry: 1, // Retry apenas 1 vez em caso de falha
    staleTime: 25_000, // Considera dados frescos por 25s
  })

  const { mutate: goLive, isPending: goingLive } = useMutation({
    mutationFn: onboardingApi.goLive,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['onboarding-status'] })
      setImportResult('Go-live executado.')
    },
  })

  const esc = status?.escritorio
  const statusResumo = useMemo(() => {
    if (!status) return 'Indisponível'
    if (status.onboarding_completo) return 'Operacional'
    return `${status.percentual_completo}% concluído`
  }, [status])

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">Configurações</h1>
        <p className="page-subtitle">Onboarding, persona da IA e operação do escritório</p>
      </div>

      {/* Warning when backend is unavailable — DON'T block the page */}
      {statusError && (
        <div className="error-box" style={{ marginBottom: 16 }}>
          <AlertTriangle size={16} style={{ flexShrink: 0 }} />
          <span>Não foi possível carregar status do onboarding. Algumas informações podem estar indisponíveis.</span>
        </div>
      )}

      <div style={{ borderBottom: '1px solid var(--surface-border)', marginBottom: 20, display: 'flex' }}>
        <button className={`tab ${activeTab === 'profile' ? 'active' : ''}`} onClick={() => setActiveTab('profile')}>Perfil</button>
        <button className={`tab ${activeTab === 'persona' ? 'active' : ''}`} onClick={() => setActiveTab('persona')}>Persona IA</button>
        <button className={`tab ${activeTab === 'templates' ? 'active' : ''}`} onClick={() => setActiveTab('templates')}>Templates</button>
        <button className={`tab ${activeTab === 'onboarding' ? 'active' : ''}`} onClick={() => setActiveTab('onboarding')}>Onboarding</button>
        <button className={`tab ${activeTab === 'status' ? 'active' : ''}`} onClick={() => setActiveTab('status')}>Status</button>
      </div>

      {activeTab === 'profile' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: 12, maxWidth: 800 }}>
          <div className="surface" style={{ padding: 18 }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12 }}>Dados da conta</div>
            <div style={{ display: 'grid', gap: 6, fontSize: 13 }}>
              <div>Nome: <strong style={{ color: 'var(--text-primary)' }}>{user?.nome ?? '—'}</strong></div>
              <div>E-mail: <strong style={{ color: 'var(--text-primary)' }}>{user?.email ?? '—'}</strong></div>
              <div>Perfil: <strong style={{ color: 'var(--text-primary)' }}>{user?.role ?? '—'}</strong></div>
              <div>OAB: <strong style={{ color: 'var(--text-primary)' }}>{user?.oab ?? 'não informado'}</strong></div>
              <div>ID: <strong style={{ color: 'var(--text-primary)' }}>{user?.id ?? '—'}</strong></div>
            </div>
          </div>

          <div style={{ display: 'grid', gap: 12 }}>
            <div className="surface" style={{ padding: 18 }}>
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>Resumo</div>
              <div style={{ display: 'grid', gap: 4, fontSize: 12 }}>
                {isLoading ? <Spinner size={14} /> : (
                  <>
                    <div>Escritório: <strong style={{ color: 'var(--text-primary)' }}>{esc?.nome ?? '—'}</strong></div>
                    <div>Onboarding: <strong style={{ color: status?.onboarding_completo ? 'var(--success)' : 'var(--warning)' }}>{statusResumo}</strong></div>
                    <div>WhatsApp: <strong style={{ color: esc?.whatsapp_conectado ? 'var(--success)' : 'var(--warning)' }}>{esc?.whatsapp_conectado ? 'conectado' : 'desconectado'}</strong></div>
                  </>
                )}
              </div>
            </div>
            <div className="surface" style={{ padding: 18 }}>
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>Segurança</div>
              <div style={{ display: 'flex', gap: 8 }}>
                <button className="btn btn-secondary" onClick={() => window.location.reload()}>Recarregar</button>
                <button className="btn btn-danger" onClick={logout}>Sair</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'persona' && (
        <div className="surface" style={{ padding: 20, maxWidth: 560 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14 }}>Configurar persona da IA</div>
          {personaError && <div style={{ marginBottom: 10 }}><ErrorBox message="Falha ao salvar persona." /></div>}
          {saved === 'persona' && <div style={{ marginBottom: 10, color: 'var(--success)', fontSize: 12 }}>Salvo com sucesso.</div>}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div>
              <label className="label">Nome da IA</label>
              <input className="input" value={persona.persona_nome} onChange={(e) => setPersona(p => ({ ...p, persona_nome: e.target.value }))} />
            </div>
            <div>
              <label className="label">Tom de voz</label>
              <select className="input" value={persona.persona_tom} onChange={(e) => setPersona(p => ({ ...p, persona_tom: e.target.value }))}>
                <option value="formal">Formal</option>
                <option value="amigavel">Amigável</option>
                <option value="neutro">Neutro</option>
              </select>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              <div>
                <label className="label">Horário início</label>
                <input className="input" type="time" value={persona.horario_inicio} onChange={(e) => setPersona(p => ({ ...p, horario_inicio: e.target.value }))} />
              </div>
              <div>
                <label className="label">Horário fim</label>
                <input className="input" type="time" value={persona.horario_fim} onChange={(e) => setPersona(p => ({ ...p, horario_fim: e.target.value }))} />
              </div>
            </div>
            <button className="btn btn-primary" onClick={() => savePersona()} disabled={savingPersona || !persona.persona_nome.trim()}>
              {savingPersona ? <Spinner size={12} /> : null} Salvar persona
            </button>
          </div>
        </div>
      )}

      {activeTab === 'templates' && (
        <div className="surface" style={{ padding: 20, maxWidth: 560 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14 }}>Templates de mensagem</div>
          {templatesError && <div style={{ marginBottom: 10 }}><ErrorBox message="Falha ao salvar templates." /></div>}
          {saved === 'templates' && <div style={{ marginBottom: 10, color: 'var(--success)', fontSize: 12 }}>Salvos com sucesso.</div>}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div>
              <label className="label">Boas-vindas</label>
              <textarea className="input" rows={3} value={templates.template_boas_vindas} onChange={(e) => setTemplates(t => ({ ...t, template_boas_vindas: e.target.value }))} />
            </div>
            <div>
              <label className="label">Atualização</label>
              <textarea className="input" rows={3} value={templates.template_atualizacao} onChange={(e) => setTemplates(t => ({ ...t, template_atualizacao: e.target.value }))} />
            </div>
            <div>
              <label className="label">Sem novidade</label>
              <textarea className="input" rows={3} value={templates.template_sem_novidade} onChange={(e) => setTemplates(t => ({ ...t, template_sem_novidade: e.target.value }))} />
            </div>
            <button className="btn btn-primary" onClick={() => saveTemplates()} disabled={savingTemplates}>
              {savingTemplates ? <Spinner size={12} /> : null} Salvar templates
            </button>
          </div>
        </div>
      )}

      {activeTab === 'onboarding' && (
        <div className="surface" style={{ padding: 20, maxWidth: 700 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12 }}>Etapas do onboarding</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div>
              <label className="label">CSV para importação</label>
              <input className="input" type="file" accept=".csv" onChange={(e) => setCsvFile(e.target.files?.[0] ?? null)} />
            </div>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              <button className="btn btn-secondary" onClick={() => importPreview()} disabled={!csvFile || previewing}>
                {previewing ? <Spinner size={12} /> : null} Preview
              </button>
              <button className="btn btn-primary" onClick={() => importReal()} disabled={!csvFile || importing}>
                {importing ? <Spinner size={12} /> : null} Importar
              </button>
              <button className="btn btn-secondary" onClick={() => importClientesAdmin()} disabled={!csvFile || importingClientes}>
                {importingClientes ? <Spinner size={12} /> : null} Import admin
              </button>
            </div>
            <div style={{ display: 'flex', gap: 6 }}>
              <button className="btn btn-secondary" onClick={() => connectWhatsapp()} disabled={connectingWhatsapp}>
                {connectingWhatsapp ? <Spinner size={12} /> : null} Conectar WhatsApp
              </button>
              <button className="btn btn-primary" onClick={() => goLive()} disabled={goingLive}>
                {goingLive ? <Spinner size={12} /> : null} Go-live
              </button>
            </div>
            {whatsappError && <ErrorBox message={whatsappError} />}
            {whatsappFeedback && <div style={{ fontSize: 12, color: 'var(--success)' }}>{whatsappFeedback}</div>}
            {whatsappQr && (
              <div style={{ marginTop: 12 }}>
                <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>QR Code — escaneie com o WhatsApp</div>
                <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
                  <img src={whatsappQr} alt="WhatsApp QR" style={{ width: 220, height: 'auto', borderRadius: 8, border: '1px solid var(--surface-border)' }} />
                  <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                    <div>Abra o WhatsApp no seu celular → Configurações → Dispositivos conectados → Escanear código.</div>
                    <button className="btn btn-ghost" onClick={() => setWhatsappQr(null)} style={{ marginTop: 8 }}>Fechar QR</button>
                  </div>
                </div>
              </div>
            )}
            <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
              WhatsApp: {whatsappStatus?.connected ? 'conectado' : `desconectado (${whatsappStatus?.state ?? '—'})`}
            </div>
            {importResult && <div style={{ fontSize: 12, color: 'var(--success)' }}>{importResult}</div>}
          </div>
        </div>
      )}

      {activeTab === 'status' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, maxWidth: 560 }}>
          <div className="surface" style={{ padding: 18 }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>Status geral</div>
            {isLoading ? <Spinner size={14} /> : !status ? (
              <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Dados indisponíveis.</div>
            ) : (
              <>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 10 }}>{statusResumo}</div>
                {status.etapas.map((etapa) => (
                  <div key={etapa.numero} style={{ display: 'flex', gap: 8, marginBottom: 6 }}>
                    <span style={{ fontSize: 12, color: etapa.concluida ? 'var(--success)' : 'var(--text-muted)' }}>{etapa.concluida ? '✓' : '○'}</span>
                    <div>
                      <div style={{ fontSize: 12, color: 'var(--text-primary)' }}>{etapa.nome}</div>
                      <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{etapa.descricao}</div>
                    </div>
                  </div>
                ))}
              </>
            )}
          </div>
        </div>
      )}
    </>
  )
}
