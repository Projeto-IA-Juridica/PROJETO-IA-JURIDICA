import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import {
  FileText, BarChart3, MessageSquare, BookOpen,
  ArrowLeft, ArrowRight, Search, Users, Scale, Clock,
  Upload, Download, Trash2, AlertTriangle,
  AlertCircle, UserPlus, X, CheckCircle2, Zap, Star,
} from 'lucide-react'
import ProcessoTab    from '../tabs/ProcessoTab'
import ScoreTab       from '../tabs/ScoreTab'
import ChatTab        from '../tabs/ChatTab'
import DocumentosTab  from '../tabs/DocumentosTab'
import RiskChip       from '../components/RiskChip'
import AprovacaoCard  from '../components/agendamento/AprovacaoCard'
import AgendaSemanal  from '../components/agendamento/AgendaSemanal'
import { fetchClientes, analisarCliente } from '../api/crm'
import { fetchProcessos }  from '../api/processos'
import { exportarCliente, deletarClienteLGPD, criarClienteManual } from '../api/clientes'
import { listarAgendamentos } from '../api/agendamentos'
import CadastroCSVPage from './CadastroCSVPage'
import type { CRMClienteCard, ClientesNavRequest } from '../types'

type Tab  = 'processo' | 'score' | 'chat' | 'documentos'
type View = 'lista' | 'crm' | 'agenda'

const VIEW_LABELS: Record<View, string> = {
  lista: 'Lista',
  crm: 'Relacionamento',
  agenda: 'Agenda',
}

const TABS: { id: Tab; icon: React.ReactNode; label: string }[] = [
  { id: 'processo',   icon: <FileText size={13} />,      label: 'Processo'   },
  { id: 'score',      icon: <BarChart3 size={13} />,     label: 'Score'      },
  { id: 'chat',       icon: <MessageSquare size={13} />, label: 'Assistente' },
  { id: 'documentos', icon: <BookOpen size={13} />,      label: 'Documentos' },
]

const NIVEIS = ['todos', 'excelente', 'satisfeito', 'neutro', 'em_risco', 'critico', 'sem_analise'] as const
type Nivel = typeof NIVEIS[number]

const NIVEL_CFG: Record<string, { color: string; bg: string; border: string; label: string }> = {
  excelente:   { color: '#1A9E78', bg: 'rgba(26,158,120,0.08)',  border: 'rgba(26,158,120,0.22)',  label: 'Excelente'  },
  satisfeito:  { color: '#2E7D32', bg: 'rgba(46,125,50,0.08)',   border: 'rgba(46,125,50,0.22)',   label: 'Satisfeito' },
  neutro:      { color: '#D08010', bg: 'rgba(208,128,16,0.08)',  border: 'rgba(208,128,16,0.22)',  label: 'Neutro'     },
  em_risco:    { color: '#C83030', bg: 'rgba(200,48,48,0.08)',   border: 'rgba(200,48,48,0.22)',   label: 'Atenção'    },
  critico:     { color: '#8B0000', bg: 'rgba(139,0,0,0.08)',     border: 'rgba(139,0,0,0.22)',     label: 'Crítico'    },
  sem_analise: { color: '#8AAAC0', bg: 'rgba(138,170,192,0.08)', border: 'rgba(138,170,192,0.22)', label: 'Sem análise'},
}

function initials(nome: string) {
  return nome.split(' ').slice(0, 2).map(n => n[0].toUpperCase()).join('')
}

function formatDate(iso: string | null) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' })
}

interface Props {
  activeId: number | null
  onSelect: (id: number) => void
  onBack?: () => void
  /** navegação vinda do Painel (agenda/pendentes) */
  navRequest?: ClientesNavRequest | null
  onGoConfig?: () => void
}

