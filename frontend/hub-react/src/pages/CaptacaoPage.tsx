import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import {
  Target, Search, Dna, List, Building2, User, Star,
  RefreshCw, Loader2, AlertTriangle, Phone, CheckCircle,
  XCircle, Trash2, Sparkles, ChevronDown, ChevronUp,
  Shield, ExternalLink, FileText,
} from 'lucide-react'
import { Select } from '../components/Select'
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
  { value: 'TJSP',  label: 'TJSP — São Paulo'      },
  { value: 'TJRJ',  label: 'TJRJ — Rio de Janeiro' },
  { value: 'TJMG',  label: 'TJMG — Minas Gerais'   },
  { value: 'TRT2',  label: 'TRT2 — São Paulo'       },
  { value: 'TRT15', label: 'TRT15 — Campinas'       },
  { value: 'STJ',   label: 'STJ'                    },
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

/* ─── Aviso LGPD ─────────────────────────────────────────────────────────── */

function AvisoLGPD({ texto }: { texto: string }) {
  return (
    <div className="flex items-start gap-2.5 rounded-2xl p-3.5"
      style={{ background: 'rgba(208,128,16,0.06)', border: '1px solid rgba(208,128,16,0.22)' }}>
      <Shield size={13} className="flex-shrink-0 mt-0.5" style={{ color: '#D08010' }} />
      <p className="text-[11px] leading-relaxed" style={{ color: '#7A4D00' }}>{texto}</p>
    </div>
  )
}

/* ─── LeadCard ─────────────────────────────────────────────────────────── */

