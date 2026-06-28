import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Scale, Clock, AlertCircle, MessageCircle, Phone, Star, Gavel, User,
  ChevronDown, ChevronUp, Plus, Trash2, Edit2, X, Check, Search, RefreshCw, WifiOff,
} from 'lucide-react'
import { fetchProcessos, criarProcesso, deletarProcesso, atualizarProcesso, enriquecerProcesso, type ProcessoCreate, type ProcessoUpdate, type ProcessoFilters } from '../api/processos'
import type { CRMClienteCard, Processo } from '../types'
import Skeleton from '../components/Skeleton'
import RiskChip from '../components/RiskChip'

/* ── Helpers de layout ── */
function Field({ label, value, mono = false }: { label: string; value?: string | null; mono?: boolean }) {
  return (
    <div>
      <p className="text-[10px] font-bold uppercase tracking-wider text-am-muted mb-0.5">{label}</p>
      {value
        ? <p className={`text-xs font-semibold text-am-ink leading-snug ${mono ? 'font-mono' : ''}`}>{value}</p>
        : <p className="text-xs text-am-muted">—</p>
      }
    </div>
  )
}

function Card({ children, accentColor }: { children: React.ReactNode; accentColor?: string }) {
  return (
    <div className="bg-white rounded-2xl overflow-hidden"
      style={{
        border: '1px solid var(--color-am-border)',
        borderLeft: accentColor ? `3px solid ${accentColor}` : '1px solid var(--color-am-border)',
        boxShadow: '0 1px 4px rgba(12,30,48,0.05)',
      }}>
      {children}
    </div>
  )
}

function CardHeader({ icon, title, badge }: { icon: React.ReactNode; title: string; badge?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between px-4 py-3"
      style={{ borderBottom: '1px solid var(--color-am-border)', background: 'rgba(12,30,48,0.02)' }}>
      <div className="flex items-center gap-2">
        <span className="text-am-blue">{icon}</span>
        <span className="text-[10px] font-bold uppercase tracking-wider text-am-secondary">{title}</span>
      </div>
      {badge}
    </div>
  )
}

