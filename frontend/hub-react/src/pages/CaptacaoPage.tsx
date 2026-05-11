import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Target, Search, Dna, List, Building2, User, Star,
  RefreshCw, Loader2, AlertTriangle, ChevronDown, ChevronUp,
  Phone, CheckCircle, XCircle, Trash2, SlidersHorizontal,
  Sparkles, Shield,
} from 'lucide-react'
import {
  fetchDNA, atualizarDNA, descobrirLeads, fetchPipeline,
  atualizarStatus, deletarLead,
} from '../api/prospeccao'
import type { LeadProspeccaoResponse, LeadStatus, TipoLead } from '../types'

/* ─── Constantes ───────────────────────────────────────────────────────────── */

const TIPOS_ACAO = [
  'Reclamação Trabalhista', 'Horas Extras', 'Rescisão Indireta',
  'Ação de Cobrança', 'Indenização por Danos Morais', 'Ação de Divórcio',
  'Execução de Título Extrajudicial', 'Ação Consumerista',
  'Rescisão Contratual', 'Acidente de Trabalho',
]

const TRIBUNAIS = [
  { value: '', label: 'Todos os tribunais' },
  { value: 'TJSP', label: 'TJSP — São Paulo' },
  { value: 'TJRJ', label: 'TJRJ — Rio de Janeiro' },
  { value: 'TJMG', label: 'TJMG — Minas Gerais' },
  { value: 'TRT2', label: 'TRT2 — São Paulo' },
  { value: 'TRT15', label: 'TRT15 — Campinas' },
  { value: 'STJ', label: 'STJ' },
]

const STATUS_CFG: Record<LeadStatus, { label: string; color: string; bg: string; border: string }> = {
  novo:        { label: 'Novo',        color: '#3A7AB8', bg: 'rgba(58,122,184,0.08)',  border: 'rgba(58,122,184,0.22)'  },
  contatado:   { label: 'Contatado',   color: '#D08010', bg: 'rgba(208,128,16,0.08)',  border: 'rgba(208,128,16,0.22)'  },
  qualificado: { label: 'Qualificado', color: '#1A9E78', bg: 'rgba(26,158,120,0.08)',  border: 'rgba(26,158,120,0.22)'  },
  descartado:  { label: 'Descartado',  color: '#8AAAC0', bg: 'rgba(138,170,192,0.08)', border: 'rgba(138,170,192,0.22)' },
}

function scoreColor(score: number | null) {
  if (score === null) return '#8AAAC0'
  if (score >= 75) return '#1A9E78'
  if (score >= 40) return '#D08010'
  return '#C83030'
}

function ScoreBadge({ score }: { score: number | null }) {
  const color = scoreColor(score)
  return (
    <div className="flex flex-col items-center justify-center w-12 h-12 rounded-xl flex-shrink-0"
      style={{ background: `color-mix(in srgb, ${color} 10%, transparent)`, border: `1px solid color-mix(in srgb, ${color} 25%, transparent)` }}>
      <span className="text-sm font-extrabold leading-none" style={{ color }}>{score ?? '—'}</span>
      <span className="text-[8px] font-bold" style={{ color }}>score</span>
    </div>
  )
}

/* ─── LeadCard ─────────────────────────────────────────────────────────────── */

