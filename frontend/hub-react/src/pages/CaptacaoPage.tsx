import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Target, Search, Dna, List, Building2, User, Star,
  RefreshCw, Loader2, AlertTriangle, ChevronDown, ChevronUp,
  Phone, CheckCircle, XCircle, Trash2, Sparkles,
} from 'lucide-react'
import {
  fetchDNA, atualizarDNA, descobrirLeads, fetchPipeline,
  atualizarStatus, deletarLead,
} from '../api/prospeccao'
import type { LeadProspeccaoResponse, LeadStatus, TipoLead } from '../types'

/* ─── Constantes ─────────────────────────────────────────────────────────── */

const TIPOS_ACAO = [
  'Reclamação Trabalhista', 'Horas Extras', 'Rescisão Indireta',
  'Ação de Cobrança', 'Indenização por Danos Morais', 'Ação de Divórcio',
  'Execução de Título Extrajudicial', 'Ação Consumerista',
  'Rescisão Contratual', 'Acidente de Trabalho',
]

const TRIBUNAIS = [
  { value: '', label: 'Todos os tribunais' },
  { value: 'TJSP',  label: 'TJSP — São Paulo'    },
  { value: 'TJRJ',  label: 'TJRJ — Rio de Janeiro'},
  { value: 'TJMG',  label: 'TJMG — Minas Gerais' },
  { value: 'TRT2',  label: 'TRT2 — São Paulo'     },
  { value: 'TRT15', label: 'TRT15 — Campinas'     },
  { value: 'STJ',   label: 'STJ'                  },
]

const STATUS_CFG: Record<LeadStatus, { label: string; color: string; bg: string }> = {
  novo:        { label: 'Novo',        color: '#3A7AB8', bg: 'rgba(58,122,184,0.10)'  },
  contatado:   { label: 'Contatado',   color: '#D08010', bg: 'rgba(208,128,16,0.10)'  },
  qualificado: { label: 'Qualificado', color: '#1A9E78', bg: 'rgba(26,158,120,0.10)'  },
  descartado:  { label: 'Descartado',  color: '#8AAAC0', bg: 'rgba(138,170,192,0.10)' },
}

function scoreColor(score: number | null) {
  if (score === null) return '#8AAAC0'
  if (score >= 75) return '#1A9E78'
  if (score >= 40) return '#D08010'
  return '#C83030'
}

/* ─── LeadCard ─────────────────────────────────────────────────────────── */