export default function HubPage({ activeId, onSelect, onBack, navRequest, onGoConfig }: Props) {
  const [activeTab, setActiveTab]       = useState<Tab>('processo')
  const [search, setSearch]             = useState('')
  const [view, setView]                 = useState<View>('lista')
  const [showCSV, setShowCSV]           = useState(false)
  const [confirmarDelete, setConfirmarDelete] = useState(false)

  // Agendamento Inteligente
  const [showPendentes, setShowPendentes] = useState(false)
  const [agendaSemana, setAgendaSemana]   = useState<string | null>(null)

  // CRM states
  const [nivel, setNivel]               = useState<Nivel>('todos')
  const [analisandoId, setAnalisandoId] = useState<number | null>(null)
  const [erroId, setErroId]             = useState<{ id: number; msg: string } | null>(null)

  // Modal novo cliente
  const [showModal, setShowModal]       = useState(false)
  const [novoNome, setNovoNome]         = useState('')
  const [novoTel, setNovoTel]           = useState('')
  const [novoCnj, setNovoCnj]           = useState('')
  const [novoPolo, setNovoPolo]         = useState<'autor' | 'reu' | 'terceiro'>('autor')
  const [novoErro, setNovoErro]         = useState<string | null>(null)
  const [novoOk, setNovoOk]             = useState<string | null>(null)

  const qc = useQueryClient()

  const exportarMut = useMutation({ mutationFn: () => exportarCliente(activeId!) })

  const deletarMut = useMutation({
    mutationFn: () => deletarClienteLGPD(activeId!),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['clientes'] }); onBack?.() },
    onSettled: () => setConfirmarDelete(false),
  })

  const analisarClienteMut = useMutation({
    mutationFn: (clienteId: number) => analisarCliente(clienteId),
    onMutate:  (clienteId) => { setAnalisandoId(clienteId); setErroId(null) },
    onSuccess: () => { setAnalisandoId(null); qc.invalidateQueries({ queryKey: ['clientes'] }) },
    onError: (e: unknown, clienteId) => {
      setAnalisandoId(null)
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Erro ao analisar'
      setErroId({ id: clienteId, msg })
      setTimeout(() => setErroId(null), 5000)
    },
  })

  const novoClienteMut = useMutation({
    mutationFn: () => criarClienteManual({
      nome: novoNome.trim(),
      telefone_whatsapp: novoTel.trim(),
      numero_cnj: novoCnj.trim() || null,
      polo_cliente: novoPolo,
    }),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['clientes'] })
      setNovoErro(null)
      setNovoOk(`Cliente "${res.nome}" cadastrado com sucesso!${res.processo_id ? ' Processo vinculado e enriquecimento iniciado.' : ''}`)
      setTimeout(() => {
        setShowModal(false); setNovoOk(null)
        setNovoNome(''); setNovoTel(''); setNovoCnj(''); setNovoPolo('autor')
      }, 2200)
    },
    onError: (e: unknown) => {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Erro ao cadastrar cliente'
      setNovoErro(msg)
    },
  })

  const { data: clientes, isLoading, isError } = useQuery({
    queryKey: ['clientes'],
    queryFn: fetchClientes,
    staleTime: 60_000,
  })

  const { data: processoData } = useQuery({
    queryKey: ['processos', activeId],
    queryFn: () => fetchProcessos(activeId!),
    enabled: activeId != null,
  })

  // Aprovações pendentes — polling 10s sincroniza com aprovações via WhatsApp:
  // quando o advogado responde "1" no WhatsApp, o card some no próximo ciclo.
  const { data: pendentes } = useQuery({
    queryKey: ['agendamentos-pendentes'],
    queryFn: () => listarAgendamentos({ status: 'aguardando_advogado' }),
    refetchInterval: 10_000,
    staleTime: 5_000,
  })
  const totalPendentes = pendentes?.length ?? 0

  // Navegação vinda do Painel (widget Próximas reuniões)
  useEffect(() => {
    if (!navRequest) return
    setView(navRequest.view)
    setShowPendentes(!!navRequest.pendentes)
    if (navRequest.semana) setAgendaSemana(navRequest.semana)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [navRequest?.ts])

  function selectClienteComTab(clienteId: number, tab: Tab) {
    setActiveTab(tab)
    onSelect(clienteId)
  }

  const cliente  = clientes?.find((c) => c.id === activeId) ?? null
  const processo = processoData?.items[0] ?? null

  const filtered = (clientes ?? []).filter((c: CRMClienteCard) => {
    const matchSearch = c.nome.toLowerCase().includes(search.toLowerCase())
    if (view === 'crm') {
      const matchNivel = nivel === 'todos' ? true
        : nivel === 'sem_analise' ? !c.crm_nivel
        : c.crm_nivel === nivel
      return matchSearch && matchNivel
    }
    return matchSearch
  })

  const countFor = (n: Nivel) =>
    n === 'todos'        ? (clientes?.length ?? 0)
    : n === 'sem_analise' ? (clientes?.filter(c => !c.crm_nivel).length ?? 0)
    : (clientes?.filter(c => c.crm_nivel === n).length ?? 0)

  /* ── CSV import ── */
  if (showCSV) return <CadastroCSVPage onBack={() => setShowCSV(false)} />

  /* ── Lista / CRM ── */
  if (!cliente) {
    return (
      <div className="flex flex-col h-full overflow-hidden bg-am-bg">
        <div className="flex flex-col h-full w-full max-w-5xl mx-auto">

          {/* Header */}
          <div className="flex-shrink-0 px-6 pt-3 pb-4 space-y-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <h1 className="text-sm font-bold text-am-ink tracking-tight">
                    {view === 'lista' ? 'Clientes' : view === 'crm' ? 'Relacionamento' : 'Agenda'}
                  </h1>
                  {totalPendentes > 0 && (
                    <button
                      onClick={() => { setView('lista'); setShowPendentes(true) }}
                      title={`${totalPendentes} agendamento(s) aguardando aprovação`}
                      className="press flex items-center justify-center text-[10px] font-bold text-white rounded-full"
                      style={{ background: '#C83030', minWidth: 18, height: 18, padding: '0 5px' }}>
                      {totalPendentes}
                    </button>
                  )}
                </div>
                <p className="text-xs text-am-muted mt-0.5">
                  {view === 'lista'
                    ? `${clientes?.length ?? 0} cadastrados`
                    : view === 'crm'
                      ? 'Satisfação baseada no histórico de conversas com a IA'
                      : 'Reuniões confirmadas, aprovações pendentes e prazos da semana'}
                </p>
              </div>

              <div className="flex items-center gap-2 flex-shrink-0">
                <button
                  onClick={() => { setShowModal(true); setNovoErro(null); setNovoOk(null) }}
                  className="press flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-semibold flex-shrink-0"
                  style={{
                    background: 'var(--color-am-surface)',
                    border: '1px solid var(--color-am-border)',
                    color: 'var(--color-am-blue)',
                    fontFamily: 'var(--font-sans)',
                  }}>
                  <UserPlus size={12} /> Novo cliente
                </button>

                {view === 'lista' && (
                  <button
                    onClick={() => setShowCSV(true)}
                    className="press flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-semibold text-white flex-shrink-0"
                    style={{ background: 'linear-gradient(135deg,#1248BE,#3A7AB8)', border: 'none', fontFamily: 'var(--font-sans)' }}>
                    <Upload size={12} /> Importar CSV
                  </button>
                )}

                {/* View toggle */}
                <div className="flex p-1 rounded-xl gap-0.5" style={{ background: 'rgba(12,30,48,0.05)' }}>
                  {(['lista', 'crm', 'agenda'] as const).map(v => (
                    <motion.button
                      key={v}
                      onClick={() => { setView(v); if (v !== 'lista') setShowPendentes(false) }}
                      className="relative px-3 py-1.5 rounded-lg text-[11px] font-semibold"
                      style={{ color: view === v ? 'var(--color-am-blue)' : 'var(--color-am-muted)' }}
                    >
                      <AnimatePresence>
                        {view === v && (
                          <motion.span
                            layoutId="view-pill"
                            className="absolute inset-0 rounded-lg bg-white"
                            style={{ boxShadow: '0 1px 4px rgba(18,72,190,0.12), 0 0 0 1px rgba(18,72,190,0.06)' }}
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            exit={{ opacity: 0 }}
                            transition={{ type: 'spring', stiffness: 400, damping: 28 }}
                          />
                        )}
                      </AnimatePresence>
                      <span className="relative">{VIEW_LABELS[v]}</span>
                    </motion.button>
                  ))}
                </div>
              </div>
            </div>

            {/* CRM level filters */}
            {view === 'crm' && (
              <div className="flex gap-2 flex-wrap" role="group" aria-label="Filtrar por nível de satisfação">
                {NIVEIS.map(n => {
                  const cfg    = n === 'todos' || n === 'sem_analise' ? null : NIVEL_CFG[n]
                  const count  = countFor(n)
                  const active = nivel === n
                  return (
                    <button key={n} onClick={() => setNivel(n)}
                      aria-pressed={active}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold press"
                      style={active
                        ? { background: cfg?.bg ?? 'var(--color-am-surface)', color: cfg?.color ?? 'var(--color-am-blue)', border: `1px solid ${cfg?.border ?? 'var(--color-am-border)'}` }
                        : { background: 'var(--color-am-surface)', color: cfg?.color ?? 'var(--color-am-secondary)', border: '1px solid var(--color-am-border)' }
                      }>
                      {cfg && <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ background: cfg.color }} />}
                      {n === 'todos' ? 'Todos' : n === 'sem_analise' ? 'Sem análise' : NIVEL_CFG[n]?.label ?? n}
                      <span className="ml-1 text-[10px] font-bold opacity-60">{count}</span>
                    </button>
                  )
                })}
              </div>
            )}

            {/* Search — não se aplica à Agenda */}
            {view !== 'agenda' && (
              <div className="relative">
                <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-am-muted pointer-events-none" aria-hidden="true" />
                <label htmlFor="hub-search" className="sr-only">Buscar cliente</label>
                <input
                  id="hub-search"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Buscar cliente..."
                  className="am-input am-input-with-icon"
                />
              </div>
            )}
          </div>

          {/* Content */}
          <div className="flex-1 overflow-y-auto px-6 pb-4">

            {/* ── Vista: Agenda semanal ── */}
            {view === 'agenda' && (
              <AgendaSemanal
                semanaISO={agendaSemana}
                navTs={navRequest?.ts}
                onSelectCliente={(id, tab) => selectClienteComTab(id, tab)}
                onVerPendentes={() => { setView('lista'); setShowPendentes(true) }}
                onGoConfig={() => onGoConfig?.()}
              />
            )}

            {/* ── Cards de aprovação pendente (vista Lista) ── */}
            {view === 'lista' && (pendentes ?? []).length > 0 && (
              <div className="space-y-3 mt-2 mb-4">
                <div className="flex items-center justify-between">
                  <p className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-widest" style={{ color: '#B06D0A' }}>
                    <Clock size={11} /> Aguardando sua aprovação
                  </p>
                  {showPendentes && (
                    <button
                      onClick={() => setShowPendentes(false)}
                      className="press text-[11px] font-semibold"
                      style={{ color: 'var(--color-am-blue)' }}>
                      Mostrar todos os clientes
                    </button>
                  )}
                </div>
                {(pendentes ?? []).map(ag => (
                  <AprovacaoCard key={ag.id} agendamento={ag} />
                ))}
              </div>
            )}

            {view === 'lista' && showPendentes && (pendentes ?? []).length === 0 && (
              <div className="flex flex-col items-center gap-2 py-8">
                <CheckCircle2 size={20} style={{ color: '#1A9E78' }} />
                <p className="text-xs text-am-muted">Nenhuma aprovação pendente. Tudo em dia! 🎉</p>
                <button
                  onClick={() => setShowPendentes(false)}
                  className="press text-[11px] font-semibold"
                  style={{ color: 'var(--color-am-blue)' }}>
                  Mostrar todos os clientes
                </button>
              </div>
            )}

            {/* Empty state — sem clientes */}
            {view !== 'agenda' && !showPendentes && !isLoading && (clientes ?? []).length === 0 && (
              <div className="flex flex-col items-center justify-center gap-4 py-12">
                <div className="w-14 h-14 rounded-2xl flex items-center justify-center"
                  style={{ background: 'rgba(18,72,190,0.07)', border: '1px solid rgba(18,72,190,0.15)' }}>
                  <Users size={22} style={{ color: 'var(--color-am-blue)' }} />
                </div>
                <div className="text-center">
                  <p className="text-sm font-bold text-am-ink mb-1">Nenhum cliente ainda</p>
                  <p className="text-xs text-am-muted leading-relaxed">Importe sua base de clientes via CSV<br/>para começar a usar o amicus.</p>
                </div>
                <button
                  onClick={() => setShowCSV(true)}
                  className="press flex items-center gap-2 px-5 py-2.5 rounded-xl text-xs font-bold text-white"
                  style={{ background: 'linear-gradient(135deg,#1248BE,#3A7AB8)', boxShadow: '0 4px 14px rgba(18,72,190,0.25)', border: 'none', fontFamily: 'var(--font-sans)' }}>
                  <Upload size={13} /> Importar clientes via CSV
                </button>
              </div>
            )}

            {/* ── Vista: Lista ── */}
            {view === 'lista' && !showPendentes && (
              <>
                {isLoading && (
                  <div className="flex items-center justify-center h-32">
                    <div className="w-5 h-5 rounded-full border-2 border-am-blue border-t-transparent animate-spin" />
                  </div>
                )}
                {!isLoading && (clientes ?? []).length > 0 && filtered.length === 0 && (
                  <div className="flex items-center justify-center h-32">
                    <p className="text-xs text-am-muted">Nenhum cliente encontrado</p>
                  </div>
                )}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-2">
                  {filtered.map((c) => {
                    const ini = initials(c.nome)
                    const cfg = c.crm_nivel ? (NIVEL_CFG[c.crm_nivel] ?? null) : null
                    return (
                      <motion.button
                        key={c.id}
                        onClick={() => onSelect(c.id)}
                        whileHover={{ scale: 1.01 }}
                        whileTap={{ scale: 0.98 }}
                        transition={{ type: 'spring', stiffness: 400, damping: 28 }}
                        className="w-full flex items-start gap-3 px-4 py-3.5 rounded-2xl text-left"
                        style={{ background: 'white', border: '1px solid var(--color-am-border)', boxShadow: '0 1px 4px rgba(12,30,48,0.05)' }}
                      >
                        <div className="w-9 h-9 rounded-xl flex items-center justify-center text-xs font-bold text-white flex-shrink-0 mt-0.5"
                          style={{ background: 'linear-gradient(135deg,#1248BE,#4A8ED4)' }}>
                          {ini}
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <p className="text-sm font-semibold text-am-ink truncate">{c.nome}</p>
                            {cfg && (
                              <span className="flex-shrink-0 text-[10px] font-semibold px-1.5 py-0.5 rounded-md"
                                style={{ color: cfg.color, background: cfg.bg, border: `1px solid ${cfg.border}` }}>
                                {cfg.label}
                              </span>
                            )}
                          </div>
                          <div className="flex items-center gap-3 mt-1.5">
                            <span className="flex items-center gap-1 text-[11px] text-am-muted">
                              <Scale size={11} />{c.total_processos} processo{c.total_processos !== 1 ? 's' : ''}
                            </span>
                            {c.ultimo_contato && (
                              <span className="flex items-center gap-1 text-[11px] text-am-muted">
                                <Clock size={11} />
                                {new Date(c.ultimo_contato).toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' })}
                              </span>
                            )}
                            {c.telefone_whatsapp && (
                              <span className="text-[11px] text-am-muted truncate">{c.telefone_whatsapp}</span>
                            )}
                          </div>
                          {c.crm_resumo && (
                            <p className="text-[11px] text-am-muted mt-1.5 leading-relaxed line-clamp-1">{c.crm_resumo}</p>
                          )}
                        </div>
                        <ArrowLeft size={13} className="text-am-muted rotate-180 flex-shrink-0 mt-1" />
                      </motion.button>
                    )
                  })}
                </div>
              </>
            )}

            {/* ── Vista: Relacionamento (CRM) ── */}
            {view === 'crm' && (
              <>
                <div className="bg-white rounded-2xl card-shadow border border-am-border overflow-hidden card-border-hover mt-2">
                  <div className="hidden sm:grid grid-cols-[1fr_auto_auto_auto_auto_auto] gap-4 px-5 py-2.5 bg-am-bg border-b border-am-border">
                    {['Cliente', 'Processos', 'Último contato', 'Score', 'Nível', ''].map(h => (
                      <span key={h} className="text-[9px] font-bold uppercase tracking-widest text-am-muted">{h}</span>
                    ))}
                  </div>

                  {isLoading && Array.from({ length: 5 }).map((_, i) => (
                    <div key={i} className="flex items-center gap-3 px-5 py-4 border-b border-am-border last:border-0">
                      <div className="w-8 h-8 rounded-full flex-shrink-0 skeleton" style={{ background: 'rgba(58,122,184,0.08)' }} />
                      <div className="flex-1 space-y-1.5">
                        <div className="h-3 w-36 rounded skeleton" style={{ background: 'rgba(58,122,184,0.08)' }} />
                        <div className="h-2 w-24 rounded skeleton" style={{ background: 'rgba(58,122,184,0.06)' }} />
                      </div>
                    </div>
                  ))}

                  {isError && (
                    <div className="flex items-center gap-2 m-4 p-3 rounded-xl"
                      style={{ background: 'rgba(200,48,48,0.06)', border: '1px solid rgba(200,48,48,0.2)' }}>
                      <AlertCircle size={13} style={{ color: '#C83030' }} />
                      <span className="text-xs text-am-secondary">Erro ao carregar clientes.</span>
                    </div>
                  )}

                  {!isLoading && !isError && filtered.length === 0 && (clientes ?? []).length > 0 && (
                    <div className="flex flex-col items-center py-12 gap-2 text-am-muted">
                      <Search size={22} strokeWidth={1.5} />
                      <span className="text-xs">Nenhum cliente encontrado</span>
                    </div>
                  )}

                  {filtered.map((c: CRMClienteCard) => {
                    const cfg        = c.crm_nivel ? (NIVEL_CFG[c.crm_nivel] ?? NIVEL_CFG.sem_analise) : NIVEL_CFG.sem_analise
                    const isAnalysing = analisandoId === c.id
                    const hasErro    = erroId?.id === c.id

                    return (
                      <div key={c.id}
                        className="flex items-center gap-3 sm:grid sm:grid-cols-[1fr_auto_auto_auto_auto_auto] sm:gap-4 px-5 border-b border-am-border last:border-0">
                        <button
                          onClick={() => onSelect(c.id)}
                          className="flex items-center gap-3 min-w-0 py-3.5 text-left flex-1 hover:opacity-80 transition-opacity">
                          <div className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0"
                            style={{ background: 'var(--color-am-surface)', color: 'var(--color-am-blue)' }}>
                            {initials(c.nome)}
                          </div>
                          <div className="min-w-0">
                            <div className="text-xs font-semibold text-am-ink truncate">{c.nome}</div>
                            <div className="text-[10px] text-am-muted mt-0.5 sm:hidden">
                              {c.total_processos} proc. · {formatDate(c.ultimo_contato)}
                            </div>
                            {hasErro
                              ? <div className="text-[10px] mt-0.5 truncate max-w-xs hidden sm:block" style={{ color: '#C83030' }}>{erroId.msg}</div>
                              : c.crm_acao_sugerida
                                ? <div className="text-[10px] mt-0.5 truncate max-w-xs hidden sm:block" style={{ color: cfg.color }}>{c.crm_acao_sugerida}</div>
                                : c.crm_resumo
                                  ? <div className="text-[10px] text-am-muted mt-0.5 truncate max-w-xs hidden sm:block">{c.crm_resumo}</div>
                                  : null
                            }
                          </div>
                        </button>

                        <div className="hidden sm:flex items-center gap-1 text-xs text-am-secondary font-medium whitespace-nowrap">
                          <Scale size={10} className="text-am-muted" />{c.total_processos}
                        </div>

                        <div className="hidden sm:flex items-center gap-1 text-[11px] text-am-muted whitespace-nowrap">
                          <Clock size={10} />{formatDate(c.ultimo_contato)}
                        </div>

                        <div className="hidden sm:block text-xs font-bold text-am-ink whitespace-nowrap">
                          {c.crm_score !== null ? `${c.crm_score}` : '—'}
                          {c.nps_medio !== null && (
                            <span className="ml-1 text-[10px] font-medium" style={{ color: '#1A9E78' }}>
                              <Star size={8} className="inline mb-0.5" /> {c.nps_medio}
                            </span>
                          )}
                        </div>

                        <div className="hidden sm:flex items-center justify-end">
                          <span className="text-[9px] font-bold px-1.5 py-0.5 rounded whitespace-nowrap"
                            style={{ color: cfg.color, background: cfg.bg, border: `1px solid ${cfg.border}` }}>
                            {cfg.label}
                          </span>
                        </div>

                        <div className="hidden sm:flex items-center gap-1 flex-shrink-0">
                          <button
                            onClick={e => { e.stopPropagation(); analisarClienteMut.mutate(c.id) }}
                            disabled={isAnalysing || analisarClienteMut.isPending}
                            title="Analisar cliente com IA"
                            className="flex items-center gap-1 px-2 py-1 rounded-lg text-[10px] font-semibold transition-all"
                            style={isAnalysing
                              ? { background: 'rgba(18,72,190,0.08)', color: 'var(--color-am-blue)', border: '1px solid rgba(18,72,190,0.20)', cursor: 'not-allowed' }
                              : { background: 'rgba(18,72,190,0.05)', color: 'var(--color-am-blue)', border: '1px solid rgba(18,72,190,0.15)', cursor: 'pointer' }
                            }>
                            {isAnalysing
                              ? <span className="w-3 h-3 rounded-full border border-am-blue border-t-transparent animate-spin" />
                              : <Zap size={10} />
                            }
                            {isAnalysing ? 'IA...' : 'Analisar'}
                          </button>
                          <ArrowRight size={11} className="text-am-muted" />
                        </div>
                      </div>
                    )
                  })}
                </div>

                {!isLoading && !isError && (
                  <p className="text-[10px] text-am-muted text-right mt-3">
                    {filtered.length} de {clientes?.length ?? 0} clientes
                  </p>
                )}
              </>
            )}
          </div>
        </div>

        {/* Modal — Novo Cliente */}
        {showModal && (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center"
            style={{ background: 'rgba(10,18,35,0.55)', backdropFilter: 'blur(3px)' }}
            onClick={e => { if (e.target === e.currentTarget) setShowModal(false) }}>
            <div
              className="bg-white rounded-2xl shadow-2xl w-full max-w-md mx-4 overflow-hidden"
              style={{ border: '1px solid var(--color-am-border)' }}>

              <div className="flex items-center justify-between px-6 py-4 border-b border-am-border">
                <div className="flex items-center gap-2">
                  <UserPlus size={16} style={{ color: 'var(--color-am-blue)' }} />
                  <span className="text-sm font-bold text-am-ink">Novo cliente</span>
                </div>
                <button onClick={() => setShowModal(false)} className="press p-1 rounded-lg hover:bg-am-surface transition-colors">
                  <X size={14} className="text-am-muted" />
                </button>
              </div>

              <div className="px-6 py-5 space-y-4">
                {novoOk && (
                  <div className="flex items-center gap-2 px-3 py-2.5 rounded-xl text-xs font-medium"
                    style={{ background: 'rgba(26,158,120,0.07)', border: '1px solid rgba(26,158,120,0.22)', color: '#1A9E78' }}>
                    <CheckCircle2 size={13} /> {novoOk}
                  </div>
                )}
                {novoErro && (
                  <div className="flex items-center gap-2 px-3 py-2.5 rounded-xl text-xs font-medium"
                    style={{ background: 'rgba(200,48,48,0.07)', border: '1px solid rgba(200,48,48,0.20)', color: '#C83030' }}>
                    <AlertCircle size={13} /> {novoErro}
                  </div>
                )}

                <div>
                  <label className="block text-[11px] font-semibold text-am-secondary mb-1">
                    Nome <span style={{ color: '#C83030' }}>*</span>
                  </label>
                  <input type="text" value={novoNome} onChange={e => setNovoNome(e.target.value)}
                    placeholder="Ex: João da Silva" className="am-input w-full" disabled={novoClienteMut.isPending} />
                </div>

                <div>
                  <label className="block text-[11px] font-semibold text-am-secondary mb-1">
                    Telefone WhatsApp <span style={{ color: '#C83030' }}>*</span>
                  </label>
                  <input type="tel" value={novoTel} onChange={e => setNovoTel(e.target.value)}
                    placeholder="(11) 99999-9999" className="am-input w-full" disabled={novoClienteMut.isPending} />
                  <p className="text-[10px] text-am-muted mt-1">Aceita qualquer formato: (11) 99999-9999, 11999999999, +5511999999999</p>
                </div>

                <div>
                  <label className="block text-[11px] font-semibold text-am-secondary mb-1">
                    Número do processo <span className="font-normal text-am-muted">(opcional)</span>
                  </label>
                  <input type="text" value={novoCnj} onChange={e => setNovoCnj(e.target.value)}
                    placeholder="0000000-00.0000.0.00.0000" className="am-input w-full" disabled={novoClienteMut.isPending} />
                </div>

                {novoCnj.trim() && (
                  <div>
                    <label className="block text-[11px] font-semibold text-am-secondary mb-1.5">Polo do cliente</label>
                    <div className="flex gap-2">
                      {(['autor', 'reu', 'terceiro'] as const).map(p => (
                        <button key={p} type="button" onClick={() => setNovoPolo(p)} disabled={novoClienteMut.isPending}
                          className="flex-1 py-1.5 rounded-lg text-[11px] font-semibold press transition-all"
                          style={novoPolo === p
                            ? { background: 'rgba(18,72,190,0.10)', color: 'var(--color-am-blue)', border: '1px solid rgba(18,72,190,0.30)' }
                            : { background: 'var(--color-am-surface)', color: 'var(--color-am-secondary)', border: '1px solid var(--color-am-border)' }
                          }>
                          {p === 'reu' ? 'Réu' : p.charAt(0).toUpperCase() + p.slice(1)}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              <div className="flex gap-2 px-6 pb-5">
                <button type="button" onClick={() => setShowModal(false)} disabled={novoClienteMut.isPending}
                  className="flex-1 py-2 rounded-xl text-xs font-semibold press"
                  style={{ background: 'var(--color-am-surface)', color: 'var(--color-am-secondary)', border: '1px solid var(--color-am-border)' }}>
                  Cancelar
                </button>
                <button type="button" onClick={() => novoClienteMut.mutate()}
                  disabled={novoClienteMut.isPending || !novoNome.trim() || !novoTel.trim()}
                  className="flex-1 py-2 rounded-xl text-xs font-semibold text-white press"
                  style={{
                    background: 'linear-gradient(135deg,#1248BE,#3A7AB8)',
                    opacity: (novoClienteMut.isPending || !novoNome.trim() || !novoTel.trim()) ? 0.5 : 1,
                    cursor:  (novoClienteMut.isPending || !novoNome.trim() || !novoTel.trim()) ? 'not-allowed' : 'pointer',
                  }}>
                  {novoClienteMut.isPending
                    ? <span className="flex items-center justify-center gap-1.5">
                        <span className="w-3 h-3 rounded-full border-2 border-white border-t-transparent animate-spin" /> Cadastrando...
                      </span>
                    : 'Cadastrar cliente'
                  }
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    )
  }

  /* ── Detalhe do cliente ── */
  const ini = initials(cliente.nome)

  return (
    <div className="flex flex-col h-full overflow-hidden bg-am-bg">
      <div className="flex flex-col h-full w-full max-w-5xl mx-auto">

        {/* Header */}
        <div className="flex-shrink-0 px-6 pt-5 pb-4">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-3 min-w-0">
              <button onClick={onBack}
                aria-label="Voltar para lista de clientes"
                className="flex-shrink-0 w-8 h-8 rounded-xl flex items-center justify-center text-am-muted hover:text-am-ink transition-colors"
                style={{ border: '1px solid var(--color-am-border)', background: 'white' }}>
                <ArrowLeft size={14} />
              </button>
              <div className="w-10 h-10 rounded-2xl flex items-center justify-center text-sm font-bold text-white flex-shrink-0"
                style={{ background: 'linear-gradient(135deg,#1248BE,#4A8ED4)', boxShadow: '0 4px 12px rgba(18,72,190,0.22)' }}>
                {ini}
              </div>
              <div className="min-w-0">
                <h1 className="text-sm font-bold text-am-ink truncate">{cliente.nome}</h1>
                <p className="text-[11px] text-am-muted mt-0.5 font-mono truncate">
                  {processo?.numero_cnj ?? 'Sem processo vinculado'}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2 flex-shrink-0">
              {processo?.polo_cliente && (
                <span className="text-[10px] font-semibold px-2 py-1 rounded-lg"
                  style={processo.polo_cliente === 'autor'
                    ? { color: '#1A9E78', background: 'rgba(26,158,120,0.08)', border: '1px solid rgba(26,158,120,0.20)' }
                    : { color: '#C83030', background: 'rgba(200,48,48,0.08)',  border: '1px solid rgba(200,48,48,0.20)' }
                  }>
                  {processo.polo_cliente === 'autor' ? 'Autor' : 'Réu'}
                </span>
              )}
              {processo?.score_risco != null && (
                <RiskChip nivel={processo.score_nivel} score={processo.score_risco} size="md" />
              )}
            </div>
          </div>

          {/* LGPD */}
          <div className="flex items-center justify-end gap-2 mt-3">
            {confirmarDelete ? (
              <>
                <span className="flex items-center gap-1 text-[10px] text-am-muted font-medium">
                  <AlertTriangle size={11} style={{ color: '#C83030' }} />
                  Confirmar exclusão dos dados?
                </span>
                <button onClick={() => deletarMut.mutate()} disabled={deletarMut.isPending}
                  className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-[10px] font-bold press"
                  style={{ background: 'rgba(200,48,48,0.10)', color: '#C83030', border: '1px solid rgba(200,48,48,0.25)', cursor: 'pointer' }}>
                  {deletarMut.isPending
                    ? <span className="w-3 h-3 rounded-full border border-current border-t-transparent animate-spin" />
                    : 'Confirmar'}
                </button>
                <button onClick={() => setConfirmarDelete(false)} disabled={deletarMut.isPending}
                  className="px-2.5 py-1 rounded-lg text-[10px] font-semibold press"
                  style={{ background: 'var(--color-am-surface)', color: 'var(--color-am-secondary)', border: '1px solid var(--color-am-border)', cursor: 'pointer' }}>
                  Cancelar
                </button>
              </>
            ) : (
              <>
                <button onClick={() => exportarMut.mutate()} disabled={exportarMut.isPending}
                  title="Exportar dados pessoais (LGPD Art. 18, V)"
                  className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-[10px] font-semibold press"
                  style={{ background: 'rgba(18,72,190,0.06)', color: 'var(--color-am-blue)', border: '1px solid rgba(18,72,190,0.18)', cursor: 'pointer' }}>
                  {exportarMut.isPending
                    ? <span className="w-3 h-3 rounded-full border border-current border-t-transparent animate-spin" />
                    : <Download size={10} />}
                  Exportar dados
                </button>
                <button onClick={() => setConfirmarDelete(true)}
                  title="Direito ao esquecimento (LGPD Art. 18, IV)"
                  className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-[10px] font-semibold press"
                  style={{ background: 'rgba(200,48,48,0.06)', color: '#C83030', border: '1px solid rgba(200,48,48,0.18)', cursor: 'pointer' }}>
                  <Trash2 size={10} /> Apagar dados
                </button>
              </>
            )}
          </div>

          {/* Tab switcher */}
          <div role="tablist" aria-label="Seções do cliente" className="flex gap-1 p-1 rounded-2xl mt-4" style={{ background: 'rgba(12,30,48,0.05)' }}>
            {TABS.map((t) => {
              const disabled = t.id === 'score' && !processo?.score_risco
              const active   = activeTab === t.id
              return (
                <motion.button
                  key={t.id}
                  role="tab"
                  aria-selected={active}
                  disabled={disabled}
                  onClick={() => !disabled && setActiveTab(t.id)}
                  whileHover={{ scale: active || disabled ? 1 : 1.04 }}
                  whileTap={{ scale: disabled ? 1 : 0.95 }}
                  transition={{ type: 'spring', stiffness: 380, damping: 22 }}
                  className="relative flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold whitespace-nowrap flex-1 justify-center"
                  style={{
                    color:   active ? 'var(--color-am-blue)' : 'var(--color-am-muted)',
                    opacity: disabled ? 0.4 : 1,
                    cursor:  disabled ? 'not-allowed' : 'pointer',
                  }}
                >
                  <AnimatePresence>
                    {active && (
                      <motion.span
                        layoutId="hub-tab-pill"
                        className="absolute inset-0 rounded-xl"
                        style={{ background: 'white', boxShadow: '0 1px 6px rgba(18,72,190,0.12), 0 0 0 1px rgba(18,72,190,0.08)' }}
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        transition={{ type: 'spring', stiffness: 400, damping: 28 }}
                      />
                    )}
                  </AnimatePresence>
                  <span className="relative">{t.icon}</span>
                  <span className="relative hidden sm:inline">{t.label}</span>
                </motion.button>
              )
            })}
          </div>
        </div>

        {/* Conteúdo */}
        <div className={`flex-1 overflow-hidden px-4 pb-4 ${activeTab === 'chat' ? 'flex flex-col' : 'overflow-y-auto'}`}>
          {activeTab === 'processo'   && <ProcessoTab   cliente={cliente} />}
          {activeTab === 'score'      && <ScoreTab      cliente={cliente} />}
          {activeTab === 'chat'       && <ChatTab       cliente={cliente} />}
          {activeTab === 'documentos' && <DocumentosTab cliente={cliente} />}
        </div>

      </div>
    </div>
  )
}
