import { useState, useRef, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Users, FileText, MessageCircle, Star,
  ArrowRight, Zap,
  TrendingUp, TrendingDown, Minus, Download,
  Bell, Check, X, ChevronDown, ChevronUp,
} from 'lucide-react'
import { fetchClientes, fetchResumoCRM } from '../api/crm'
import { exportarRelatorio } from '../api/chat'
import { listarEscalacoes, aprovarEscalacao, rejeitarEscalacao, type EscalacaoItem } from '../api/escalacoes'
import ProximasReunioes from '../components/agendamento/ProximasReunioes'
import type { CRMClienteCard } from '../types'
/* ── Barra animada ── */
function Bar({ pct, color }: { pct: number; color: string }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = ref.current; if (!el) return
    el.style.width = '0%'
    const id = requestAnimationFrame(() => requestAnimationFrame(() => { el.style.width = `${pct}%` }))
    return () => cancelAnimationFrame(id)
  }, [pct])
  return (
    <div className="h-1.5 rounded-full overflow-hidden flex-1" style={{ background: `${color}18` }}>
      <div ref={ref} className="h-full rounded-full" style={{ background: color, width: '0%', transition: 'width 0.7s cubic-bezier(0.4,0,0.2,1)' }} />
    </div>
  )
}

/* ── KPI card ── */
function KPI({ icon, label, value, sub, color, delta }: {
  icon: React.ReactNode; label: string; value: string | number
  sub?: string; color: string; delta?: number
}) {
  return (
    <div className="bg-white rounded-2xl p-4 flex flex-col gap-3 card-shadow card-border-hover"
      style={{ border: '1px solid var(--color-am-border)' }}>
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-bold uppercase tracking-wider text-am-muted">{label}</span>
        <div className="w-7 h-7 rounded-xl flex items-center justify-center flex-shrink-0"
          style={{ background: `${color}14`, color }}>
          {icon}
        </div>
      </div>
      <div className="text-2xl font-extrabold leading-none" style={{ color }}>{value}</div>
      <div className="flex items-center gap-2">
        {delta !== undefined && (
          <span className="flex items-center gap-0.5 text-[10px] font-semibold"
            style={{ color: delta > 0 ? '#1A9E78' : delta < 0 ? '#C83030' : '#A0AEC0' }}>
            {delta > 0 ? <TrendingUp size={10} /> : delta < 0 ? <TrendingDown size={10} /> : <Minus size={10} />}
            {delta > 0 ? '+' : ''}{delta}
          </span>
        )}
        {sub && <span className="text-[10px] text-am-muted">{sub}</span>}
      </div>
    </div>
  )
}

/* ── Section wrapper ── */
function Section({ title, icon, badge, children }: {
  title: string; icon: React.ReactNode; badge?: React.ReactNode; children: React.ReactNode
}) {
  return (
    <div className="bg-white rounded-2xl overflow-hidden card-shadow card-border-hover flex flex-col h-full"
      style={{ border: '1px solid var(--color-am-border)' }}>
      <div className="flex-shrink-0 flex items-center justify-between px-4 py-3"
        style={{ borderBottom: '1px solid var(--color-am-border)', background: 'rgba(12,30,48,0.02)' }}>
        <div className="flex items-center gap-2">
          <span className="text-am-blue">{icon}</span>
          <span className="text-[10px] font-bold uppercase tracking-wider text-am-secondary">{title}</span>
        </div>
        {badge}
      </div>
      <div className="flex-1 flex flex-col">{children}</div>
    </div>
  )
}