function LeadCard({ lead, onStatusChange, onDelete }: {
  lead: LeadProspeccaoResponse
  onStatusChange: (id: number, status: LeadStatus, notas?: string) => void
  onDelete: (id: number) => void
}) {
  const [expanded, setExpanded] = useState(false)
  const [nota, setNota]         = useState(lead.notas_advogado ?? '')

  const cfg   = STATUS_CFG[lead.status as LeadStatus] ?? STATUS_CFG.novo
  const isEmp = lead.tipo_lead === 'empresa'
  const score = lead.score_match

  const accentColor =
    lead.status === 'qualificado' ? '#1A9E78' :
    lead.status === 'descartado'  ? '#C8D8E8' :
    score !== null && score >= 75  ? '#1A9E78' :
    score !== null && score >= 40  ? '#D08010' : '#3A7AB8'

  return (
    <div className="bg-white rounded-2xl overflow-hidden"
      style={{
        border: '1px solid var(--color-am-border)',
        borderLeft: `3px solid ${accentColor}`,
        boxShadow: '0 1px 4px rgba(12,30,48,0.05)',
      }}>
      <div className="px-4 pt-3.5 pb-3 space-y-2.5">

        {/* ── Linha principal ── */}
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-xl flex items-center justify-center flex-shrink-0"
            style={{ background: isEmp ? 'rgba(58,122,184,0.10)' : 'rgba(26,158,120,0.10)' }}>
            {isEmp
              ? <Building2 size={12} style={{ color: '#3A7AB8' }} />
              : <User      size={12} style={{ color: '#1A9E78' }} />}
          </div>
          <p className="flex-1 text-sm font-semibold text-am-ink truncate">{lead.nome}</p>

          {/* Score */}
          {score !== null && (
            <span className="text-[10px] font-extrabold px-1.5 py-0.5 rounded-md flex-shrink-0"
              style={{ color: scoreColor(score), background: `${scoreColor(score)}14` }}>
              {score}
            </span>
          )}

          <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full flex-shrink-0"
            style={{ color: cfg.color, background: cfg.bg }}>
            {cfg.label}
          </span>
        </div>

        {/* ── Detalhe contextual ── */}
        <div className="pl-9 space-y-2">
          {/* Meta linha */}
          {(isEmp
            ? (lead.empresa_setor || lead.empresa_porte)
            : (lead.tipo_acao_origem || lead.polo_processo)) && (
            <p className="text-[11px] text-am-muted leading-snug">
              {isEmp
                ? [lead.empresa_setor, lead.empresa_porte].filter(Boolean).join(' · ')
                : [lead.tipo_acao_origem, lead.polo_processo ? `polo ${lead.polo_processo}` : null].filter(Boolean).join(' · ')}
              {!isEmp && lead.processos_publicos_count > 1 && (
                <span className="text-am-border"> · {lead.processos_publicos_count} processos públicos</span>
              )}
            </p>
          )}

          {/* Abordagem sugerida pela IA — principal valor */}
          {lead.abordagem_sugerida && (
            <div className="flex items-start gap-1.5">
              <Sparkles size={9} className="flex-shrink-0 mt-0.5" style={{ color: '#3A7AB8' }} />
              <p className="text-[11px] leading-snug text-am-secondary">{lead.abordagem_sugerida}</p>
            </div>
          )}

          {/* Sócios (empresa B2B) */}
          {isEmp && lead.socios.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {lead.socios.slice(0, 3).map((s) => (
                <span key={s.nome} className="text-[10px] px-2 py-0.5 rounded-lg text-am-secondary"
                  style={{ background: 'rgba(12,30,48,0.04)', border: '1px solid var(--color-am-border)' }}>
                  {s.nome}
                </span>
              ))}
              {lead.socios.length > 3 && (
                <span className="text-[10px] text-am-muted self-center">+{lead.socios.length - 3}</span>
              )}
            </div>
          )}

          {/* Contatos LinkedIn */}
          {isEmp && lead.contatos_linkedin.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {lead.contatos_linkedin.slice(0, 2).map((c) => (
                <a key={c.url_perfil} href={c.url_perfil} target="_blank" rel="noopener noreferrer"
                  className="flex items-center gap-1 text-[10px] font-medium px-2 py-0.5 rounded-lg transition-opacity hover:opacity-70"
                  style={{ color: '#0077B5', background: 'rgba(0,119,181,0.07)', border: '1px solid rgba(0,119,181,0.18)' }}>
                  <ExternalLink size={8} />
                  {c.nome}
                  {c.cargo && <span className="text-[9px] opacity-70">· {c.cargo}</span>}
                </a>
              ))}
            </div>
          )}

          {/* CNJ de referência (pessoa B2C) */}
          {!isEmp && lead.numero_cnj_exemplo && (
            <div className="flex items-center gap-1.5">
              <FileText size={9} className="text-am-muted flex-shrink-0" />
              <span className="text-[10px] font-mono text-am-muted">{lead.numero_cnj_exemplo}</span>
            </div>
          )}

          {/* Score motivo (expansível) */}
          {expanded && lead.score_motivo && (
            <p className="text-[11px] text-am-muted leading-snug italic pt-0.5 border-t border-am-border">
              {lead.score_motivo}
            </p>
          )}

          {/* Notas do advogado */}
          {expanded && (
            <textarea
              rows={2}
              value={nota}
              onChange={(e) => setNota(e.target.value)}
              placeholder="Observações sobre este lead…"
              className="am-textarea"
            />
          )}
        </div>

        {/* ── Ações ── */}
        <div className="flex items-center gap-1.5 pt-2.5 border-t border-am-border">
          {lead.status !== 'contatado'   && lead.status !== 'descartado' && (
            <Chip icon={<Phone size={9} />} label="Contatado" color="#D08010"
              onClick={() => onStatusChange(lead.id, 'contatado', nota || undefined)} />
          )}
          {lead.status !== 'qualificado' && lead.status !== 'descartado' && (
            <Chip icon={<CheckCircle size={9} />} label="Qualificado" color="#1A9E78"
              onClick={() => onStatusChange(lead.id, 'qualificado', nota || undefined)} />
          )}
          {lead.status !== 'descartado' && (
            <Chip icon={<XCircle size={9} />} label="Descartar" color="#8AAAC0"
              onClick={() => onStatusChange(lead.id, 'descartado', nota || undefined)} />
          )}
          {lead.status === 'descartado' && (
            <Chip icon={<RefreshCw size={9} />} label="Reabrir" color="#3A7AB8"
              onClick={() => onStatusChange(lead.id, 'novo', nota || undefined)} />
          )}

          <div className="ml-auto flex items-center gap-1">
            <button onClick={() => setExpanded((v) => !v)}
              className="flex items-center gap-1 text-[10px] text-am-muted px-2 py-1 rounded-lg transition-colors hover:text-am-secondary"
              style={{ border: '1px solid var(--color-am-border)' }}>
              {expanded ? <ChevronUp size={9} /> : <ChevronDown size={9} />}
              {expanded ? 'Menos' : 'Mais'}
            </button>
            <button onClick={() => onDelete(lead.id)}
              className="w-6 h-6 rounded-lg flex items-center justify-center text-am-muted transition-colors hover:text-red-400"
              style={{ border: '1px solid var(--color-am-border)' }}>
              <Trash2 size={10} />
            </button>
          </div>
        </div>

      </div>
    </div>
  )
}

