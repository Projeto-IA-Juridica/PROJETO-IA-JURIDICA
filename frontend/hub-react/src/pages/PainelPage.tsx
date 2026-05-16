import { useState, useRef, useEffect } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import {
  Users, FileText, AlertTriangle, Star,
  ArrowRight, Shield, Zap, Clock,
  TrendingUp, TrendingDown, Minus, Download,
} from 'lucide-react'
import { fetchClientes, fetchResumoCRM } from '../api/crm'
import { exportarRelatorio } from '../api/chat'
import type { CRMClienteCard } from '../types'

/* ── Paleta de risco ── */
const RISK: Record<string, { color: string; bg: string; border: string; label: string }> = {
  baixo:    { color: '#1A9E78', bg: 'rgba(26,158,120,0.08)',  border: 'rgba(26,158,120,0.20)',  label: 'Baixo'    },
  moderado: { color: '#D08010', bg: 'rgba(208,128,16,0.08)',  border: 'rgba(208,128,16,0.20)',  label: 'Moderado' },
  alto:     { color: '#C83030', bg: 'rgba(200,48,48,0.08)',   border: 'rgba(200,48,48,0.20)',   label: 'Alto'     },
  critico:  { color: '#C83030', bg: 'rgba(200,48,48,0.08)',   border: 'rgba(200,48,48,0.20)',   label: 'Crítico'  },
}

function ini(nome: string) {
  return nome.split(' ').slice(0, 2).map((n) => n[0].toUpperCase()).join('')
}

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
    <div className="bg-white rounded-2xl overflow-hidden card-shadow card-border-hover"
      style={{ border: '1px solid var(--color-am-border)' }}>
      <div className="flex items-center justify-between px-4 py-3"
        style={{ borderBottom: '1px solid var(--color-am-border)', background: 'rgba(12,30,48,0.02)' }}>
        <div className="flex items-center gap-2">
          <span className="text-am-blue">{icon}</span>
          <span className="text-[10px] font-bold uppercase tracking-wider text-am-secondary">{title}</span>
        </div>
        {badge}
      </div>
      {children}
    </div>
  )
}

interface Props { onSelectCliente: (id: number) => void }