function LeadCard({ lead, onStatusChange, onDelete }: {
  lead: LeadProspeccaoResponse
  onStatusChange: (id: number, status: LeadStatus, notas?: string) => void
  onDelete: (id: number) => void
}) {
  const [expanded, setExpanded] = useState(false)
  const [nota, setNota]         = useState(lead.notas_advogado ?? '')
  const cfg    = STATUS_CFG[lead.status as LeadStatus] ?? STATUS_CFG.novo
  const isEmp  = lead.tipo_lead === 'empresa'
  const accentLeft = lead.status === 'qualificado' ? '#1A9E78'
    : lead.status === 'descartado' ? 'rgba(138,170,192,0.4)'
    : lead.score_match && lead.score_match >= 75 ? '#1A9E78'
    : lead.score_match && lead.score_match >= 40 ? '#D08010'
    : '#3A7AB8'

  return (
    <div className="bg-white rounded-2xl card-shadow border border-am-border overflow-hidden card-border-hover"
      style={{ borderLeft: `3px solid ${accentLeft}` }}>
      <div className="px-4 sm:px-5 py-4">
        <div className="flex items-start gap-3">
          <ScoreBadge score={lead.score_match} />

          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <div className="flex items-center gap-1.5 min-w-0">
                {isEmp
                  ? <Building2 size={12} className="text-am-blue flex-shrink-0" />
                  : <User size={12} className="text-am-secondary flex-shrink-0" />}
                <span className="text-sm font-bold text-am-ink truncate">{lead.nome}</span>
              </div>
              <span className="text-[9px] font-bold px-1.5 py-0.5 rounded flex-shrink-0"
                style={{ color: cfg.color, background: cfg.bg, border: `1px solid ${cfg.border}` }}>
                {cfg.label}
              </span>
              <span className="text-[9px] font-semibold px-1.5 py-0.5 rounded flex-shrink-0"
                style={{ color: 'var(--color-am-secondary)', background: 'var(--color-am-surface)', border: '1px solid var(--color-am-border)' }}>
                {isEmp ? 'B2B' : 'B2C'}
              </span>
            </div>

            {/* Info rápida */}
            <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-[10px] text-am-muted">
              {isEmp && lead.empresa_setor && <span>Setor: {lead.empresa_setor}</span>}
              {isEmp && lead.empresa_porte  && <span>Porte: {lead.empresa_porte}</span>}
              {isEmp && lead.cnpj           && <span className="font-mono">{lead.cnpj}</span>}
              {!isEmp && lead.tipo_acao_origem && <span>Ação: {lead.tipo_acao_origem}</span>}
              {!isEmp && lead.polo_processo    && <span>Polo: {lead.polo_processo}</span>}
              {!isEmp && lead.numero_cnj_exemplo && (
                <span className="font-mono">{lead.numero_cnj_exemplo}</span>
              )}
              {lead.fonte_descoberta && <span>Via: {lead.fonte_descoberta}</span>}
            </div>

            {/* Motivo da IA */}
            {lead.score_motivo && (
              <p className="mt-2 text-[10px] text-am-secondary leading-relaxed line-clamp-2">
                {lead.score_motivo}
              </p>
            )}
          </div>
        </div>

        {/* Abordagem sugerida */}
        {lead.abordagem_sugerida && (
          <div className="mt-3 px-3 py-2 rounded-xl text-[10px] text-am-secondary leading-relaxed"
            style={{ background: 'rgba(58,122,184,0.05)', border: '1px solid rgba(58,122,184,0.14)' }}>
            <span className="flex items-center gap-1 text-[9px] font-bold text-am-blue mb-1">
              <Sparkles size={9} /> Abordagem sugerida pela IA
            </span>
            {lead.abordagem_sugerida}
          </div>
        )}

        {/* Expandido: sócios + LinkedIn + notas */}
        {expanded && (
          <div className="mt-3 space-y-3 pt-3 border-t border-am-border">
            {isEmp && lead.socios.length > 0 && (
              <div>
                <p className="text-[9px] font-bold text-am-muted uppercase tracking-wider mb-1">Sócios</p>
                {lead.socios.map((s, i) => (
                  <div key={i} className="text-[10px] text-am-secondary">
                    {s.nome} <span className="text-am-muted">· {s.qualificacao}</span>
                  </div>
                ))}
              </div>
            )}
            {isEmp && lead.contatos_linkedin.length > 0 && (
              <div>
                <p className="text-[9px] font-bold text-am-muted uppercase tracking-wider mb-1">LinkedIn</p>
                {lead.contatos_linkedin.map((c, i) => (
                  <div key={i} className="text-[10px] text-am-secondary">
                    {c.nome} <span className="text-am-muted">· {c.cargo}</span>
                  </div>
                ))}
              </div>
            )}
            <div>
              <p className="text-[9px] font-bold text-am-muted uppercase tracking-wider mb-1">Notas</p>
              <textarea rows={2} value={nota} onChange={(e) => setNota(e.target.value)}
                placeholder="Adicione observações sobre este lead…"
                className="w-full px-3 py-2 text-xs border border-am-border rounded-xl bg-am-bg text-am-ink outline-none resize-none transition-fast placeholder:text-am-muted"
                onFocus={(e) => (e.target.style.borderColor = 'var(--color-am-blue)')}
                onBlur={(e) => (e.target.style.borderColor = 'var(--color-am-border)')}
              />
            </div>
          </div>
        )}

        {/* Ações */}
        <div className="mt-3 pt-3 border-t border-am-border flex items-center gap-2 flex-wrap">
          {/* Transições de status */}
          {lead.status !== 'contatado' && lead.status !== 'descartado' && (
            <button onClick={() => onStatusChange(lead.id, 'contatado', nota)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[10px] font-bold press"
              style={{ color: '#D08010', background: 'rgba(208,128,16,0.08)', border: '1px solid rgba(208,128,16,0.2)' }}>
              <Phone size={10} /> Contatado
            </button>
          )}
          {lead.status !== 'qualificado' && lead.status !== 'descartado' && (
            <button onClick={() => onStatusChange(lead.id, 'qualificado', nota)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[10px] font-bold press"
              style={{ color: '#1A9E78', background: 'rgba(26,158,120,0.08)', border: '1px solid rgba(26,158,120,0.2)' }}>
              <CheckCircle size={10} /> Qualificado
            </button>
          )}
          {lead.status !== 'descartado' && (
            <button onClick={() => onStatusChange(lead.id, 'descartado', nota)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[10px] font-bold press"
              style={{ color: '#8AAAC0', background: 'rgba(138,170,192,0.08)', border: '1px solid rgba(138,170,192,0.2)' }}>
              <XCircle size={10} /> Descartar
            </button>
          )}
          {lead.status === 'descartado' && (
            <button onClick={() => onStatusChange(lead.id, 'novo', nota)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[10px] font-bold press"
              style={{ color: '#3A7AB8', background: 'rgba(58,122,184,0.08)', border: '1px solid rgba(58,122,184,0.2)' }}>
              <RefreshCw size={10} /> Reabrir
            </button>
          )}

          <div className="ml-auto flex items-center gap-1.5">
            <button onClick={() => setExpanded((v) => !v)}
              className="flex items-center gap-1 text-[10px] text-am-muted press px-2 py-1.5 rounded-lg"
              style={{ border: '1px solid var(--color-am-border)' }}>
              {expanded ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
              {expanded ? 'Menos' : 'Detalhes'}
            </button>
            <button onClick={() => onDelete(lead.id)}
              className="w-7 h-7 rounded-lg flex items-center justify-center press text-am-muted"
              style={{ border: '1px solid var(--color-am-border)' }}
              onMouseEnter={(e) => { e.currentTarget.style.color = '#C83030'; e.currentTarget.style.borderColor = 'rgba(200,48,48,0.4)' }}
              onMouseLeave={(e) => { e.currentTarget.style.color = ''; e.currentTarget.style.borderColor = 'var(--color-am-border)' }}>
              <Trash2 size={11} />
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

/* ─── Página principal ─────────────────────────────────────────────────────── */

type Tab = 'dna' | 'buscar' | 'pipeline'

export default function CaptacaoPage() {
  const [tab, setTab]               = useState<Tab>('buscar')
  const [tipoAcao, setTipoAcao]     = useState(TIPOS_ACAO[0])
  const [tipoLead, setTipoLead]     = useState<TipoLead | 'auto'>('auto')
  const [tribunal, setTribunal]     = useState('')
  const [limite, setLimite]         = useState(5)
  const [scoreMin, setScoreMin]     = useState(40)
  const [filterStatus, setFilterStatus] = useState<LeadStatus | 'todos'>('todos')
  const [filterTipo, setFilterTipo]     = useState<TipoLead | 'todos'>('todos')

  const qc = useQueryClient()

  const { data: dna, isLoading: dnaLoading } = useQuery({
    queryKey: ['dna'],
    queryFn: fetchDNA,
    retry: 1,
  })

  const { data: pipeline, isLoading: pipelineLoading } = useQuery({
    queryKey: ['pipeline', filterStatus, filterTipo],
    queryFn: () => fetchPipeline({
      status: filterStatus !== 'todos' ? filterStatus : undefined,
      tipo_lead: filterTipo !== 'todos' ? filterTipo : undefined,
    }),
    retry: 1,
  })

  const refreshDNA = useMutation({
    mutationFn: atualizarDNA,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['dna'] }),
  })

  const descobrir = useMutation({
    mutationFn: descobrirLeads,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pipeline'] }),
  })

  const updateStatus = useMutation({
    mutationFn: ({ id, status, notas }: { id: number; status: LeadStatus; notas?: string }) =>
      atualizarStatus(id, { status, notas_advogado: notas }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pipeline'] }),
  })

  const remover = useMutation({
    mutationFn: deletarLead,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pipeline'] }),
  })

  const leads = pipeline?.leads ?? []
  const novos       = leads.filter((l) => l.status === 'novo').length
  const qualificados= leads.filter((l) => l.status === 'qualificado').length
  const scoreMedio  = leads.length
    ? Math.round(leads.reduce((a, l) => a + (l.score_match ?? 0), 0) / leads.length)
    : 0

  const TABS = [
    { id: 'dna'     as Tab, icon: <Dna size={14} />,    label: 'Perfil DNA'        },
    { id: 'buscar'  as Tab, icon: <Search size={14} />,  label: 'Buscar Candidatos' },
    { id: 'pipeline'as Tab, icon: <List size={14} />,    label: `Pipeline (${pipeline?.total ?? 0})` },
  ]

  return (
    <div className="flex flex-col h-full overflow-hidden bg-am-bg">
      <div className="flex flex-col h-full w-full max-w-3xl mx-auto">

        {/* ── Header ── */}
        <div className="flex-shrink-0 px-4 pt-5 pb-4">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 rounded-2xl flex items-center justify-center flex-shrink-0"
              style={{ background: 'linear-gradient(135deg,#1248BE,#4A8ED4)', boxShadow: '0 4px 12px rgba(18,72,190,0.22)' }}>
              <Target size={18} className="text-white" />
            </div>
            <div>
              <h2 className="text-sm font-bold text-am-ink">Captação Inteligente</h2>
              <p className="text-xs text-am-muted mt-0.5">Descubra leads que combinam com o seu escritório</p>
            </div>
          </div>

          {/* Pill switcher */}
          <div className="flex gap-1 p-1 rounded-2xl" style={{ background: 'rgba(12,30,48,0.05)' }}>
            {TABS.map((t) => {
              const active = tab === t.id
              return (
                <motion.button
                  key={t.id}
                  onClick={() => setTab(t.id)}
                  whileHover={{ scale: active ? 1 : 1.04 }}
                  whileTap={{ scale: 0.95 }}
                  transition={{ type: 'spring', stiffness: 380, damping: 22 }}
                  className="relative flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold whitespace-nowrap flex-1 justify-center"
                  style={{ color: active ? 'var(--color-am-blue)' : 'var(--color-am-muted)' }}
                >
                  <AnimatePresence>
                    {active && (
                      <motion.span
                        layoutId="cap-tab-pill"
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
                  <span className="relative">{t.label}</span>
                </motion.button>
              )
            })}
          </div>
        </div>

      <div className="flex-1 overflow-y-auto">
        <div className="px-4 pb-6 space-y-5" key={tab}>

          {/* ── TAB DNA ─────────────────────────────────────────────────────── */}
          {tab === 'dna' && (
            <>
              <div className="flex items-center justify-between flex-wrap gap-3">
                <div>
                  <h3 className="text-sm font-bold text-am-ink">Perfil do Escritório</h3>
                  <p className="text-xs text-am-muted mt-0.5">
                    A IA analisa os seus processos e constrói um perfil para identificar os melhores candidatos
                  </p>
                </div>
                <button onClick={() => refreshDNA.mutate()}
                  disabled={refreshDNA.isPending}
                  className="flex items-center gap-2 px-4 py-2 rounded-xl text-white text-xs font-bold press btn-primary disabled:opacity-50"
                  style={{ background: 'var(--color-am-blue)' }}
                  onMouseEnter={(e) => { if (!refreshDNA.isPending) e.currentTarget.style.background = 'var(--color-am-blue-hover)' }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = 'var(--color-am-blue)' }}>
                  {refreshDNA.isPending
                    ? <><Loader2 size={13} className="animate-spin" /> Gerando…</>
                    : <><RefreshCw size={13} /> Atualizar DNA</>}
                </button>
              </div>

              {dnaLoading ? (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  {[1, 2].map((i) => <div key={i} className="h-40 rounded-2xl skeleton" style={{ background: 'rgba(58,122,184,0.06)' }} />)}
                </div>
              ) : !dna || dna.dados_insuficientes ? (
                <div className="bg-white rounded-2xl card-shadow border border-am-border p-8 flex flex-col items-center gap-3 text-center card-border-hover">
                  <div className="w-12 h-12 rounded-2xl flex items-center justify-center"
                    style={{ background: 'rgba(208,128,16,0.08)', border: '1px solid rgba(208,128,16,0.2)' }}>
                    <Dna size={22} style={{ color: '#D08010' }} />
                  </div>
                  <div>
                    <div className="text-sm font-bold text-am-ink">DNA ainda não gerado</div>
                    <div className="text-xs text-am-muted mt-1 max-w-xs">
                      Clique em <strong>Atualizar DNA</strong> para que a IA analise o histórico de processos do escritório e monte o perfil ideal.
                    </div>
                  </div>
                </div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="bg-white rounded-2xl card-shadow border border-am-border p-5 card-border-hover space-y-4">
                    <div>
                      <p className="text-[9px] font-bold text-am-muted uppercase tracking-wider mb-2">Especialidades</p>
                      <div className="flex flex-wrap gap-1.5">
                        {dna.especialidades.map((e) => (
                          <span key={e} className="text-[10px] font-semibold px-2 py-0.5 rounded-lg"
                            style={{ color: 'var(--color-am-blue)', background: 'rgba(58,122,184,0.08)', border: '1px solid rgba(58,122,184,0.18)' }}>
                            {e}
                          </span>
                        ))}
                      </div>
                    </div>
                    <div>
                      <p className="text-[9px] font-bold text-am-muted uppercase tracking-wider mb-1">Tipo predominante</p>
                      <span className="text-xs font-bold flex items-center gap-1.5"
                        style={{ color: dna.tipo_lead_predominante === 'empresa' ? '#3A7AB8' : '#1A9E78' }}>
                        {dna.tipo_lead_predominante === 'empresa'
                          ? <><Building2 size={12} /> B2B — Empresas</>
                          : dna.tipo_lead_predominante === 'pessoa'
                            ? <><User size={12} /> B2C — Pessoas</>
                            : 'Ambos'}
                      </span>
                    </div>
                    {dna.diferenciais.length > 0 && (
                      <div>
                        <p className="text-[9px] font-bold text-am-muted uppercase tracking-wider mb-2">Diferenciais</p>
                        {dna.diferenciais.map((d) => (
                          <div key={d} className="flex items-start gap-1.5 text-[10px] text-am-secondary mb-1">
                            <Star size={9} className="text-am-amber flex-shrink-0 mt-0.5" /> {d}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  <div className="bg-white rounded-2xl card-shadow border border-am-border p-5 card-border-hover space-y-4">
                    {dna.setores_alvo.length > 0 && (
                      <div>
                        <p className="text-[9px] font-bold text-am-muted uppercase tracking-wider mb-2">Setores-alvo</p>
                        <div className="flex flex-wrap gap-1.5">
                          {dna.setores_alvo.map((s) => (
                            <span key={s} className="text-[10px] font-semibold px-2 py-0.5 rounded-lg"
                              style={{ color: '#1A9E78', background: 'rgba(26,158,120,0.08)', border: '1px solid rgba(26,158,120,0.18)' }}>
                              {s}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                    {dna.perfil_cliente_ideal && (
                      <div>
                        <p className="text-[9px] font-bold text-am-muted uppercase tracking-wider mb-1">Perfil do cliente ideal</p>
                        <p className="text-xs text-am-secondary leading-relaxed">{dna.perfil_cliente_ideal}</p>
                      </div>
                    )}
                    {dna.gerado_em && (
                      <p className="text-[9px] text-am-muted">
                        Gerado em {new Date(dna.gerado_em).toLocaleDateString('pt-BR', { day: '2-digit', month: 'short', year: 'numeric' })}
                      </p>
                    )}
                  </div>
                </div>
              )}
            </>
          )}

          {/* ── TAB BUSCAR ──────────────────────────────────────────────────── */}
          {tab === 'buscar' && (
            <>
              <div>
                <h3 className="text-sm font-bold text-am-ink">Encontrar Candidatos</h3>
                <p className="text-xs text-am-muted mt-0.5">
                  A IA busca litigantes no DataJud (CNJ), analisa cada um e pontua quem mais se encaixa no seu perfil
                </p>
              </div>

              {/* Formulário */}
              <div className="bg-white rounded-2xl card-shadow border border-am-border p-5 card-border-hover">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="sm:col-span-2">
                    <label className="text-[10px] font-bold text-am-secondary uppercase tracking-wider block mb-1.5">
                      Tipo de ação a buscar
                    </label>
                    <select value={tipoAcao} onChange={(e) => setTipoAcao(e.target.value)}
                      className="w-full px-3 py-2.5 text-xs border border-am-border rounded-xl bg-am-bg text-am-ink outline-none">
                      {TIPOS_ACAO.map((t) => <option key={t} value={t}>{t}</option>)}
                    </select>
                  </div>

                  <div>
                    <label className="text-[10px] font-bold text-am-secondary uppercase tracking-wider block mb-1.5">
                      Tipo de lead
                    </label>
                    <div className="flex gap-2">
                      {([
                        { v: 'auto',    label: 'Auto (DNA)' },
                        { v: 'empresa', label: '🏢 Empresa' },
                        { v: 'pessoa',  label: '👤 Pessoa'  },
                      ] as const).map(({ v, label }) => (
                        <button key={v} onClick={() => setTipoLead(v)}
                          className="flex-1 py-2 text-[10px] font-bold rounded-xl press"
                          style={tipoLead === v
                            ? { background: 'var(--color-am-surface)', color: 'var(--color-am-blue)', border: '1px solid var(--color-am-blue)' }
                            : { background: 'var(--color-am-bg)', color: 'var(--color-am-muted)', border: '1px solid var(--color-am-border)' }}>
                          {label}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div>
                    <label className="text-[10px] font-bold text-am-secondary uppercase tracking-wider block mb-1.5">
                      Tribunal
                    </label>
                    <select value={tribunal} onChange={(e) => setTribunal(e.target.value)}
                      className="w-full px-3 py-2.5 text-xs border border-am-border rounded-xl bg-am-bg text-am-ink outline-none">
                      {TRIBUNAIS.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
                    </select>
                  </div>

                  <div>
                    <label className="text-[10px] font-bold text-am-secondary uppercase tracking-wider block mb-1.5">
                      Score mínimo: <span className="font-extrabold" style={{ color: scoreColor(scoreMin) }}>{scoreMin}</span>
                    </label>
                    <input type="range" min={0} max={100} step={5} value={scoreMin}
                      onChange={(e) => setScoreMin(Number(e.target.value))}
                      className="w-full accent-blue-600" />
                    <div className="flex justify-between text-[9px] text-am-muted mt-0.5">
                      <span>0 — qualquer</span><span>75+ mais quente</span><span>100</span>
                    </div>
                  </div>

                  <div>
                    <label className="text-[10px] font-bold text-am-secondary uppercase tracking-wider block mb-1.5">
                      Candidatos a analisar: <span className="font-extrabold text-am-ink">{limite}</span>
                    </label>
                    <input type="range" min={1} max={20} step={1} value={limite}
                      onChange={(e) => setLimite(Number(e.target.value))}
                      className="w-full accent-blue-600" />
                    <div className="flex justify-between text-[9px] text-am-muted mt-0.5">
                      <span>1</span><span>10</span><span>20</span>
                    </div>
                  </div>
                </div>

                <button
                  onClick={() => descobrir.mutate({
                    tipo_acao: tipoAcao,
                    tipo_lead: tipoLead,
                    tribunal: tribunal || null,
                    limite,
                    score_minimo: scoreMin,
                  })}
                  disabled={descobrir.isPending}
                  className="mt-5 w-full py-3 rounded-xl text-white text-sm font-bold press btn-primary disabled:opacity-50 flex items-center justify-center gap-2"
                  style={{ background: 'var(--color-am-blue)' }}
                  onMouseEnter={(e) => { if (!descobrir.isPending) e.currentTarget.style.background = 'var(--color-am-blue-hover)' }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = 'var(--color-am-blue)' }}>
                  {descobrir.isPending
                    ? <><Loader2 size={15} className="animate-spin" /> Buscando e analisando com IA…</>
                    : <><Search size={15} /> Buscar e Qualificar Leads</>}
                </button>
              </div>

              {/* Resultado */}
              {descobrir.isSuccess && descobrir.data && (
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <p className="text-xs font-bold text-am-ink">
                      {descobrir.data.total} candidato{descobrir.data.total !== 1 ? 's' : ''} encontrado{descobrir.data.total !== 1 ? 's' : ''}
                    </p>
                    <button onClick={() => setTab('pipeline')}
                      className="text-xs font-bold text-am-blue press px-3 py-1.5 rounded-lg"
                      style={{ border: '1px solid var(--color-am-border)' }}>
                      Ver pipeline →
                    </button>
                  </div>
                  {descobrir.data.aviso_lgpd && (
                    <div className="flex items-start gap-2 p-3 rounded-xl text-[10px]"
                      style={{ background: 'rgba(208,128,16,0.07)', border: '1px solid rgba(208,128,16,0.25)', color: '#D08010' }}>
                      <Shield size={12} className="flex-shrink-0 mt-0.5" />
                      <span className="leading-relaxed">{descobrir.data.aviso_lgpd}</span>
                    </div>
                  )}
                  {descobrir.data.leads.map((lead) => (
                    <LeadCard key={lead.id} lead={lead}
                      onStatusChange={(id, status, notas) => updateStatus.mutate({ id, status, notas })}
                      onDelete={(id) => remover.mutate(id)} />
                  ))}
                </div>
              )}

              {descobrir.isError && (
                <div className="flex items-center gap-2 p-3 rounded-xl text-xs"
                  style={{ background: 'rgba(200,48,48,0.07)', border: '1px solid rgba(200,48,48,0.2)', color: '#C83030' }}>
                  <AlertTriangle size={12} />
                  Erro ao buscar leads. Verifique se o backend está ativo e o DNA foi gerado.
                </div>
              )}

              {/* Explicação de score */}
              <div className="bg-white rounded-2xl card-shadow border border-am-border p-4 card-border-hover">
                <p className="text-[9px] font-bold text-am-muted uppercase tracking-wider mb-3">Como a pontuação funciona</p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2">
                  {[
                    { label: 'Área jurídica bate com sua especialidade', pts: '+30', tipo: 'empresa' },
                    { label: 'Setor compatível com seu histórico',        pts: '+20', tipo: 'empresa' },
                    { label: 'Empresa com muitos processos ativos',       pts: '+15', tipo: 'empresa' },
                    { label: 'Contato identificado no LinkedIn',          pts: '+15', tipo: 'empresa' },
                    { label: 'Tipo de ação bate com especialidade',       pts: '+35', tipo: 'pessoa'  },
                    { label: 'Polo do processo compatível',               pts: '+25', tipo: 'pessoa'  },
                    { label: 'Processo em fase inicial',                  pts: '+20', tipo: 'pessoa'  },
                    { label: 'Alta recorrência de processos similares',   pts: '+20', tipo: 'pessoa'  },
                  ].map(({ label, pts, tipo }) => (
                    <div key={label} className="flex items-center gap-2 text-[10px] text-am-secondary">
                      <span className="text-[9px] font-bold w-7 text-right flex-shrink-0"
                        style={{ color: tipo === 'empresa' ? '#3A7AB8' : '#1A9E78' }}>{pts}</span>
                      <span className="flex items-center gap-1">
                        {tipo === 'empresa' ? <Building2 size={8} className="text-am-muted flex-shrink-0" /> : <User size={8} className="text-am-muted flex-shrink-0" />}
                        {label}
                      </span>
                    </div>
                  ))}
                </div>
                <div className="mt-3 flex gap-3 text-[10px]">
                  <span className="font-bold" style={{ color: '#1A9E78' }}>75+ quente</span>
                  <span className="font-bold" style={{ color: '#D08010' }}>40–74 morno</span>
                  <span className="font-bold" style={{ color: '#C83030' }}>&lt;40 frio</span>
                </div>
              </div>
            </>
          )}

          {/* ── TAB PIPELINE ────────────────────────────────────────────────── */}
          {tab === 'pipeline' && (
            <>
              {/* KPIs */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {[
                  { label: 'Total leads',   value: pipeline?.total ?? 0, color: 'var(--color-am-blue)'  },
                  { label: 'Novos',         value: novos,                color: 'var(--color-am-blue)'  },
                  { label: 'Qualificados',  value: qualificados,         color: 'var(--color-am-green)' },
                  { label: 'Score médio',   value: scoreMedio,           color: scoreColor(scoreMedio)  },
                ].map(({ label, value, color }) => (
                  <div key={label} className="bg-white rounded-xl card-shadow border border-am-border p-3 card-border-hover">
                    <div className="text-[9px] font-bold text-am-muted uppercase tracking-wider">{label}</div>
                    <div className="text-xl font-extrabold mt-1 leading-none" style={{ color }}>{value}</div>
                  </div>
                ))}
              </div>

              {/* Filtros */}
              <div className="flex items-center gap-2 flex-wrap">
                <SlidersHorizontal size={12} className="text-am-muted flex-shrink-0" />
                <div className="flex gap-1.5 flex-wrap">
                  {(['todos', 'novo', 'contatado', 'qualificado', 'descartado'] as const).map((s) => {
                    const cfg = s !== 'todos' ? STATUS_CFG[s] : null
                    return (
                      <button key={s} onClick={() => setFilterStatus(s)}
                        className="px-2.5 py-1 text-[10px] font-bold rounded-lg press"
                        style={filterStatus === s
                          ? { background: cfg?.bg ?? 'var(--color-am-surface)', color: cfg?.color ?? 'var(--color-am-blue)', border: `1px solid ${cfg?.border ?? 'var(--color-am-border)'}` }
                          : { background: 'transparent', color: 'var(--color-am-muted)', border: '1px solid transparent' }}>
                        {s === 'todos' ? 'Todos' : STATUS_CFG[s].label}
                      </button>
                    )
                  })}
                </div>
                <div className="flex gap-1.5 ml-2">
                  {(['todos', 'empresa', 'pessoa'] as const).map((t) => (
                    <button key={t} onClick={() => setFilterTipo(t)}
                      className="flex items-center gap-1 px-2.5 py-1 text-[10px] font-bold rounded-lg press"
                      style={filterTipo === t
                        ? { background: 'var(--color-am-surface)', color: 'var(--color-am-blue)', border: '1px solid var(--color-am-border)' }
                        : { background: 'transparent', color: 'var(--color-am-muted)', border: '1px solid transparent' }}>
                      {t === 'todos' ? 'Todos' : t === 'empresa' ? <><Building2 size={9} /> B2B</> : <><User size={9} /> B2C</>}
                    </button>
                  ))}
                </div>
              </div>

              {/* LGPD */}
              {pipeline?.aviso_lgpd && (
                <div className="flex items-start gap-2 p-3 rounded-xl text-[10px]"
                  style={{ background: 'rgba(208,128,16,0.07)', border: '1px solid rgba(208,128,16,0.25)', color: '#D08010' }}>
                  <Shield size={12} className="flex-shrink-0 mt-0.5" />
                  <span className="leading-relaxed">{pipeline.aviso_lgpd}</span>
                </div>
              )}

              {/* Lista */}
              {pipelineLoading ? (
                Array.from({ length: 3 }).map((_, i) => (
                  <div key={i} className="h-32 rounded-2xl skeleton" style={{ background: 'rgba(58,122,184,0.06)' }} />
                ))
              ) : leads.length === 0 ? (
                <div className="bg-white rounded-2xl card-shadow border border-am-border p-10 flex flex-col items-center gap-3 text-center card-border-hover">
                  <Target size={28} strokeWidth={1.5} className="text-am-muted" />
                  <div className="text-sm font-bold text-am-ink">Pipeline vazio</div>
                  <div className="text-xs text-am-muted max-w-xs">
                    Use a aba <strong>Buscar Candidatos</strong> para encontrar leads qualificados pela IA
                  </div>
                  <button onClick={() => setTab('buscar')}
                    className="px-4 py-2 rounded-xl text-white text-xs font-bold press btn-primary mt-1"
                    style={{ background: 'var(--color-am-blue)' }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--color-am-blue-hover)')}
                    onMouseLeave={(e) => (e.currentTarget.style.background = 'var(--color-am-blue)')}>
                    Buscar candidatos
                  </button>
                </div>
              ) : (
                <div className="space-y-3">
                  {leads.map((lead) => (
                    <LeadCard key={lead.id} lead={lead}
                      onStatusChange={(id, status, notas) => updateStatus.mutate({ id, status, notas })}
                      onDelete={(id) => remover.mutate(id)} />
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </div>
      </div>
    </div>
  )
}