function Chip({ icon, label, color, onClick }: {
  icon: React.ReactNode; label: string; color: string; onClick: () => void
}) {
  return (
    <button onClick={onClick}
      className="flex items-center gap-1 px-2 py-1 rounded-lg text-[10px] font-medium transition-opacity hover:opacity-75"
      style={{ color, background: `${color}0f`, border: `1px solid ${color}22` }}>
      {icon} {label}
    </button>
  )
}

/* ─── Página principal ──────────────────────────────────────────────────── */

type Tab = 'dna' | 'buscar' | 'pipeline'

export default function CaptacaoPage() {
  const [tab, setTab]           = useState<Tab>('buscar')
  const [tipoAcao, setTipoAcao] = useState(TIPOS_ACAO[0])
  const [tipoLead, setTipoLead] = useState<TipoLead | 'auto'>('empresa')
  const [tribunal, setTribunal] = useState('')
  const [filterStatus, setFilterStatus] = useState<LeadStatus | 'todos'>('todos')

  const qc = useQueryClient()

  const { data: dna, isLoading: dnaLoading } = useQuery({
    queryKey: ['dna'],
    queryFn: fetchDNA,
    retry: 1,
  })

  const { data: pipeline, isLoading: pipelineLoading } = useQuery({
    queryKey: ['pipeline', filterStatus],
    queryFn: () => fetchPipeline({
      status: filterStatus !== 'todos' ? filterStatus : undefined,
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

  // Se tipo_lead='auto' e DNA não disponível → bloquear busca
  const dnaOk       = dna && !dna.dados_insuficientes
  const autoSemDNA  = tipoLead === 'auto' && !dnaOk
  const podeDiscovrir = !autoSemDNA && !descobrir.isPending

  const TABS = [
    { id: 'dna'      as Tab, icon: <Dna    size={13} />, label: 'Perfil'    },
    { id: 'buscar'   as Tab, icon: <Search size={13} />, label: 'Buscar'    },
    { id: 'pipeline' as Tab, icon: <List   size={13} />, label: `Pipeline${pipeline?.total ? ` (${pipeline.total})` : ''}` },
  ]

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="flex flex-col h-full w-full max-w-3xl mx-auto">

        {/* ── Header ── */}
        <div className="flex-shrink-0 px-6 pt-5 pb-4">
          <div className="mb-4">
            <h2 className="text-sm font-bold text-am-ink tracking-tight">Captação</h2>
            <p className="text-xs text-am-muted mt-0.5">Leads qualificados pela IA</p>
          </div>

          {/* Tabs */}
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
          <div className="px-6 pb-8 space-y-4">

            {/* ── TAB DNA ── */}
            {tab === 'dna' && (
              <>
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-bold text-am-ink">Perfil do escritório</p>
                    <p className="text-[11px] text-am-muted mt-0.5">
                      A IA analisa seus processos e monta o perfil ideal de captação
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
                    style={{ border: '1px solid var(--color-am-border)' }}>
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

            {/* ── TAB BUSCAR ── */}
            {tab === 'buscar' && (
              <>
                <div className="bg-white rounded-2xl overflow-hidden"
                  style={{ border: '1px solid var(--color-am-border)', boxShadow: '0 1px 6px rgba(12,30,48,0.05)' }}>

                  <div className="px-4 py-4 space-y-3">
                    <div>
                      <label className="am-label">Tipo de ação</label>
                      <Select
                        value={tipoAcao}
                        onChange={setTipoAcao}
                        options={TIPOS_ACAO.map((t) => ({ value: t, label: t }))}
                      />
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="am-label">Tribunal</label>
                        <Select
                          value={tribunal}
                          onChange={setTribunal}
                          options={TRIBUNAIS.map((t) => ({ value: t.value, label: t.label }))}
                        />
                      </div>
                      <div>
                        <label className="am-label">Tipo de lead</label>
                        <Select
                          value={tipoLead}
                          onChange={(v) => setTipoLead(v as TipoLead | 'auto')}
                          options={[
                            { value: 'auto',    label: 'Auto (via DNA)' },
                            { value: 'empresa', label: 'Empresa (B2B)'  },
                            { value: 'pessoa',  label: 'Pessoa (B2C)'   },
                          ]}
                        />
                      </div>
                    </div>

                    {/* Aviso: auto sem DNA */}
                    {autoSemDNA && (
                      <div className="flex items-start gap-2 rounded-xl p-3"
                        style={{ background: 'rgba(208,128,16,0.07)', border: '1px solid rgba(208,128,16,0.22)' }}>
                        <AlertTriangle size={12} className="flex-shrink-0 mt-0.5" style={{ color: '#D08010' }} />
                        <p className="text-[11px] leading-snug" style={{ color: '#7A4D00' }}>
                          O modo <strong>Auto</strong> exige que o DNA do escritório esteja gerado.{' '}
                          <button onClick={() => setTab('dna')} className="font-semibold underline">
                            Gerar DNA →
                          </button>
                        </p>
                      </div>
                    )}
                  </div>

                  <div className="px-6 pb-4">
                    <button
                      onClick={() => descobrir.mutate({
                        tipo_acao:    tipoAcao,
                        tipo_lead:    tipoLead,
                        tribunal:     tribunal || null,
                        limite:       20,
                        score_minimo: 40,
                      })}
                      disabled={!podeDiscovrir}
                      className="w-full py-3 rounded-xl text-white text-sm font-bold disabled:opacity-50 flex items-center justify-center gap-2 transition-opacity hover:opacity-90"
                      style={{ background: 'linear-gradient(135deg,#1248BE,#3A7AB8)' }}>
                      {descobrir.isPending
                        ? <><Loader2 size={14} className="animate-spin" /> Analisando com IA…</>
                        : <><Sparkles size={14} /> Buscar leads</>}
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

                {/* Resultados */}
                {descobrir.isSuccess && descobrir.data && (
                  <div className="space-y-2.5">
                    <div className="flex items-center justify-between">
                      <p className="text-xs font-bold text-am-ink">
                        {descobrir.data.total} lead{descobrir.data.total !== 1 ? 's' : ''} encontrado{descobrir.data.total !== 1 ? 's' : ''}
                      </p>
                      <button onClick={() => setTab('pipeline')}
                        className="text-[11px] font-semibold text-am-blue hover:underline">
                        Ver pipeline →
                      </button>
                    </div>

                    {/* Aviso LGPD quando há leads B2C */}
                    {descobrir.data.aviso_lgpd && (
                      <AvisoLGPD texto={descobrir.data.aviso_lgpd} />
                    )}

                    {descobrir.data.leads.map((lead) => (
                      <LeadCard key={lead.id} lead={lead}
                        onStatusChange={(id, status, notas) => updateStatus.mutate({ id, status, notas })}
                        onDelete={(id) => remover.mutate(id)} />
                    ))}
                  </div>
                )}
              </>
            )}

            {/* ── TAB PIPELINE ── */}
            {tab === 'pipeline' && (
              <>
                {/* KPIs */}
                <div className="grid grid-cols-2 gap-3">
                  {[
                    { label: 'Total de leads', value: pipeline?.total ?? 0, color: '#3A7AB8' },
                    { label: 'Qualificados',   value: qualificados,         color: '#1A9E78' },
                  ].map(({ label, value, color }) => (
                    <div key={label} className="bg-white rounded-xl py-3 px-4 text-center"
                      style={{ border: '1px solid var(--color-am-border)', boxShadow: '0 1px 4px rgba(12,30,48,0.04)' }}>
                      <p className="text-xl font-extrabold leading-none" style={{ color }}>{value}</p>
                      <p className="text-[10px] text-am-muted mt-1">{label}</p>
                    </div>
                  ))}
                </div>

                {/* Aviso LGPD do pipeline */}
                {pipeline?.aviso_lgpd && <AvisoLGPD texto={pipeline.aviso_lgpd} />}

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
                </div>

                {/* Lista */}
                {pipelineLoading ? (
                  <div className="space-y-2.5">
                    {Array.from({ length: 3 }).map((_, i) => (
                      <div key={i} className="h-20 rounded-2xl animate-pulse" style={{ background: 'rgba(58,122,184,0.06)' }} />
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
                  <div className="space-y-2.5">
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