/* ── Escalações ─────────────────────────────────────────────────────────── */
function EscalacoesSection() {
  const qc = useQueryClient()
  const [expandido, setExpandido] = useState<number | null>(null)
  const [respostas, setRespostas] = useState<Record<number, string>>({})

  const { data: escalacoes, isLoading } = useQuery({
    queryKey: ['escalacoes-pendentes'],
    queryFn: () => listarEscalacoes('pendente'),
    staleTime: 30_000,
    refetchInterval: 60_000,
  })

  const aprovarMut = useMutation({
    mutationFn: ({ id, resposta }: { id: number; resposta?: string }) =>
      aprovarEscalacao(id, resposta),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['escalacoes-pendentes'] }),
  })

  const rejeitarMut = useMutation({
    mutationFn: (id: number) => rejeitarEscalacao(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['escalacoes-pendentes'] }),
  })

  const pendentes = escalacoes ?? []
  const count = pendentes.length

  if (!isLoading && count === 0) return null

  return (
    <div className="flex-shrink-0">
    <Section
      title="Escalações pendentes"
      icon={<Bell size={13} />}
      badge={
        count > 0
          ? <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full text-white"
              style={{ background: '#C83030' }}>{count}</span>
          : undefined
      }
    >
      {isLoading ? (
        <div className="flex items-center justify-center h-16">
          <div className="w-4 h-4 rounded-full border-2 border-am-blue border-t-transparent animate-spin" />
        </div>
      ) : (
        <div className="divide-y divide-am-border">
          {pendentes.map((esc: EscalacaoItem) => {
            const aberto = expandido === esc.id
            const pendingAprovar = aprovarMut.isPending && aprovarMut.variables?.id === esc.id
            const pendingRejeitar = rejeitarMut.isPending && rejeitarMut.variables === esc.id
            const respostaEditada = respostas[esc.id] ?? esc.sugestao_resposta ?? ''

            return (
              <div key={esc.id}>
                {/* Cabeçalho do item */}
                <button
                  onClick={() => setExpandido(aberto ? null : esc.id)}
                  className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-am-bg transition-colors">
                  <div className="w-7 h-7 rounded-xl flex items-center justify-center text-[10px] font-bold text-white flex-shrink-0"
                    style={{ background: 'linear-gradient(135deg,#C83030,#E05050)' }}>
                    {(esc.cliente_nome ?? '?').slice(0, 2).toUpperCase()}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-semibold text-am-ink truncate">
                      {esc.cliente_nome ?? `Cliente #${esc.cliente_id}`}
                    </p>
                    <p className="text-[10px] text-am-muted truncate mt-0.5">
                      {esc.mensagem_cliente ?? '—'}
                    </p>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <span className="text-[10px] text-am-muted">
                      {new Date(esc.created_at).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}
                    </span>
                    {aberto ? <ChevronUp size={11} className="text-am-muted" /> : <ChevronDown size={11} className="text-am-muted" />}
                  </div>
                </button>

                {/* Detalhe expandido */}
                <AnimatePresence>
                  {aberto && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.2 }}
                      className="overflow-hidden">
                      <div className="px-4 pb-4 space-y-3">
                        {/* Mensagem do cliente */}
                        {esc.mensagem_cliente && (
                          <div className="rounded-xl p-3" style={{ background: 'rgba(12,30,48,0.04)', border: '1px solid var(--color-am-border)' }}>
                            <p className="text-[10px] font-bold uppercase tracking-wider text-am-muted mb-1">Mensagem do cliente</p>
                            <p className="text-xs text-am-ink leading-relaxed">{esc.mensagem_cliente}</p>
                          </div>
                        )}

                        {/* Sugestão da IA (editável) */}
                        <div>
                          <p className="text-[10px] font-bold uppercase tracking-wider text-am-muted mb-1">
                            Resposta sugerida pela IA
                            <span className="normal-case font-normal ml-1">(editável)</span>
                          </p>
                          <textarea
                            value={respostaEditada}
                            onChange={e => setRespostas(prev => ({ ...prev, [esc.id]: e.target.value }))}
                            rows={4}
                            className="am-textarea"
                          />
                        </div>

                        {/* Ações */}
                        <div className="flex items-center gap-2">
                          <button
                            disabled={pendingAprovar || pendingRejeitar}
                            onClick={() => aprovarMut.mutate({ id: esc.id, resposta: respostaEditada || undefined })}
                            className="flex items-center gap-1.5 flex-1 justify-center py-2 rounded-xl text-xs font-semibold text-white transition-opacity"
                            style={{ background: 'linear-gradient(135deg,#1A9E78,#25C896)', opacity: pendingAprovar ? 0.6 : 1, cursor: pendingAprovar ? 'not-allowed' : 'pointer' }}>
                            {pendingAprovar
                              ? <div className="w-3 h-3 rounded-full border-2 border-white border-t-transparent animate-spin" />
                              : <Check size={12} />}
                            Aprovar e enviar
                          </button>
                          <button
                            disabled={pendingAprovar || pendingRejeitar}
                            onClick={() => rejeitarMut.mutate(esc.id)}
                            className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold transition-colors"
                            style={{ border: '1px solid rgba(200,48,48,0.3)', color: '#C83030', background: 'rgba(200,48,48,0.05)', cursor: pendingRejeitar ? 'not-allowed' : 'pointer', opacity: pendingRejeitar ? 0.6 : 1 }}>
                            {pendingRejeitar
                              ? <div className="w-3 h-3 rounded-full border-2 border-red-400 border-t-transparent animate-spin" />
                              : <X size={12} />}
                            Rejeitar
                          </button>
                        </div>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            )
          })}
        </div>
      )}
    </Section>
    </div>
  )
}