function LeadCard({ lead, onStatusChange, onDelete }: {
  lead: LeadProspeccaoResponse
  onStatusChange: (id: number, status: LeadStatus, notas?: string) => void
  onDelete: (id: number) => void
}) {
  const [expanded, setExpanded] = useState(false)
  const [nota, setNota]         = useState(lead.notas_advogado ?? '')

  const cfg     = STATUS_CFG[lead.status as LeadStatus] ?? STATUS_CFG.novo
  const isEmp   = lead.tipo_lead === 'empresa'
  const score   = lead.score_match
  const sColor  = scoreColor(score)

  const accentColor =
    lead.status === 'qualificado' ? '#1A9E78' :
    lead.status === 'descartado'  ? '#C8D8E8' :
    score && score >= 75          ? '#1A9E78' :
    score && score >= 40          ? '#D08010' : '#3A7AB8'

  return (
    <div className="bg-white rounded-2xl overflow-hidden"
      style={{
        border: '1px solid var(--color-am-border)',
        borderLeft: `3px solid ${accentColor}`,
        boxShadow: '0 1px 6px rgba(12,30,48,0.05)',
      }}>

      <div className="px-4 py-3.5">
        {/* Linha principal: nome + score + status */}
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-lg flex items-center justify-center flex-shrink-0"
            style={{ background: isEmp ? 'rgba(58,122,184,0.10)' : 'rgba(26,158,120,0.10)' }}>
            {isEmp
              ? <Building2 size={11} style={{ color: '#3A7AB8' }} />
              : <User      size={11} style={{ color: '#1A9E78' }} />}
          </div>

          <p className="flex-1 text-sm font-bold text-am-ink truncate">{lead.nome}</p>

          {/* Score */}
          {score !== null && (
            <span className="text-[10px] font-extrabold px-1.5 py-0.5 rounded-md flex-shrink-0"
              style={{ color: sColor, background: `${sColor}14` }}>
              {score}
            </span>
          )}

          {/* Status */}
          <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full flex-shrink-0"
            style={{ color: cfg.color, background: cfg.bg }}>
            {cfg.label}
          </span>
        </div>

        {/* Linha de detalhes */}
        <div className="mt-1.5 flex flex-wrap gap-x-2.5 gap-y-0.5 text-[10px] text-am-muted pl-8">
          {isEmp && lead.empresa_setor && <span>{lead.empresa_setor}</span>}
          {isEmp && lead.empresa_porte  && <span>· {lead.empresa_porte}</span>}
          {!isEmp && lead.tipo_acao_origem && <span>{lead.tipo_acao_origem}</span>}
          {!isEmp && lead.polo_processo    && <span>· Polo {lead.polo_processo}</span>}
          {lead.fonte_descoberta && <span>· {lead.fonte_descoberta}</span>}
        </div>

        {/* Abordagem sugerida */}
        {lead.abordagem_sugerida && (
          <div className="mt-2.5 pl-8 flex items-start gap-1.5">
            <Sparkles size={9} className="flex-shrink-0 mt-0.5" style={{ color: '#3A7AB8' }} />
            <p className="text-[10px] text-am-secondary leading-relaxed line-clamp-2">
              {lead.abordagem_sugerida}
            </p>
          </div>
        )}

        {/* Notas expandidas */}
        <AnimatePresence>
          {expanded && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="overflow-hidden">
              <div className="mt-3 pt-3 border-t border-am-border pl-8">
                <textarea
                  rows={2}
                  value={nota}
                  onChange={(e) => setNota(e.target.value)}
                  placeholder="Observações sobre este lead…"
                  className="am-textarea"
                />
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Ações */}
        <div className="mt-3 pt-3 border-t border-am-border flex items-center gap-1.5 flex-wrap pl-8">
          {lead.status !== 'contatado'   && lead.status !== 'descartado' && (
            <ActionBtn icon={<Phone size={10} />} label="Contatado" color="#D08010"
              onClick={() => onStatusChange(lead.id, 'contatado', nota)} />
          )}
          {lead.status !== 'qualificado' && lead.status !== 'descartado' && (
            <ActionBtn icon={<CheckCircle size={10} />} label="Qualificado" color="#1A9E78"
              onClick={() => onStatusChange(lead.id, 'qualificado', nota)} />
          )}
          {lead.status !== 'descartado' && (
            <ActionBtn icon={<XCircle size={10} />} label="Descartar" color="#8AAAC0"
              onClick={() => onStatusChange(lead.id, 'descartado', nota)} />
          )}
          {lead.status === 'descartado' && (
            <ActionBtn icon={<RefreshCw size={10} />} label="Reabrir" color="#3A7AB8"
              onClick={() => onStatusChange(lead.id, 'novo', nota)} />
          )}

          <div className="ml-auto flex items-center gap-1">
            <button onClick={() => setExpanded((v) => !v)}
              className="flex items-center gap-1 text-[10px] text-am-muted px-2.5 py-1.5 rounded-lg transition-colors hover:text-am-secondary"
              style={{ border: '1px solid var(--color-am-border)' }}>
              {expanded ? <ChevronUp size={10} /> : <ChevronDown size={10} />}
              {expanded ? 'Menos' : 'Notas'}
            </button>
            <button onClick={() => onDelete(lead.id)}
              className="w-7 h-7 rounded-lg flex items-center justify-center text-am-muted transition-colors hover:text-red-500"
              style={{ border: '1px solid var(--color-am-border)' }}>
              <Trash2 size={11} />
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

function ActionBtn({ icon, label, color, onClick }: {
  icon: React.ReactNode; label: string; color: string; onClick: () => void
}) {
  return (
    <button onClick={onClick}
      className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-[10px] font-semibold transition-opacity hover:opacity-80"
      style={{ color, background: `${color}10`, border: `1px solid ${color}28` }}>
      {icon} {label}
    </button>
  )
}

/* ─── Página principal ──────────────────────────────────────────────────── */

type Tab = 'dna' | 'buscar' | 'pipeline'

export default function CaptacaoPage() {
  const [tab, setTab]           = useState<Tab>('buscar')
  const [tipoAcao, setTipoAcao] = useState(TIPOS_ACAO[0])
  const [tipoLead, setTipoLead] = useState<TipoLead | 'auto'>('auto')
  const [tribunal, setTribunal] = useState('')
  const [limite, setLimite]     = useState(5)
  const [scoreMin, setScoreMin] = useState(40)
  const [filterStatus, setFilterStatus] = useState<LeadStatus | 'todos'>('todos')
  const [filterTipo,   setFilterTipo]   = useState<TipoLead | 'todos'>('todos')

  const qc = useQueryClient()

  const { data: dna, isLoading: dnaLoading } = useQuery({
    queryKey: ['dna'],
    queryFn: fetchDNA,
    retry: 1,
  })

  const { data: pipeline, isLoading: pipelineLoading } = useQuery({
    queryKey: ['pipeline', filterStatus, filterTipo],
    queryFn: () => fetchPipeline({
      status:    filterStatus !== 'todos' ? filterStatus : undefined,
      tipo_lead: filterTipo   !== 'todos' ? filterTipo   : undefined,
    }),
    retry: 1,
  })

  const refreshDNA = useMutation({
    mutationFn: atualizarDNA,
    onSuccess:  () => qc.invalidateQueries({ queryKey: ['dna'] }),
  })

  const descobrir = useMutation({
    mutationFn: descobrirLeads,
    onSuccess:  () => qc.invalidateQueries({ queryKey: ['pipeline'] }),
  })

  const updateStatus = useMutation({
    mutationFn: ({ id, status, notas }: { id: number; status: LeadStatus; notas?: string }) =>
      atualizarStatus(id, { status, notas_advogado: notas }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pipeline'] }),
  })

  const remover = useMutation({
    mutationFn: deletarLead,
    onSuccess:  () => qc.invalidateQueries({ queryKey: ['pipeline'] }),
  })

  const leads        = pipeline?.leads ?? []
  const qualificados = leads.filter((l) => l.status === 'qualificado').length
  const scoreMedio   = leads.length
    ? Math.round(leads.reduce((a, l) => a + (l.score_match ?? 0), 0) / leads.length)
    : 0

  const TABS = [
    { id: 'dna'      as Tab, icon: <Dna    size={13} />, label: 'Perfil' },
    { id: 'buscar'   as Tab, icon: <Search size={13} />, label: 'Buscar' },
    { id: 'pipeline' as Tab, icon: <List   size={13} />, label: `Pipeline${pipeline?.total ? ` (${pipeline.total})` : ''}` },
  ]

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="flex flex-col h-full w-full max-w-2xl mx-auto">

        {/* ── Header ── */}
        <div className="flex-shrink-0 px-4 pt-5 pb-3">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-base font-extrabold text-am-ink tracking-tight">Captação</h2>
              <p className="text-[11px] text-am-muted mt-0.5">Leads qualificados pela IA</p>
            </div>
            <div className="w-9 h-9 rounded-xl flex items-center justify-center"
              style={{ background: 'linear-gradient(135deg,#1248BE,#4A8ED4)', boxShadow: '0 3px 10px rgba(18,72,190,0.20)' }}>
              <Target size={16} className="text-white" />
            </div>
          </div>

          {/* Tab switcher */}
          <div className="flex gap-1 p-1 rounded-xl" style={{ background: 'rgba(12,30,48,0.05)' }}>
            {TABS.map((t) => {
              const active = tab === t.id
              return (
                <motion.button
                  key={t.id}
                  onClick={() => setTab(t.id)}
                  whileTap={{ scale: 0.96 }}
                  transition={{ type: 'spring', stiffness: 400, damping: 28 }}
                  className="relative flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold flex-1 justify-center"
                  style={{ color: active ? 'var(--color-am-blue)' : 'var(--color-am-muted)' }}>
                  {active && (
                    <motion.span
                      layoutId="cap-tab"
                      className="absolute inset-0 rounded-lg bg-white"
                      style={{ boxShadow: '0 1px 4px rgba(18,72,190,0.10)' }}
                      transition={{ type: 'spring', stiffness: 400, damping: 28 }}
                    />
                  )}
                  <span className="relative">{t.icon}</span>
                  <span className="relative">{t.label}</span>
                </motion.button>
              )
            })}
          </div>
        </div>

        {/* ── Conteúdo ── */}
        <div className="flex-1 overflow-y-auto">
          <div className="px-4 pb-8 space-y-4">

            {/* ── TAB DNA ───────────────────────────────────────────── */}
            {tab === 'dna' && (
              <>
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-bold text-am-ink">Perfil do escritório</p>
                    <p className="text-[11px] text-am-muted mt-0.5">
                      A IA analisa seus processos e monta seu perfil ideal de captação
                    </p>
                  </div>
                  <button onClick={() => refreshDNA.mutate()}
                    disabled={refreshDNA.isPending}
                    className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-white text-[11px] font-semibold disabled:opacity-50"
                    style={{ background: 'linear-gradient(135deg,#1248BE,#3A7AB8)' }}>
                    {refreshDNA.isPending
                      ? <><Loader2 size={12} className="animate-spin" /> Gerando…</>
                      : <><RefreshCw size={12} /> Atualizar</>}
                  </button>
                </div>

                {dnaLoading ? (
                  <div className="h-48 rounded-2xl animate-pulse" style={{ background: 'rgba(58,122,184,0.06)' }} />
                ) : !dna || dna.dados_insuficientes ? (
                  <div className="bg-white rounded-2xl p-10 flex flex-col items-center gap-3 text-center"
                    style={{ border: '1px solid var(--color-am-border)', boxShadow: '0 1px 6px rgba(12,30,48,0.05)' }}>
                    <div className="w-12 h-12 rounded-2xl flex items-center justify-center"
                      style={{ background: 'rgba(208,128,16,0.08)' }}>
                      <Dna size={22} style={{ color: '#D08010' }} />
                    </div>
                    <div>
                      <p className="text-sm font-bold text-am-ink">DNA não gerado</p>
                      <p className="text-[11px] text-am-muted mt-1 max-w-[240px] leading-relaxed">
                        Clique em <strong>Atualizar</strong> para que a IA analise o histórico de processos
                      </p>
                    </div>
                  </div>
                ) : (
                  <div className="bg-white rounded-2xl overflow-hidden"
                    style={{ border: '1px solid var(--color-am-border)', boxShadow: '0 1px 6px rgba(12,30,48,0.05)' }}>

                    {/* Especialidades */}
                    <div className="px-5 py-4 border-b border-am-border">
                      <p className="text-[10px] font-bold text-am-muted uppercase tracking-wider mb-2.5">Especialidades</p>
                      <div className="flex flex-wrap gap-1.5">
                        {dna.especialidades.map((e) => (
                          <span key={e} className="text-[10px] font-semibold px-2.5 py-1 rounded-lg"
                            style={{ color: '#3A7AB8', background: 'rgba(58,122,184,0.08)', border: '1px solid rgba(58,122,184,0.15)' }}>
                            {e}
                          </span>
                        ))}
                      </div>
                    </div>

                    {/* Setores-alvo */}
                    {dna.setores_alvo.length > 0 && (
                      <div className="px-5 py-4 border-b border-am-border">
                        <p className="text-[10px] font-bold text-am-muted uppercase tracking-wider mb-2.5">Setores-alvo</p>
                        <div className="flex flex-wrap gap-1.5">
                          {dna.setores_alvo.map((s) => (
                            <span key={s} className="text-[10px] font-semibold px-2.5 py-1 rounded-lg"
                              style={{ color: '#1A9E78', background: 'rgba(26,158,120,0.08)', border: '1px solid rgba(26,158,120,0.15)' }}>
                              {s}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Tipo + diferenciais */}
                    <div className="px-5 py-4 flex flex-col gap-3">
                      <div className="flex items-center justify-between">
                        <p className="text-[10px] font-bold text-am-muted uppercase tracking-wider">Foco predominante</p>
                        <span className="text-xs font-bold flex items-center gap-1.5"
                          style={{ color: dna.tipo_lead_predominante === 'empresa' ? '#3A7AB8' : '#1A9E78' }}>
                          {dna.tipo_lead_predominante === 'empresa'
                            ? <><Building2 size={11} /> B2B</>
                            : dna.tipo_lead_predominante === 'pessoa'
                              ? <><User size={11} /> B2C</>
                              : 'Ambos'}
                        </span>
                      </div>

                      {dna.perfil_cliente_ideal && (
                        <div>
                          <p className="text-[10px] font-bold text-am-muted uppercase tracking-wider mb-1">Perfil ideal</p>
                          <p className="text-xs text-am-secondary leading-relaxed">{dna.perfil_cliente_ideal}</p>
                        </div>
                      )}

                      {dna.diferenciais.length > 0 && (
                        <div>
                          <p className="text-[10px] font-bold text-am-muted uppercase tracking-wider mb-1.5">Diferenciais</p>
                          <div className="space-y-1">
                            {dna.diferenciais.map((d) => (
                              <div key={d} className="flex items-start gap-1.5 text-[11px] text-am-secondary">
                                <Star size={9} className="flex-shrink-0 mt-0.5" style={{ color: '#D08010' }} />
                                {d}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {dna.gerado_em && (
                        <p className="text-[10px] text-am-muted">
                          Atualizado em {new Date(dna.gerado_em).toLocaleDateString('pt-BR', { day: '2-digit', month: 'short', year: 'numeric' })}
                        </p>
                      )}
                    </div>
                  </div>
                )}
              </>
            )}

            {/* ── TAB BUSCAR ────────────────────────────────────────── */}
            {tab === 'buscar' && (
              <>
                {/* Formulário */}
                <div className="bg-white rounded-2xl overflow-hidden"
                  style={{ border: '1px solid var(--color-am-border)', boxShadow: '0 1px 6px rgba(12,30,48,0.05)' }}>
                  <div className="px-4 py-3 border-b border-am-border">
                    <p className="text-[11px] font-bold text-am-secondary">Parâmetros de busca</p>
                  </div>

                  <div className="px-4 py-4 space-y-4">
                    {/* Tipo de ação */}
                    <div>
                      <label className="am-label">Tipo de ação</label>
                      <select value={tipoAcao} onChange={(e) => setTipoAcao(e.target.value)}
                        className="am-select">
                        {TIPOS_ACAO.map((t) => <option key={t} value={t}>{t}</option>)}
                      </select>
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                      {/* Tribunal */}
                      <div>
                        <label className="am-label">Tribunal</label>
                        <select value={tribunal} onChange={(e) => setTribunal(e.target.value)}
                          className="am-select">
                          {TRIBUNAIS.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
                        </select>
                      </div>

                      {/* Tipo de lead */}
                      <div>
                        <label className="am-label">Tipo de lead</label>
                        <select value={tipoLead} onChange={(e) => setTipoLead(e.target.value as TipoLead | 'auto')}
                          className="am-select">
                          <option value="auto">Auto (DNA)</option>
                          <option value="empresa">Empresa (B2B)</option>
                          <option value="pessoa">Pessoa (B2C)</option>
                        </select>
                      </div>
                    </div>

                    {/* Score mínimo */}
                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <label className="am-label mb-0">Score mínimo</label>
                        <span className="text-xs font-extrabold"
                          style={{ color: scoreColor(scoreMin) }}>{scoreMin}</span>
                      </div>
                      <input type="range" min={0} max={100} step={5} value={scoreMin}
                        onChange={(e) => setScoreMin(Number(e.target.value))}
                        className="am-range" />
                      <div className="flex justify-between text-[9px] mt-1.5">
                        <span style={{ color: '#C83030' }}>Frio</span>
                        <span style={{ color: '#D08010' }}>Morno</span>
                        <span style={{ color: '#1A9E78' }}>Quente</span>
                      </div>
                    </div>

                    {/* Quantidade */}
                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <label className="am-label mb-0">Candidatos</label>
                        <span className="text-xs font-extrabold text-am-ink">{limite}</span>
                      </div>
                      <input type="range" min={1} max={20} step={1} value={limite}
                        onChange={(e) => setLimite(Number(e.target.value))}
                        className="am-range" />
                    </div>
                  </div>

                  <div className="px-4 pb-4">
                    <button
                      onClick={() => descobrir.mutate({
                        tipo_acao: tipoAcao,
                        tipo_lead: tipoLead,
                        tribunal:  tribunal || null,
                        limite,
                        score_minimo: scoreMin,
                      })}
                      disabled={descobrir.isPending}
                      className="w-full py-3 rounded-xl text-white text-sm font-bold disabled:opacity-50 flex items-center justify-center gap-2 transition-opacity hover:opacity-90"
                      style={{ background: 'linear-gradient(135deg,#1248BE,#3A7AB8)' }}>
                      {descobrir.isPending
                        ? <><Loader2 size={14} className="animate-spin" /> Analisando com IA…</>
                        : <><Search size={14} /> Buscar leads</>}
                    </button>
                  </div>
                </div>

                {/* Erro */}
                {descobrir.isError && (
                  <div className="flex items-center gap-2 p-3 rounded-xl text-xs"
                    style={{ background: 'rgba(200,48,48,0.07)', border: '1px solid rgba(200,48,48,0.2)', color: '#C83030' }}>
                    <AlertTriangle size={12} />
                    Erro ao buscar leads. Verifique se o backend está ativo e o DNA foi gerado.
                  </div>
                )}

                {/* Resultado */}
                {descobrir.isSuccess && descobrir.data && (
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <p className="text-xs font-bold text-am-ink">
                        {descobrir.data.total} lead{descobrir.data.total !== 1 ? 's' : ''} encontrado{descobrir.data.total !== 1 ? 's' : ''}
                      </p>
                      <button onClick={() => setTab('pipeline')}
                        className="text-[11px] font-semibold text-am-blue hover:underline">
                        Ver pipeline →
                      </button>
                    </div>
                    {descobrir.data.leads.map((lead) => (
                      <LeadCard key={lead.id} lead={lead}
                        onStatusChange={(id, status, notas) => updateStatus.mutate({ id, status, notas })}
                        onDelete={(id) => remover.mutate(id)} />
                    ))}
                  </div>
                )}
              </>
            )}

            {/* ── TAB PIPELINE ──────────────────────────────────────── */}
            {tab === 'pipeline' && (
              <>
                {/* KPIs */}
                <div className="grid grid-cols-3 gap-3">
                  {[
                    { label: 'Total',        value: pipeline?.total ?? 0, color: '#3A7AB8'             },
                    { label: 'Qualificados', value: qualificados,         color: '#1A9E78'             },
                    { label: 'Score médio',  value: scoreMedio || '—',    color: scoreColor(scoreMedio)},
                  ].map(({ label, value, color }) => (
                    <div key={label} className="bg-white rounded-xl py-3 px-4 text-center"
                      style={{ border: '1px solid var(--color-am-border)', boxShadow: '0 1px 4px rgba(12,30,48,0.04)' }}>
                      <p className="text-lg font-extrabold leading-none" style={{ color }}>{value}</p>
                      <p className="text-[10px] text-am-muted mt-1">{label}</p>
                    </div>
                  ))}
                </div>

                {/* Filtros de status */}
                <div className="flex gap-1.5 flex-wrap">
                  {(['todos', 'novo', 'contatado', 'qualificado', 'descartado'] as const).map((s) => {
                    const cfg    = s !== 'todos' ? STATUS_CFG[s] : null
                    const active = filterStatus === s
                    return (
                      <button key={s} onClick={() => setFilterStatus(s)}
                        className="px-2.5 py-1 text-[10px] font-semibold rounded-lg transition-all"
                        style={active
                          ? { background: cfg?.bg ?? 'rgba(58,122,184,0.10)', color: cfg?.color ?? '#3A7AB8', border: `1px solid ${cfg?.color ?? '#3A7AB8'}28` }
                          : { background: 'transparent', color: 'var(--color-am-muted)', border: '1px solid transparent' }}>
                        {s === 'todos' ? 'Todos' : STATUS_CFG[s].label}
                      </button>
                    )
                  })}

                  <div className="h-5 w-px mx-1 self-center" style={{ background: 'var(--color-am-border)' }} />

                  {(['todos', 'empresa', 'pessoa'] as const).map((t) => {
                    const active = filterTipo === t
                    return (
                      <button key={t} onClick={() => setFilterTipo(t)}
                        className="flex items-center gap-1 px-2.5 py-1 text-[10px] font-semibold rounded-lg transition-all"
                        style={active
                          ? { background: 'rgba(58,122,184,0.10)', color: '#3A7AB8', border: '1px solid rgba(58,122,184,0.20)' }
                          : { background: 'transparent', color: 'var(--color-am-muted)', border: '1px solid transparent' }}>
                        {t === 'todos' ? 'Todos' : t === 'empresa' ? <><Building2 size={9} /> B2B</> : <><User size={9} /> B2C</>}
                      </button>
                    )
                  })}
                </div>

                {/* Lista */}
                {pipelineLoading ? (
                  <div className="space-y-3">
                    {Array.from({ length: 3 }).map((_, i) => (
                      <div key={i} className="h-24 rounded-2xl animate-pulse" style={{ background: 'rgba(58,122,184,0.06)' }} />
                    ))}
                  </div>
                ) : leads.length === 0 ? (
                  <div className="bg-white rounded-2xl p-12 flex flex-col items-center gap-3 text-center"
                    style={{ border: '1px solid var(--color-am-border)' }}>
                    <Target size={28} strokeWidth={1.5} className="text-am-muted" />
                    <div>
                      <p className="text-sm font-bold text-am-ink">Pipeline vazio</p>
                      <p className="text-[11px] text-am-muted mt-1">
                        Use a aba <strong>Buscar</strong> para encontrar leads qualificados
                      </p>
                    </div>
                    <button onClick={() => setTab('buscar')}
                      className="mt-1 px-4 py-2 rounded-xl text-white text-xs font-semibold"
                      style={{ background: 'linear-gradient(135deg,#1248BE,#3A7AB8)' }}>
                      Buscar leads
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
