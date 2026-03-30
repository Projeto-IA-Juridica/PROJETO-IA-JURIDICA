import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { adminImportApi, onboardingApi, type ConnectWhatsappResponse, type EvolutionQrPayload } from '../api'
import { Spinner, ErrorBox } from '../components/ui'

type Tab = 'persona' | 'templates' | 'onboarding' | 'status'

export default function SettingsPage() {
  const qc = useQueryClient()
  const [activeTab, setActiveTab] = useState<Tab>('persona')

  const { data: status, isLoading, error } = useQuery({
    queryKey: ['onboarding-status'],
    queryFn: onboardingApi.status,
  })

  const [persona, setPersona] = useState({ persona_nome: '', persona_tom: 'formal', horario_inicio: '08:00', horario_fim: '18:00' })
  const [templates, setTemplates] = useState({ template_boas_vindas: '', template_atualizacao: '', template_sem_novidade: '' })
  const [csvFile, setCsvFile] = useState<File | null>(null)
  const [saved, setSaved] = useState('')
  const [importResult, setImportResult] = useState<string>('')
  const [waConnectData, setWaConnectData] = useState<ConnectWhatsappResponse | null>(null)
  const [waInfo, setWaInfo] = useState('')

  const qrImageSrc = useMemo(() => {
    const qr = waConnectData?.qr_code
    if (!qr) return null

    if (typeof qr === 'string') {
      const clean = qr.trim()
      if (!clean) return null
      if (clean.startsWith('data:image')) return clean
      return `data:image/png;base64,${clean}`
    }

    const payload = qr as EvolutionQrPayload
    const candidate = [payload.base64, payload.qrcode, payload.code]
      .find((value) => typeof value === 'string' && value.trim().length > 0)

    if (!candidate) return null
    if (candidate.startsWith('data:image')) return candidate
    return `data:image/png;base64,${candidate}`
  }, [waConnectData])

  useEffect(() => {
    const esc = status?.escritorio
    if (!esc) return
    setPersona((prev) => {
      if (prev.persona_nome) return prev
      return {
        ...prev,
        persona_nome: esc.persona_nome ?? '',
        persona_tom: esc.persona_tom ?? 'formal',
      }
    })
  }, [status])

  const { mutate: savePersona, isPending: savingPersona, error: personaError } = useMutation({
    mutationFn: () => onboardingApi.configurarIA(persona),
    onSuccess: () => {
      setSaved('persona')
      qc.invalidateQueries({ queryKey: ['onboarding-status'] })
      window.setTimeout(() => setSaved(''), 2000)
    },
  })

  const { mutate: saveTemplates, isPending: savingTemplates, error: templatesError } = useMutation({
    mutationFn: () => onboardingApi.configurarTemplates(templates),
    onSuccess: () => {
      setSaved('templates')
      qc.invalidateQueries({ queryKey: ['onboarding-status'] })
      window.setTimeout(() => setSaved(''), 2000)
    },
  })

  const { mutate: importPreview, isPending: previewing } = useMutation({
    mutationFn: () => onboardingApi.importProcessos(csvFile!, true),
    onSuccess: (res: Record<string, unknown>) => {
      const total = Number(res.importados ?? 0) + Number(res.atualizados ?? 0)
      setImportResult(`Preview concluido: ${total} linha(s) validada(s).`)
    },
  })

  const { mutate: importReal, isPending: importing } = useMutation({
    mutationFn: () => onboardingApi.importProcessos(csvFile!, false),
    onSuccess: (res: Record<string, unknown>) => {
      const importados = Number(res.importados ?? 0)
      const atualizados = Number(res.atualizados ?? 0)
      setImportResult(`Importacao concluida: ${importados} novo(s), ${atualizados} atualizado(s).`)
      qc.invalidateQueries({ queryKey: ['onboarding-status'] })
    },
  })

  const { mutate: importClientesAdmin, isPending: importingClientes } = useMutation({
    mutationFn: () => adminImportApi.importarClientes(csvFile!, false),
    onSuccess: (res) => {
      setImportResult(`Clientes importados: ${res.importados}. Processos novos: ${res.processos_novos}.`)
      qc.invalidateQueries({ queryKey: ['onboarding-status'] })
    },
  })

  const { mutate: connectWhatsapp, isPending: connectingWhatsapp } = useMutation({
    mutationFn: onboardingApi.connectWhatsapp,
    onSuccess: (res) => {
      setWaConnectData(res)
      setWaInfo(`Instancia ${res.instance_name} criada/reconectada. Estado atual: ${res.status}.`)
      qc.invalidateQueries({ queryKey: ['onboarding-status'] })
      qc.invalidateQueries({ queryKey: ['whatsapp-status'] })
    },
    onError: () => {
      setWaInfo('Falha ao conectar na Evolution API.')
    },
  })

  const { data: whatsappStatus, refetch: refetchWhatsappStatus } = useQuery({
    queryKey: ['whatsapp-status'],
    queryFn: onboardingApi.whatsappStatus,
    refetchInterval: (query) => {
      const data = query.state.data
      if (activeTab !== 'onboarding') return 30_000
      if (!data?.connected) return 5_000
      return 20_000
    },
  })

  const { mutate: goLive, isPending: goingLive } = useMutation({
    mutationFn: onboardingApi.goLive,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['onboarding-status'] })
      setImportResult('Go-live executado com sucesso.')
    },
  })

  const statusResumo = useMemo(() => {
    if (!status) return 'Carregando status...'
    if (status.onboarding_completo) return 'Escritorio operacional'
    return `${status.percentual_completo}% concluido`
  }, [status])

  if (isLoading) return <Spinner />
  if (error) return <ErrorBox message="Falha ao carregar configuracoes do escritorio." />

  const esc = status?.escritorio

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">Configuracoes</h1>
        <p className="page-subtitle">Onboarding, persona da IA e operacao do escritorio</p>
      </div>

      <div style={{ borderBottom: '1px solid var(--surface-border)', marginBottom: 24, display: 'flex' }}>
        <button className={`tab ${activeTab === 'persona' ? 'active' : ''}`} onClick={() => setActiveTab('persona')}>Persona IA</button>
        <button className={`tab ${activeTab === 'templates' ? 'active' : ''}`} onClick={() => setActiveTab('templates')}>Templates</button>
        <button className={`tab ${activeTab === 'onboarding' ? 'active' : ''}`} onClick={() => setActiveTab('onboarding')}>Onboarding</button>
        <button className={`tab ${activeTab === 'status' ? 'active' : ''}`} onClick={() => setActiveTab('status')}>Status</button>
      </div>

      {activeTab === 'persona' && (
        <div className="surface" style={{ padding: 24, maxWidth: 620 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 16 }}>Configurar persona da IA</div>
          {personaError && <div style={{ marginBottom: 12 }}><ErrorBox message="Falha ao salvar persona." /></div>}
          {saved === 'persona' && <div style={{ marginBottom: 12, color: 'var(--success)', fontSize: 13 }}>Persona salva com sucesso.</div>}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div>
              <label className="label">Nome da IA</label>
              <input className="input" value={persona.persona_nome} onChange={(e) => setPersona((p) => ({ ...p, persona_nome: e.target.value }))} />
            </div>
            <div>
              <label className="label">Tom de voz</label>
              <select className="input" value={persona.persona_tom} onChange={(e) => setPersona((p) => ({ ...p, persona_tom: e.target.value }))}>
                <option value="formal">Formal</option>
                <option value="amigavel">Amigavel</option>
                <option value="neutro">Neutro</option>
              </select>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <div>
                <label className="label">Horario inicio</label>
                <input className="input" type="time" value={persona.horario_inicio} onChange={(e) => setPersona((p) => ({ ...p, horario_inicio: e.target.value }))} />
              </div>
              <div>
                <label className="label">Horario fim</label>
                <input className="input" type="time" value={persona.horario_fim} onChange={(e) => setPersona((p) => ({ ...p, horario_fim: e.target.value }))} />
              </div>
            </div>
            <button className="btn btn-primary" onClick={() => savePersona()} disabled={savingPersona || !persona.persona_nome.trim()}>
              {savingPersona ? <Spinner size={12} /> : null} Salvar persona
            </button>
          </div>
        </div>
      )}

      {activeTab === 'templates' && (
        <div className="surface" style={{ padding: 24, maxWidth: 620 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 16 }}>Templates de mensagem</div>
          {templatesError && <div style={{ marginBottom: 12 }}><ErrorBox message="Falha ao salvar templates." /></div>}
          {saved === 'templates' && <div style={{ marginBottom: 12, color: 'var(--success)', fontSize: 13 }}>Templates salvos com sucesso.</div>}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div>
              <label className="label">Boas-vindas</label>
              <textarea className="input" rows={3} value={templates.template_boas_vindas} onChange={(e) => setTemplates((t) => ({ ...t, template_boas_vindas: e.target.value }))} />
            </div>
            <div>
              <label className="label">Atualizacao</label>
              <textarea className="input" rows={3} value={templates.template_atualizacao} onChange={(e) => setTemplates((t) => ({ ...t, template_atualizacao: e.target.value }))} />
            </div>
            <div>
              <label className="label">Sem novidade</label>
              <textarea className="input" rows={3} value={templates.template_sem_novidade} onChange={(e) => setTemplates((t) => ({ ...t, template_sem_novidade: e.target.value }))} />
            </div>
            <button className="btn btn-primary" onClick={() => saveTemplates()} disabled={savingTemplates}>
              {savingTemplates ? <Spinner size={12} /> : null} Salvar templates
            </button>
          </div>
        </div>
      )}

      {activeTab === 'onboarding' && (
        <div className="surface" style={{ padding: 24, maxWidth: 780 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14 }}>Executar etapas reais do onboarding</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div>
              <label className="label">CSV para importacao</label>
              <input className="input" type="file" accept=".csv" onChange={(e) => setCsvFile(e.target.files?.[0] ?? null)} />
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <button className="btn btn-secondary" onClick={() => importPreview()} disabled={!csvFile || previewing}>
                {previewing ? <Spinner size={12} /> : null} Preview onboarding
              </button>
              <button className="btn btn-primary" onClick={() => importReal()} disabled={!csvFile || importing}>
                {importing ? <Spinner size={12} /> : null} Importar onboarding
              </button>
              <button className="btn btn-secondary" onClick={() => importClientesAdmin()} disabled={!csvFile || importingClientes}>
                {importingClientes ? <Spinner size={12} /> : null} Importacao admin/clientes
              </button>
            </div>

            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <button className="btn btn-secondary" onClick={() => connectWhatsapp()} disabled={connectingWhatsapp}>
                {connectingWhatsapp ? <Spinner size={12} /> : null} Conectar WhatsApp
              </button>
              <button className="btn btn-secondary" onClick={() => refetchWhatsappStatus()}>
                Atualizar status WhatsApp
              </button>
              <button className="btn btn-primary" onClick={() => goLive()} disabled={goingLive}>
                {goingLive ? <Spinner size={12} /> : null} Executar go-live
              </button>
            </div>

            <div className="surface-overlay" style={{ padding: 14 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', marginBottom: 10 }}>
                <div style={{ fontSize: 12, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Evolution API</div>
                <span className={`badge ${whatsappStatus?.connected ? 'badge-success' : 'badge-warning'}`}>
                  {whatsappStatus?.connected ? 'Conectado' : `Aguardando (${whatsappStatus?.state ?? 'indefinido'})`}
                </span>
              </div>

              {waConnectData?.instance_name ? (
                <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 10 }}>
                  Instancia: <strong style={{ color: 'var(--text-primary)' }}>{waConnectData.instance_name}</strong>
                </div>
              ) : null}

              {qrImageSrc && !whatsappStatus?.connected ? (
                <div style={{ display: 'grid', placeItems: 'center', gap: 8 }}>
                  <img
                    src={qrImageSrc}
                    alt="QR Code WhatsApp"
                    style={{ width: 220, height: 220, background: '#fff', padding: 8, borderRadius: 10, border: '1px solid var(--surface-border)' }}
                  />
                  <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                    Abra o WhatsApp no celular e escaneie o QR Code.
                  </div>
                </div>
              ) : null}

              {!qrImageSrc && !whatsappStatus?.connected ? (
                <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                  Clique em "Conectar WhatsApp" para gerar um novo QR Code pela Evolution API.
                </div>
              ) : null}

              {whatsappStatus?.connected ? (
                <div style={{ fontSize: 12, color: 'var(--success)' }}>
                  WhatsApp conectado com sucesso. Pode seguir para o go-live.
                </div>
              ) : null}
            </div>

            {waInfo && (
              <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                {waInfo}
              </div>
            )}

            <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
              Estado atual: {whatsappStatus?.state ?? 'indefinido'}
            </div>
            {importResult && <div style={{ fontSize: 12, color: 'var(--success)' }}>{importResult}</div>}
          </div>
        </div>
      )}

      {activeTab === 'status' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, maxWidth: 620 }}>
          <div className="surface" style={{ padding: 20 }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 10 }}>Status geral</div>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 12 }}>{statusResumo}</div>
            {status?.etapas.map((etapa) => (
              <div key={etapa.numero} style={{ display: 'flex', gap: 10, marginBottom: 8 }}>
                <span>{etapa.concluida ? 'OK' : '...'}</span>
                <div>
                  <div style={{ fontSize: 13, color: 'var(--text-primary)' }}>{etapa.nome}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{etapa.descricao}</div>
                </div>
              </div>
            ))}
          </div>

          <div className="surface" style={{ padding: 20 }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 10 }}>Dados do escritorio</div>
            {esc ? (
              <div style={{ display: 'grid', gap: 6, fontSize: 12 }}>
                <div>Nome: <strong style={{ color: 'var(--text-primary)' }}>{esc.nome}</strong></div>
                <div>Persona: <strong style={{ color: 'var(--text-primary)' }}>{esc.persona_nome ?? 'nao definida'}</strong></div>
                <div>Tom: <strong style={{ color: 'var(--text-primary)' }}>{esc.persona_tom ?? 'nao definido'}</strong></div>
                <div>WhatsApp: <strong style={{ color: esc.whatsapp_conectado ? 'var(--success)' : 'var(--warning)' }}>{esc.whatsapp_conectado ? 'conectado' : 'desconectado'}</strong></div>
              </div>
            ) : null}
          </div>
        </div>
      )}
    </>
  )
}