function ini(nome: string) {
  return nome.split(' ').slice(0, 2).map((n) => n[0].toUpperCase()).join('')
}


const NIVEL_CFG: Record<string, { label: string; color: string; bg: string }> = {
  em_risco: { label: 'Atenção', color: '#C83030', bg: 'rgba(200,48,48,0.08)' },
  critico:  { label: 'Crítico', color: '#8B0000', bg: 'rgba(139,0,0,0.08)'   },
}

interface Props {
  onSelectCliente: (id: number) => void
  /** Agendamento Inteligente — navegação para Clientes → Agenda / pendentes */
  onVerAgenda?: (semanaISO: string) => void
  onVerPendentes?: () => void
}

export default function PainelPage({ onSelectCliente, onVerAgenda, onVerPendentes }: Props) {
  const [periodo, setPeriodo] = useState<7 | 30 | 90>(30)
  const [mes, setMes] = useState(() => new Date().toISOString().slice(0, 7))

  const exportMut = useMutation({
    mutationFn: () => exportarRelatorio(mes),
  })

  const { data: clientes, isLoading } = useQuery({
    queryKey: ['clientes'],
    queryFn: fetchClientes,
    staleTime: 60_000,
  })

  const { data: resumo } = useQuery({
    queryKey: ['crm-resumo'],
    queryFn: fetchResumoCRM,
    staleTime: 60_000,
  })

  /* ── Métricas derivadas ── */
  const total         = clientes?.length ?? 0
  const totalProc     = clientes?.reduce((a, c) => a + c.total_processos, 0) ?? 0
  const clientesRisco = clientes?.filter((c) => c.crm_nivel === 'em_risco' || c.crm_nivel === 'critico') ?? []
  const emRisco       = clientesRisco.length
  const npsArr        = clientes?.map((c) => c.nps_medio).filter((n): n is number => n !== null) ?? []
  const npsMedia      = npsArr.length ? +(npsArr.reduce((a, b) => a + b, 0) / npsArr.length).toFixed(1) : null

  /* Eficiência estimada (derivada dos dados disponíveis) */
  const semAnalise     = resumo?.sem_analise ?? 0
  const analisados     = total - semAnalise
  const autonomiaPct   = total > 0 ? Math.round((analisados / total) * 100) : 0
  const horasEconomiadas = +(analisados * 0.5).toFixed(1)

  return (
    <div className="flex-1 overflow-hidden flex flex-col">
      <div className="flex-1 min-h-0 flex flex-col px-6 pt-3 pb-5 max-w-6xl mx-auto w-full gap-5 page-enter">

        {/* ── Header ── */}
        <div className="flex-shrink-0">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div>
            <h2 className="text-sm font-bold text-am-ink tracking-tight">Painel de Resultados</h2>
            <p className="text-xs text-am-muted mt-0.5">Visão geral do escritório</p>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            {/* Período */}
            <div className="flex gap-0.5 p-0.5 rounded-xl" style={{ background: 'rgba(12,30,48,0.05)' }}>
              {([7, 30, 90] as const).map((d) => (
                <motion.button
                  key={d}
                  onClick={() => setPeriodo(d)}
                  whileHover={{ scale: periodo === d ? 1 : 1.05 }}
                  whileTap={{ scale: 0.95 }}
                  transition={{ type: 'spring', stiffness: 400, damping: 28 }}
                  className="px-3 py-1.5 rounded-lg text-[11px] font-semibold press"
                  style={periodo === d
                    ? { background: 'white', color: 'var(--color-am-blue)', boxShadow: '0 1px 4px rgba(18,72,190,0.12)' }
                    : { color: 'var(--color-am-muted)' }
                  }>
                  {d}d
                </motion.button>
              ))}
            </div>
            {/* Exportar */}
            <div className="flex items-center gap-1.5">
              <input
                type="month"
                value={mes}
                onChange={e => setMes(e.target.value)}
                className="am-input"
                style={{ width: 140 }}
              />
              <button
                onClick={() => exportMut.mutate()}
                disabled={exportMut.isPending}
                className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-semibold text-white flex-shrink-0 transition-opacity"
                style={{
                  background: 'linear-gradient(135deg,#1248BE,#3A7AB8)',
                  opacity: exportMut.isPending ? 0.6 : 1,
                  cursor: exportMut.isPending ? 'not-allowed' : 'pointer',
                }}>
                {exportMut.isPending
                  ? <div className="w-3 h-3 rounded-full border-2 border-white border-t-transparent animate-spin" />
                  : <Download size={12} />}
                CSV
              </button>
            </div>
          </div>
        </div>
        {exportMut.isError && (
          <p className="text-xs text-red-500 mt-1">Erro ao exportar. Verifique se há dados para o mês selecionado.</p>
        )}
        </div>

        {/* ── KPIs ── */}
        <div className="flex-shrink-0">
        {isLoading ? (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-24 rounded-2xl animate-pulse" style={{ background: 'rgba(12,30,48,0.05)' }} />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[
              { icon: <Users size={14} />,         label: 'Clientes ativos', value: total,     color: '#1248BE', sub: `${totalProc} processos` },
              { icon: <FileText size={14} />,      label: 'Processos',       value: totalProc, color: '#6B7CFF', sub: 'Total vinculados' },
              { icon: <MessageCircle size={14} />, label: 'Atenção ao cliente', value: emRisco, color: '#C83030', sub: 'Satisfação crítica', delta: emRisco > 0 ? emRisco : undefined },
              { icon: <Star size={14} />,          label: 'NPS médio',       value: npsMedia !== null ? `${npsMedia}` : '—', color: '#1A9E78', sub: 'Satisfação' },
            ].map((kpi, i) => (
              <motion.div
                key={kpi.label}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.28, delay: i * 0.06, ease: [0.34, 1.1, 0.64, 1] }}
              >
                <KPI {...kpi} />
              </motion.div>
            ))}
          </div>
        )}
        </div>

        {/* ── Escalações pendentes ── */}
        <EscalacoesSection />

        {/* ── Próximas reuniões (Agendamento Inteligente) ── */}
        <ProximasReunioes
          onVerAgenda={(semanaISO) => onVerAgenda?.(semanaISO)}
          onVerPendentes={() => onVerPendentes?.()}
        />

        {/* ── Clientes em risco + Eficiência (lado a lado quando há dados de risco) ── */}
        <div className={`flex-1 min-h-0 grid gap-5 items-stretch ${!isLoading && clientesRisco.length > 0 ? 'sm:grid-cols-2' : 'grid-cols-1'}`}>

        {/* ── Clientes em risco ── */}
        {!isLoading && clientesRisco.length > 0 && (
          <Section
            title="Atenção ao relacionamento"
            icon={<MessageCircle size={13} />}
            badge={
              <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full text-white"
                style={{ background: '#C83030' }}>
                {clientesRisco.length}
              </span>
            }
          >
            <div className="flex-1 overflow-y-auto divide-y divide-am-border">
              {clientesRisco.map((c: CRMClienteCard) => {
                const cfg = NIVEL_CFG[c.crm_nivel ?? ''] ?? NIVEL_CFG.em_risco

                return (
                  <motion.button
                    key={c.id}
                    onClick={() => onSelectCliente(c.id)}
                    whileHover={{ backgroundColor: 'var(--color-am-bg)' }}
                    whileTap={{ scale: 0.99 }}
                    transition={{ duration: 0.15 }}
                    className="w-full flex items-start gap-3 px-4 py-3.5 text-left group transition-colors">

                    {/* Avatar */}
                    <div className="w-8 h-8 rounded-xl flex items-center justify-center text-[11px] font-bold text-white flex-shrink-0 mt-0.5"
                      style={{ background: 'linear-gradient(135deg,#C83030,#E05050)' }}>
                      {ini(c.nome)}
                    </div>

                    {/* Info */}
                    <div className="flex-1 min-w-0 space-y-1.5">

                      {/* Nome + badge */}
                      <div className="flex items-center gap-2">
                        <p className="text-xs font-semibold text-am-ink truncate">{c.nome}</p>
                        <span className="flex-shrink-0 text-[10px] font-bold px-1.5 py-0.5 rounded-md"
                          style={{ color: cfg.color, background: cfg.bg }}>
                          {cfg.label}
                        </span>
                      </div>

                      {/* Recomendação */}
                      {c.crm_acao_sugerida && (
                        <p className="text-xs font-medium leading-snug text-am-ink pt-1.5"
                          style={{ borderTop: '1px solid var(--color-am-border)' }}>
                          {c.crm_acao_sugerida}
                        </p>
                      )}
                    </div>

                    <ArrowRight size={12} className="text-am-muted opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0 mt-1" />
                  </motion.button>
                )
              })}
            </div>
          </Section>
        )}

        {/* ── Eficiência da IA ── */}
        <Section title="Eficiência da IA" icon={<Zap size={13} />}>
          {(() => {
            const autoColor = autonomiaPct >= 70 ? '#1A9E78' : autonomiaPct >= 50 ? '#D08010' : '#C83030'
            return (
              <div className="flex-1 min-h-0 flex flex-col p-5 gap-4">

                {/* Stat cards — grow to fill the card height */}
                <div className="flex-1 min-h-0 grid grid-cols-3 gap-3">
                  {[
                    { label: 'Clientes analisados', value: `${analisados}/${total}`, color: '#1248BE' },
                    { label: 'Autonomia IA',         value: `${autonomiaPct}%`,       color: autoColor },
                    { label: 'Horas economizadas',   value: `${horasEconomiadas}h`,   color: '#6B7CFF' },
                  ].map(({ label, value, color }) => (
                    <div key={label}
                      className="flex flex-col items-center justify-center rounded-2xl gap-2 px-2"
                      style={{ background: `${color}08`, border: `1px solid ${color}18` }}>
                      <p className="text-2xl font-extrabold leading-none" style={{ color }}>{value}</p>
                      <p className="text-[10px] text-am-muted leading-snug text-center">{label}</p>
                    </div>
                  ))}
                </div>

                {/* Progress bar — anchored at bottom */}
                <div className="flex-shrink-0 space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] text-am-secondary">Atendimentos resolvidos pela IA</span>
                    <span className="text-[11px] font-bold" style={{ color: autoColor }}>{autonomiaPct}%</span>
                  </div>
                  <Bar pct={autonomiaPct} color={autoColor} />
                  <p className="text-[10px] text-am-muted">
                    {analisados} de {total} clientes analisados · {horasEconomiadas}h economizadas
                  </p>
                </div>

              </div>
            )
          })()}
        </Section>

        </div>{/* /grid 2 colunas */}

      </div>
    </div>
  )
}