/* ── Modal de novo processo ── */
function NovoProcessoModal({ clienteId, onClose }: { clienteId: number; onClose: () => void }) {
  const qc = useQueryClient()
  const [cnj,   setCnj]   = useState('')
  const [polo,  setPolo]  = useState<'autor' | 'reu' | 'terceiro'>('autor')
  const [acao,  setAcao]  = useState('')
  const [erro,  setErro]  = useState('')

  const mut = useMutation({
    mutationFn: (payload: ProcessoCreate) => criarProcesso(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['processos', clienteId] })
      onClose()
    },
    onError: (e: unknown) => {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setErro(msg ?? 'Erro ao cadastrar processo.')
    },
  })

  function handleSubmit() {
    if (!cnj.trim()) { setErro('Informe o número CNJ.'); return }
    setErro('')
    mut.mutate({ numero_cnj: cnj.trim(), cliente_id: clienteId, polo_cliente: polo, tipo_acao: acao.trim() || undefined })
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-4"
      style={{ background: 'rgba(12,30,48,0.45)', backdropFilter: 'blur(4px)' }}>
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 20 }}
        className="w-full max-w-md bg-white rounded-3xl p-6"
        style={{ boxShadow: '0 24px 64px rgba(12,30,48,0.18)' }}>
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-sm font-bold text-am-ink">Cadastrar processo</h2>
          <button onClick={onClose} className="w-7 h-7 rounded-lg flex items-center justify-center text-am-muted hover:text-am-ink transition-colors"
            style={{ border: '1px solid var(--color-am-border)' }}>
            <X size={13} />
          </button>
        </div>

        <div className="space-y-3 mb-4">
          <div>
            <label className="block text-[10px] font-bold uppercase tracking-wider text-am-secondary mb-1.5">Nº do processo (CNJ) *</label>
            <input value={cnj} onChange={e => setCnj(e.target.value)} placeholder="0000001-23.2024.8.26.0100" className="am-input" />
          </div>

          <div>
            <label className="block text-[10px] font-bold uppercase tracking-wider text-am-secondary mb-1.5">Polo do cliente</label>
            <div className="flex gap-2">
              {(['autor', 'reu', 'terceiro'] as const).map(p => (
                <button key={p} type="button" onClick={() => setPolo(p)}
                  className="flex-1 py-2 rounded-xl text-xs font-semibold transition-all capitalize"
                  style={polo === p
                    ? { background: 'rgba(18,72,190,0.08)', border: '1.5px solid var(--color-am-blue)', color: 'var(--color-am-blue)' }
                    : { background: 'transparent', border: '1px solid var(--color-am-border)', color: 'var(--color-am-secondary)' }
                  }>
                  {p === 'reu' ? 'Réu' : p.charAt(0).toUpperCase() + p.slice(1)}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-[10px] font-bold uppercase tracking-wider text-am-secondary mb-1.5">Tipo de ação (opcional)</label>
            <input value={acao} onChange={e => setAcao(e.target.value)} placeholder="Ex: Ação de Indenização" className="am-input" />
          </div>
        </div>

        {erro && (
          <p className="text-xs mb-3 flex items-center gap-1.5" style={{ color: '#C83030' }}>
            <AlertCircle size={12} /> {erro}
          </p>
        )}

        <button onClick={handleSubmit} disabled={mut.isPending}
          className="press w-full py-2.5 rounded-xl text-xs font-bold text-white flex items-center justify-center gap-2"
          style={{ background: 'linear-gradient(135deg,#1248BE,#3A7AB8)', border: 'none', cursor: mut.isPending ? 'not-allowed' : 'pointer', fontFamily: 'var(--font-sans)', opacity: mut.isPending ? 0.6 : 1 }}>
          {mut.isPending
            ? <><span className="w-4 h-4 rounded-full border-2 border-white border-t-transparent animate-spin" /> Cadastrando...</>
            : <><Check size={13} /> Cadastrar processo</>
          }
        </button>
      </motion.div>
    </div>
  )
}

/* ── Modal de edição ── */
function EditarProcessoModal({ processo, clienteId, onClose }: { processo: Processo; clienteId: number; onClose: () => void }) {
  const qc = useQueryClient()
  const [polo,  setPolo]  = useState<'autor' | 'reu' | 'terceiro'>(processo.polo_cliente as 'autor' | 'reu' | 'terceiro')
  const [acao,  setAcao]  = useState(processo.tipo_acao ?? '')
  const [monit, setMonit] = useState(true)

  const mut = useMutation({
    mutationFn: (payload: ProcessoUpdate) => atualizarProcesso(processo.id, payload),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['processos', clienteId] }); onClose() },
  })

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-4"
      style={{ background: 'rgba(12,30,48,0.45)', backdropFilter: 'blur(4px)' }}>
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 20 }}
        className="w-full max-w-md bg-white rounded-3xl p-6"
        style={{ boxShadow: '0 24px 64px rgba(12,30,48,0.18)' }}>
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-sm font-bold text-am-ink">Editar processo</h2>
          <button onClick={onClose} className="w-7 h-7 rounded-lg flex items-center justify-center text-am-muted hover:text-am-ink transition-colors"
            style={{ border: '1px solid var(--color-am-border)' }}>
            <X size={13} />
          </button>
        </div>
        <p className="text-[11px] text-am-muted font-mono mb-4">{processo.numero_cnj}</p>

        <div className="space-y-3 mb-4">
          <div>
            <label className="block text-[10px] font-bold uppercase tracking-wider text-am-secondary mb-1.5">Polo do cliente</label>
            <div className="flex gap-2">
              {(['autor', 'reu', 'terceiro'] as const).map(p => (
                <button key={p} type="button" onClick={() => setPolo(p)}
                  className="flex-1 py-2 rounded-xl text-xs font-semibold transition-all capitalize"
                  style={polo === p
                    ? { background: 'rgba(18,72,190,0.08)', border: '1.5px solid var(--color-am-blue)', color: 'var(--color-am-blue)' }
                    : { background: 'transparent', border: '1px solid var(--color-am-border)', color: 'var(--color-am-secondary)' }
                  }>
                  {p === 'reu' ? 'Réu' : p.charAt(0).toUpperCase() + p.slice(1)}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-[10px] font-bold uppercase tracking-wider text-am-secondary mb-1.5">Tipo de ação</label>
            <input value={acao} onChange={e => setAcao(e.target.value)} placeholder="Ex: Ação de Indenização" className="am-input" />
          </div>

          <label className="flex items-center gap-3 cursor-pointer">
            <div className="relative">
              <input type="checkbox" checked={monit} onChange={e => setMonit(e.target.checked)} className="sr-only" />
              <div className="w-9 h-5 rounded-full transition-colors" style={{ background: monit ? 'var(--color-am-blue)' : 'rgba(12,30,48,0.15)' }} />
              <div className="absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full transition-transform shadow-sm"
                style={{ transform: monit ? 'translateX(16px)' : 'translateX(0)' }} />
            </div>
            <span className="text-xs font-medium text-am-secondary">Monitoramento ativo</span>
          </label>
        </div>

        <button onClick={() => mut.mutate({ polo_cliente: polo, tipo_acao: acao.trim() || undefined, monitoramento_ativo: monit })}
          disabled={mut.isPending}
          className="press w-full py-2.5 rounded-xl text-xs font-bold text-white flex items-center justify-center gap-2"
          style={{ background: 'linear-gradient(135deg,#1248BE,#3A7AB8)', border: 'none', cursor: mut.isPending ? 'not-allowed' : 'pointer', fontFamily: 'var(--font-sans)', opacity: mut.isPending ? 0.6 : 1 }}>
          {mut.isPending
            ? <><span className="w-4 h-4 rounded-full border-2 border-white border-t-transparent animate-spin" /> Salvando...</>
            : <><Check size={13} /> Salvar alterações</>
          }
        </button>
      </motion.div>
    </div>
  )
}

const SCORE_NIVEIS = ['baixo', 'moderado', 'alto', 'critico'] as const
const SCORE_LABELS: Record<string, { label: string; color: string; bg: string; border: string }> = {
  baixo:    { label: 'Baixo',    color: '#1A9E78', bg: 'rgba(26,158,120,0.08)',  border: 'rgba(26,158,120,0.22)'  },
  moderado: { label: 'Moderado', color: '#D08010', bg: 'rgba(208,128,16,0.08)',  border: 'rgba(208,128,16,0.22)'  },
  alto:     { label: 'Alto',     color: '#C83030', bg: 'rgba(200,48,48,0.08)',   border: 'rgba(200,48,48,0.22)'   },
  critico:  { label: 'Crítico',  color: '#C83030', bg: 'rgba(200,48,48,0.08)',   border: 'rgba(200,48,48,0.22)'   },
}

/* ── ProcessoTab principal ── */
export default function ProcessoTab({ cliente }: { cliente: CRMClienteCard }) {
  const qc = useQueryClient()
  const [andamentosAbertos, setAndamentosAbertos] = useState<Set<number>>(new Set())
  const [showNovoModal,  setShowNovoModal]  = useState(false)
  const [editandoProc,   setEditandoProc]   = useState<Processo | null>(null)
  const [enrichErros, setEnrichErros]       = useState<Record<number, string>>({})

  // Filtros
  const [filtroStatus, setFiltroStatus] = useState<'ativo' | 'arquivado' | ''>('')
  const [filtroCNJ,    setFiltroCNJ]    = useState('')
  const [filtroScore,  setFiltroScore]  = useState<ProcessoFilters['score_nivel'] | ''>('')

  const searchParam = filtroCNJ.length >= 3 ? filtroCNJ : undefined

  const { data, isLoading } = useQuery({
    queryKey: ['processos', cliente.id, filtroStatus, searchParam, filtroScore],
    queryFn: () => fetchProcessos(cliente.id, {
      status:      filtroStatus  || undefined,
      search:      searchParam,
      score_nivel: filtroScore   || undefined,
    }),
  })
  const processos: Processo[] = data?.items ?? []

  const deleteMut = useMutation({
    mutationFn: deletarProcesso,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['processos', cliente.id] }),
  })

  const enriquecerMut = useMutation({
    mutationFn: enriquecerProcesso,
    onSuccess: (_data, processoId) => {
      setEnrichErros(prev => { const n = { ...prev }; delete n[processoId]; return n })
      qc.invalidateQueries({ queryKey: ['processos', cliente.id] })
    },
    onError: (e: unknown, processoId) => {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        ?? 'Erro ao consultar DataJud'
      setEnrichErros(prev => ({ ...prev, [processoId]: msg }))
    },
  })

  function toggleAndamentos(id: number) {
    setAndamentosAbertos(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  const temFiltroAtivo = filtroStatus !== '' || filtroScore !== '' || filtroCNJ.length >= 3

  return (
    <div className="space-y-3 p-4">

      {/* ── Recomendação de relacionamento ── */}
      {cliente.crm_acao_sugerida && (
        <motion.div
          initial={{ opacity: 0, y: -6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.22 }}
          className="flex items-start gap-3 px-4 py-3.5 rounded-2xl"
          style={{ background: 'rgba(18,72,190,0.05)', border: '1.5px solid rgba(18,72,190,0.18)', borderLeft: '4px solid var(--color-am-blue)' }}
        >
          <MessageCircle size={16} style={{ color: 'var(--color-am-blue)' }} className="flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-[10px] font-bold uppercase tracking-wider mb-1" style={{ color: 'var(--color-am-blue)' }}>Recomendação para o advogado</p>
            <p className="text-sm font-medium text-am-ink leading-snug">{cliente.crm_acao_sugerida}</p>
          </div>
        </motion.div>
      )}

      {/* Card do cliente */}
      <Card>
        <CardHeader icon={<User size={13} />} title="Cliente"
          badge={<span className="text-[10px] font-semibold px-2 py-0.5 rounded-lg" style={{ color: '#1A9E78', background: 'rgba(26,158,120,0.08)', border: '1px solid rgba(26,158,120,0.18)' }}>Ativo</span>}
        />
        <div className="px-4 py-4 space-y-4">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-wider text-am-muted mb-0.5">Nome completo</p>
            <p className="text-sm font-bold text-am-ink">{cliente.nome}</p>
          </div>
          <div className="grid grid-cols-2 gap-x-6 gap-y-3">
            <div>
              <p className="text-[10px] font-bold uppercase tracking-wider text-am-muted mb-0.5">Telefone</p>
              <p className="flex items-center gap-1.5 text-xs font-semibold text-am-ink font-mono">
                <Phone size={10} className="text-am-muted" />{cliente.telefone_whatsapp ?? '—'}
              </p>
            </div>
            {cliente.nps_medio != null && (
              <div>
                <p className="text-[10px] font-bold uppercase tracking-wider text-am-muted mb-0.5">NPS</p>
                <p className="flex items-center gap-1.5 text-xs font-bold text-am-ink">
                  <Star size={10} style={{ color: '#D08010' }} />{cliente.nps_medio.toFixed(1)}
                </p>
              </div>
            )}
            <div>
              <p className="text-[10px] font-bold uppercase tracking-wider text-am-muted mb-0.5">Processos</p>
              <p className="text-xs font-semibold text-am-ink">{cliente.total_processos}</p>
            </div>
            {cliente.ultimo_contato && (
              <div>
                <p className="text-[10px] font-bold uppercase tracking-wider text-am-muted mb-0.5">Último contato</p>
                <p className="text-xs font-semibold text-am-ink">
                  {new Date(cliente.ultimo_contato).toLocaleDateString('pt-BR', { day: '2-digit', month: 'short', year: 'numeric' })}
                </p>
              </div>
            )}
            {cliente.crm_nivel && (
              <div>
                <p className="text-[10px] font-bold uppercase tracking-wider text-am-muted mb-0.5">Risco CRM</p>
                <RiskChip nivel={cliente.crm_nivel} size="sm" />
              </div>
            )}
          </div>
          {cliente.crm_resumo && (
            <p className="text-xs text-am-secondary leading-relaxed pt-3" style={{ borderTop: '1px solid var(--color-am-border)' }}>
              {cliente.crm_resumo}
            </p>
          )}
        </div>
      </Card>

      {/* ── Filtros de processos ── */}
      <div className="space-y-2">
        {/* Busca por CNJ */}
        <div className="relative">
          <Search size={12} className="absolute left-3 top-1/2 -translate-y-1/2 text-am-muted pointer-events-none" />
          <input
            value={filtroCNJ}
            onChange={e => setFiltroCNJ(e.target.value)}
            placeholder="Buscar por CNJ (mín. 3 caracteres)…"
            className="am-input am-input-with-icon"
          />
        </div>

        {/* Status + Score */}
        <div className="flex flex-wrap gap-1.5">
          {/* Status */}
          {(['', 'ativo', 'arquivado'] as const).map(s => (
            <button key={s} onClick={() => setFiltroStatus(s)}
              className="px-2.5 py-1 rounded-lg text-[10px] font-semibold press"
              style={filtroStatus === s
                ? { background: 'rgba(18,72,190,0.10)', color: 'var(--color-am-blue)', border: '1.5px solid rgba(18,72,190,0.28)' }
                : { background: 'var(--color-am-surface)', color: 'var(--color-am-secondary)', border: '1px solid var(--color-am-border)' }
              }>
              {s === '' ? 'Todos' : s === 'ativo' ? 'Ativos' : 'Arquivados'}
            </button>
          ))}

          <span className="w-px bg-am-border mx-0.5" />

          {/* Score */}
          {SCORE_NIVEIS.map(n => {
            const cfg = SCORE_LABELS[n]
            const ativo = filtroScore === n
            return (
              <button key={n} onClick={() => setFiltroScore(ativo ? '' : n)}
                className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-[10px] font-semibold press"
                style={ativo
                  ? { background: cfg.bg, color: cfg.color, border: `1.5px solid ${cfg.border}` }
                  : { background: 'var(--color-am-surface)', color: 'var(--color-am-secondary)', border: '1px solid var(--color-am-border)' }
                }>
                <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ background: ativo ? cfg.color : 'var(--color-am-border)' }} />
                {cfg.label}
              </button>
            )
          })}
        </div>
      </div>

      {/* Skeleton */}
      {isLoading && (
        <div className="space-y-2 px-1">
          <Skeleton className="h-4 w-1/3" />
          <Skeleton className="h-3 w-2/3" />
          <Skeleton className="h-3 w-1/2" />
        </div>
      )}

      {/* Lista de processos */}
      {!isLoading && processos.map(processo => {
        const poloCor = processo.polo_cliente === 'autor' ? '#1A9E78' : '#C83030'
        const andamentosAberto = andamentosAbertos.has(processo.id)
        return (
          <div key={processo.id} className="space-y-0">
            <Card accentColor={poloCor}>
              <CardHeader icon={<Gavel size={13} />} title="Processo Judicial"
                badge={
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] font-semibold px-2 py-0.5 rounded-lg"
                      style={processo.polo_cliente === 'autor'
                        ? { color: '#1A9E78', background: 'rgba(26,158,120,0.08)', border: '1px solid rgba(26,158,120,0.18)' }
                        : { color: '#C83030', background: 'rgba(200,48,48,0.08)',  border: '1px solid rgba(200,48,48,0.18)' }}>
                      {processo.polo_cliente === 'autor' ? 'Autor' : processo.polo_cliente === 'reu' ? 'Réu' : 'Terceiro'}
                    </span>
                    <button
                      onClick={() => enriquecerMut.mutate(processo.id)}
                      disabled={enriquecerMut.isPending && enriquecerMut.variables === processo.id}
                      className="w-6 h-6 rounded-lg flex items-center justify-center text-am-muted hover:text-am-blue transition-colors"
                      title="Atualizar dados do processo no DataJud">
                      <RefreshCw size={11} className={enriquecerMut.isPending && enriquecerMut.variables === processo.id ? 'animate-spin' : ''} />
                    </button>
                    <button onClick={() => setEditandoProc(processo)}
                      className="w-6 h-6 rounded-lg flex items-center justify-center text-am-muted hover:text-am-blue transition-colors"
                      title="Editar">
                      <Edit2 size={11} />
                    </button>
                    <button onClick={() => { if (confirm('Arquivar este processo?')) deleteMut.mutate(processo.id) }}
                      disabled={deleteMut.isPending}
                      className="w-6 h-6 rounded-lg flex items-center justify-center text-am-muted hover:text-red-500 transition-colors"
                      title="Arquivar">
                      <Trash2 size={11} />
                    </button>
                  </div>
                }
              />
              <div className="px-4 py-4 space-y-4">

                {/* Erro de enriquecimento */}
                {enrichErros[processo.id] && (
                  <div className="flex items-start gap-2 px-3 py-2.5 rounded-xl text-xs"
                    style={{ background: 'rgba(200,48,48,0.07)', border: '1px solid rgba(200,48,48,0.22)', color: '#C83030' }}>
                    <WifiOff size={13} className="flex-shrink-0 mt-0.5" />
                    <span>{enrichErros[processo.id]}</span>
                  </div>
                )}

                {/* Aviso: dados ainda não carregados */}
                {!processo.tribunal && !enrichErros[processo.id] && (
                  <div className="flex items-center gap-2 px-3 py-2 rounded-xl text-xs"
                    style={{ background: 'rgba(208,128,16,0.07)', border: '1px solid rgba(208,128,16,0.22)', color: '#D08010' }}>
                    <AlertCircle size={12} className="flex-shrink-0" />
                    <span>Dados do processo ainda não carregados. Clique em ↻ para buscar no DataJud.</span>
                  </div>
                )}

                <div>
                  <p className="text-[10px] font-bold uppercase tracking-wider text-am-muted mb-0.5">Número CNJ</p>
                  <p className="text-xs font-bold font-mono text-am-blue">{processo.numero_cnj}</p>
                </div>
                <div className="grid grid-cols-2 gap-x-6 gap-y-3">
                  <Field label="Tribunal"     value={processo.tribunal}  />
                  <Field label="Vara"         value={processo.vara}      />
                  <Field label="Comarca"      value={processo.comarca}   />
                  <Field label="Tipo de ação" value={processo.tipo_acao} />
                  <Field label="Status"       value={processo.status}    />
                  {processo.data_distribuicao && (
                    <Field label="Ajuizamento" value={new Date(processo.data_distribuicao).toLocaleDateString('pt-BR')} />
                  )}
                  {processo.valor_causa && (
                    <div>
                      <p className="text-[10px] font-bold uppercase tracking-wider text-am-muted mb-0.5">Valor da causa</p>
                      <p className="text-xs font-bold text-am-ink">
                        R$ {Number(processo.valor_causa).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                      </p>
                    </div>
                  )}
                </div>
                {processo.ultimo_andamento && (
                  <div className="pt-3" style={{ borderTop: '1px solid var(--color-am-border)' }}>
                    <p className="text-[10px] font-bold uppercase tracking-wider text-am-muted mb-1">Último andamento</p>
                    <p className="text-xs text-am-secondary leading-relaxed">{processo.ultimo_andamento}</p>
                    {processo.data_ultimo_andamento && (
                      <p className="text-[10px] text-am-muted mt-1 flex items-center gap-1">
                        <Clock size={9} />
                        {new Date(processo.data_ultimo_andamento).toLocaleDateString('pt-BR', { day: '2-digit', month: 'long', year: 'numeric' })}
                      </p>
                    )}
                  </div>
                )}
                {processo.score_risco != null && (
                  <div className="flex items-center gap-3 pt-3" style={{ borderTop: '1px solid var(--color-am-border)' }}>
                    <RiskChip nivel={processo.score_nivel} score={processo.score_risco} size="md" />
                    {processo.score_interpretacao && (
                      <p className="text-xs text-am-secondary leading-relaxed flex-1">{processo.score_interpretacao}</p>
                    )}
                  </div>
                )}
              </div>
            </Card>

            {/* Andamentos por processo */}
            {processo.andamentos && processo.andamentos.length > 0 && (
              <Card accentColor="var(--color-am-blue)">
                <button
                  onClick={() => toggleAndamentos(processo.id)}
                  className="w-full flex items-center justify-between px-4 py-3 hover:bg-black/[0.02] transition-colors"
                  style={{ borderBottom: andamentosAberto ? '1px solid var(--color-am-border)' : 'none' }}>
                  <div className="flex items-center gap-2">
                    <span className="text-am-blue"><Clock size={13} /></span>
                    <span className="text-[10px] font-bold uppercase tracking-wider text-am-secondary">
                      Andamentos · {processo.andamentos.length}
                    </span>
                  </div>
                  {andamentosAberto ? <ChevronUp size={14} className="text-am-muted" /> : <ChevronDown size={14} className="text-am-muted" />}
                </button>
                {andamentosAberto && (
                  <ol className="px-4 py-4 space-y-0">
                    {processo.andamentos.map((a, i) => (
                      <li key={i} className="flex gap-3 pb-4 last:pb-0">
                        <div className="flex flex-col items-center flex-shrink-0">
                          <div className="w-2 h-2 rounded-full mt-1 flex-shrink-0"
                            style={{ background: i === 0 ? 'var(--color-am-blue)' : 'var(--color-am-border)', boxShadow: i === 0 ? '0 0 0 3px rgba(18,72,190,0.12)' : 'none' }} />
                          {i < processo.andamentos.length - 1 && <div className="w-px flex-1 mt-1.5 bg-am-border" />}
                        </div>
                        <div className="pb-1 min-w-0">
                          {a.data && (
                            <time className="text-[10px] font-bold text-am-muted block mb-0.5">
                              {new Date(a.data).toLocaleDateString('pt-BR', { day: '2-digit', month: 'short', year: 'numeric' })}
                            </time>
                          )}
                          <p className={`text-xs leading-relaxed ${i === 0 ? 'font-semibold text-am-ink' : 'text-am-secondary'}`}>
                            {a.descricao}
                          </p>
                        </div>
                      </li>
                    ))}
                  </ol>
                )}
              </Card>
            )}
          </div>
        )
      })}

      {/* Empty state */}
      {!isLoading && processos.length === 0 && (
        <div className="flex flex-col items-center justify-center py-10 gap-4 text-center">
          <div className="w-11 h-11 rounded-2xl flex items-center justify-center"
            style={{ background: 'rgba(12,30,48,0.04)', border: '1px solid var(--color-am-border)' }}>
            <Scale size={20} strokeWidth={1.5} className="text-am-blue" />
          </div>
          <div>
            {temFiltroAtivo
              ? <>
                  <p className="text-sm font-bold text-am-ink">Nenhum processo encontrado</p>
                  <p className="text-xs text-am-muted mt-1">Tente ajustar os filtros.</p>
                </>
              : <>
                  <p className="text-sm font-bold text-am-ink">Sem processo vinculado</p>
                  <p className="text-xs text-am-muted mt-1 max-w-xs leading-relaxed">
                    Cadastre um processo judicial para monitorar andamentos automaticamente.
                  </p>
                </>
            }
          </div>
          {!temFiltroAtivo && (
            <button onClick={() => setShowNovoModal(true)}
              className="press flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold text-white"
              style={{ background: 'linear-gradient(135deg,#1248BE,#3A7AB8)', border: 'none', cursor: 'pointer', fontFamily: 'var(--font-sans)' }}>
              <Plus size={13} /> Cadastrar processo
            </button>
          )}
        </div>
      )}

      {/* Botão adicionar processo */}
      {!isLoading && processos.length > 0 && (
        <button onClick={() => setShowNovoModal(true)}
          className="w-full flex items-center justify-center gap-2 py-2.5 rounded-2xl text-xs font-semibold text-am-secondary transition-colors hover:text-am-ink"
          style={{ border: '1px dashed var(--color-am-border)', background: 'transparent', cursor: 'pointer' }}>
          <Plus size={12} /> Adicionar outro processo
        </button>
      )}

      {/* Modais */}
      <AnimatePresence>
        {showNovoModal && <NovoProcessoModal clienteId={cliente.id} onClose={() => setShowNovoModal(false)} />}
        {editandoProc  && <EditarProcessoModal processo={editandoProc} clienteId={cliente.id} onClose={() => setEditandoProc(null)} />}
      </AnimatePresence>
    </div>
  )
}