export default function PainelPage({ onSelectCliente }: Props) {
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
  const total      = clientes?.length ?? 0
  const totalProc  = clientes?.reduce((a, c) => a + c.total_processos, 0) ?? 0
  const emRisco    = clientes?.filter((c) => c.crm_nivel === 'alto' || c.crm_nivel === 'critico').length ?? 0
  const npsArr     = clientes?.map((c) => c.nps_medio).filter((n): n is number => n !== null) ?? []
  const npsMedia   = npsArr.length ? +(npsArr.reduce((a, b) => a + b, 0) / npsArr.length).toFixed(1) : null

  /* Ranking: em risco → sem NPS → ok, ordenado por último contato */
  const ranking = [...(clientes ?? [])].sort((a, b) => {
    const rA = a.crm_nivel === 'alto' || a.crm_nivel === 'critico' ? 0 : a.nps_medio === null ? 1 : 2
    const rB = b.crm_nivel === 'alto' || b.crm_nivel === 'critico' ? 0 : b.nps_medio === null ? 1 : 2
    if (rA !== rB) return rA - rB
    return (b.ultimo_contato ?? '').localeCompare(a.ultimo_contato ?? '')
  })

  /* Eficiência estimada (derivada dos dados disponíveis) */
  const semAnalise     = resumo?.sem_analise ?? 0
  const analisados     = total - semAnalise
  const autonomiaPct   = total > 0 ? Math.round((analisados / total) * 100) : 0
  const horasEconomiadas = +(analisados * 0.5).toFixed(1)

  /* Distribuição de risco */
  const niveis = ['baixo', 'moderado', 'alto', 'critico'] as const

  const daysSince = (iso: string | null) => {
    if (!iso) return null
    return Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000)
  }

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="p-4 max-w-3xl mx-auto space-y-4 page-enter">

        {/* ── Header + período ── */}
        <div className="flex items-end justify-between">
          <div>
            <h2 className="text-base font-extrabold text-am-ink tracking-tight">Painel de Resultados</h2>
            <p className="text-[11px] text-am-muted mt-0.5">Visão geral do escritório</p>
          </div>
          <div className="flex gap-1 p-0.5 rounded-xl" style={{ background: 'rgba(12,30,48,0.05)' }}>
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
        </div>

        {/* ── Exportar relatório ── */}
        <div className="flex items-center gap-2">
          <input
            type="month"
            value={mes}
            onChange={e => setMes(e.target.value)}
            className="flex-1 px-3 py-2 rounded-xl text-xs text-am-ink border border-am-border bg-white focus:outline-none focus:border-am-blue"
            style={{ fontFamily: 'var(--font-sans)' }}
          />
          <button
            onClick={() => exportMut.mutate()}
            disabled={exportMut.isPending}
            className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold text-white flex-shrink-0 transition-opacity"
            style={{
              background: 'linear-gradient(135deg,#1248BE,#3A7AB8)',
              opacity: exportMut.isPending ? 0.6 : 1,
              cursor: exportMut.isPending ? 'not-allowed' : 'pointer',
            }}>
            {exportMut.isPending
              ? <div className="w-3.5 h-3.5 rounded-full border-2 border-white border-t-transparent animate-spin" />
              : <Download size={13} />}
            {exportMut.isPending ? 'Exportando…' : 'Exportar CSV'}
          </button>
        </div>
        {exportMut.isError && (
          <p className="text-[11px] text-red-600 -mt-2">
            Erro ao exportar. Verifique se há dados para o mês selecionado.
          </p>
        )}

        {/* ── KPIs ── */}
        {isLoading ? (
          <div className="grid grid-cols-2 gap-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-24 rounded-2xl animate-pulse" style={{ background: 'rgba(12,30,48,0.05)' }} />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-3">
            {[
              { icon: <Users size={14} />,         label: 'Clientes ativos', value: total,     color: '#1248BE', sub: `${totalProc} processos` },
              { icon: <FileText size={14} />,      label: 'Processos',       value: totalProc, color: '#6B7CFF', sub: 'Total vinculados' },
              { icon: <AlertTriangle size={14} />, label: 'Em risco',        value: emRisco,   color: '#C83030', sub: 'Alto ou crítico', delta: emRisco > 0 ? emRisco : undefined },
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

        {/* ── Eficiência da IA ── */}
        <Section title="Eficiência da IA" icon={<Zap size={13} />}>
          <div className="p-4 space-y-4">
            <div className="grid grid-cols-3 gap-3">
              {[
                { label: 'Clientes analisados', value: `${analisados}/${total}`, color: '#1248BE' },
                { label: 'Autonomia IA',         value: `${autonomiaPct}%`,       color: autonomiaPct >= 70 ? '#1A9E78' : autonomiaPct >= 50 ? '#D08010' : '#C83030' },
                { label: 'Horas economizadas',   value: `${horasEconomiadas}h`,   color: '#6B7CFF' },
              ].map(({ label, value, color }) => (
                <div key={label} className="text-center py-2 px-3 rounded-xl"
                  style={{ background: `${color}08`, border: `1px solid ${color}18` }}>
                  <p className="text-base font-extrabold leading-none mb-1" style={{ color }}>{value}</p>
                  <p className="text-[10px] text-am-muted leading-tight">{label}</p>
                </div>
              ))}
            </div>

            {/* Barra de autonomia */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-[11px] text-am-secondary">Atendimentos resolvidos pela IA</span>
                <span className="text-[11px] font-bold" style={{ color: autonomiaPct >= 70 ? '#1A9E78' : autonomiaPct >= 50 ? '#D08010' : '#C83030' }}>
                  {autonomiaPct}%
                </span>
              </div>
              <Bar pct={autonomiaPct} color={autonomiaPct >= 70 ? '#1A9E78' : autonomiaPct >= 50 ? '#D08010' : '#C83030'} />
              <p className="text-[10px] text-am-muted mt-1">
                {analisados} de {total} clientes analisados sem intervenção manual
              </p>
            </div>
          </div>
        </Section>

        {/* ── Distribuição de risco ── */}
        {!isLoading && clientes && clientes.length > 0 && (
          <Section title="Distribuição de risco" icon={<Shield size={13} />}>
            <div className="p-4 space-y-3">
              {niveis.map((nivel) => {
                const count = resumo ? resumo[nivel] : (clientes.filter((c) => c.crm_nivel === nivel).length)
                const pct   = total > 0 ? Math.round((count / total) * 100) : 0
                const r     = RISK[nivel]
                return (
                  <div key={nivel} className="flex items-center gap-3">
                    <span className="text-[11px] font-semibold w-16 flex-shrink-0" style={{ color: r.color }}>
                      {r.label}
                    </span>
                    <Bar pct={pct} color={r.color} />
                    <span className="text-[11px] font-bold text-am-ink w-8 text-right flex-shrink-0">{count}</span>
                    <span className="text-[10px] text-am-muted w-8 flex-shrink-0">{pct}%</span>
                  </div>
                )
              })}
            </div>
          </Section>
        )}

        {/* ── Ranking de clientes ── */}
        <Section
          title="Ranking de clientes"
          icon={<TrendingUp size={13} />}
          badge={
            <span className="text-[10px] text-am-muted">Em risco primeiro</span>
          }
        >
          {isLoading ? (
            <div className="divide-y divide-am-border">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="flex items-center gap-3 px-4 py-3">
                  <div className="w-7 h-7 rounded-full animate-pulse flex-shrink-0"
                    style={{ background: 'rgba(12,30,48,0.06)' }} />
                  <div className="flex-1 space-y-1.5">
                    <div className="h-2.5 w-32 rounded animate-pulse" style={{ background: 'rgba(12,30,48,0.06)' }} />
                    <div className="h-2 w-20 rounded animate-pulse" style={{ background: 'rgba(12,30,48,0.04)' }} />
                  </div>
                </div>
              ))}
            </div>
          ) : ranking.length === 0 ? (
            <div className="flex flex-col items-center py-10 gap-2 text-am-muted">
              <Users size={20} strokeWidth={1.5} />
              <span className="text-xs">Sem clientes cadastrados</span>
            </div>
          ) : (
            <div className="divide-y divide-am-border">
              {ranking.map((c: CRMClienteCard) => {
                const emRiscoC = c.crm_nivel === 'alto' || c.crm_nivel === 'critico'
                const semNps   = c.nps_medio === null
                const r        = c.crm_nivel ? RISK[c.crm_nivel] : null
                const dias     = daysSince(c.ultimo_contato)

                return (
                  <motion.button
                    key={c.id}
                    onClick={() => onSelectCliente(c.id)}
                    whileHover={{ scale: 1.01 }}
                    whileTap={{ scale: 0.98 }}
                    transition={{ type: 'spring', stiffness: 400, damping: 28 }}
                    className="w-full flex items-center gap-3 px-4 py-3 text-left group row-in row-press">

                    {/* Avatar */}
                    <div className="w-8 h-8 rounded-xl flex items-center justify-center text-[11px] font-bold text-white flex-shrink-0"
                      style={{ background: emRiscoC ? '#C83030' : 'linear-gradient(135deg,#1248BE,#4A8ED4)' }}>
                      {ini(c.nome)}
                    </div>

                    {/* Info */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <p className="text-xs font-semibold text-am-ink truncate">{c.nome}</p>
                        {r && (
                          <span className="flex-shrink-0 text-[10px] font-semibold px-1.5 py-0.5 rounded-md"
                            style={{ color: r.color, background: r.bg, border: `1px solid ${r.border}` }}>
                            {r.label}
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-2 mt-0.5">
                        <span className="text-[10px] text-am-muted">
                          {c.total_processos} processo{c.total_processos !== 1 ? 's' : ''}
                        </span>
                        {dias !== null && (
                          <>
                            <span className="text-am-border">·</span>
                            <span className="flex items-center gap-0.5 text-[10px]"
                              style={{ color: dias > 14 ? '#C83030' : dias > 7 ? '#D08010' : 'var(--color-am-muted)' }}>
                              <Clock size={9} />
                              {dias === 0 ? 'hoje' : `há ${dias}d`}
                            </span>
                          </>
                        )}
                        {semNps && (
                          <>
                            <span className="text-am-border">·</span>
                            <span className="text-[10px] text-am-muted">sem NPS</span>
                          </>
                        )}
                        {c.nps_medio !== null && (
                          <>
                            <span className="text-am-border">·</span>
                            <span className="flex items-center gap-0.5 text-[10px] text-am-muted">
                              <Star size={9} style={{ color: '#D08010' }} />
                              {c.nps_medio.toFixed(1)}
                            </span>
                          </>
                        )}
                      </div>
                    </div>

                    <ArrowRight size={12} className="text-am-muted opacity-0 group-hover:opacity-100 transition-all flex-shrink-0" />
                  </motion.button>
                )
              })}
            </div>
          )}
        </Section>

      </div>
    </div>
  )
}
