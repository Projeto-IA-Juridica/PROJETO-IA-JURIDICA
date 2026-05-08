import { useQuery } from '@tanstack/react-query'
import { Users, FileText, AlertTriangle, Star, TrendingUp, Clock, ArrowRight, Shield } from 'lucide-react'
import { fetchClientes } from '../api/crm'
import type { CRMClienteCard } from '../types'

const RISK_COLOR: Record<string, { color: string; bg: string; border: string }> = {
  baixo:    { color: '#1A9E78', bg: 'rgba(26,158,120,0.08)',  border: 'rgba(26,158,120,0.22)'  },
  moderado: { color: '#D08010', bg: 'rgba(208,128,16,0.08)',  border: 'rgba(208,128,16,0.22)'  },
  alto:     { color: '#C83030', bg: 'rgba(200,48,48,0.08)',   border: 'rgba(200,48,48,0.22)'   },
  critico:  { color: '#C83030', bg: 'rgba(200,48,48,0.08)',   border: 'rgba(200,48,48,0.22)'   },
}

const RISK_LABEL: Record<string, string> = {
  baixo: 'Baixo', moderado: 'Moderado', alto: 'Alto', critico: 'Crítico',
}

interface Props {
  onSelectCliente: (id: number) => void
}

function initials(nome: string) {
  return nome.split(' ').slice(0, 2).map((n) => n[0].toUpperCase()).join('')
}

function StatCard({ icon, label, value, color, sub }: {
  icon: React.ReactNode; label: string; value: number | string; color: string; sub?: string
}) {
  return (
    <div className="bg-white rounded-2xl p-4 sm:p-5 card-shadow border border-am-border flex flex-col gap-3 card-in card-border-hover">
      <div className="flex items-center justify-between">
        <div className="text-[10px] font-bold uppercase tracking-widest text-am-muted">{label}</div>
        <div className="w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0"
          style={{ background: `color-mix(in srgb, ${color} 10%, transparent)`, color }}>
          {icon}
        </div>
      </div>
      <div className="text-2xl sm:text-3xl font-extrabold leading-none" style={{ color }}>{value}</div>
      {sub && <div className="text-[10px] text-am-muted font-medium">{sub}</div>}
    </div>
  )
}

export default function PainelPage({ onSelectCliente }: Props) {
  const { data: clientes, isLoading } = useQuery({
    queryKey: ['clientes'],
    queryFn: fetchClientes,
    staleTime: 60_000,
  })

  const total        = clientes?.length ?? 0
  const totalProc    = clientes?.reduce((a, c) => a + c.total_processos, 0) ?? 0
  const emRisco      = clientes?.filter((c) => c.crm_nivel === 'alto' || c.crm_nivel === 'critico').length ?? 0
  const npsArr       = clientes?.map((c) => c.nps_medio).filter((n): n is number => n !== null) ?? []
  const npsMedia     = npsArr.length ? Math.round(npsArr.reduce((a, b) => a + b, 0) / npsArr.length) : null
  const recentes     = [...(clientes ?? [])].sort((a, b) =>
    (b.ultimo_contato ?? '').localeCompare(a.ultimo_contato ?? '')
  ).slice(0, 5)
  const alertas      = clientes?.filter((c) => c.crm_nivel === 'critico' || c.crm_nivel === 'alto') ?? []

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="p-4 sm:p-6 max-w-5xl mx-auto space-y-6 page-enter">

        {/* Header */}
        <div>
          <h2 className="text-lg font-extrabold text-am-ink tracking-tight">Painel de Resultados</h2>
          <p className="text-xs text-am-muted mt-0.5">Visão geral do escritório em tempo real</p>
        </div>

        {/* KPIs */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
          {isLoading ? (
            Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-28 rounded-2xl skeleton" style={{ background: 'rgba(58,122,184,0.06)' }} />
            ))
          ) : (
            <>
              <StatCard icon={<Users size={15} />}       label="Clientes"       value={total}     color="var(--color-am-blue)"  sub={`${totalProc} processo${totalProc !== 1 ? 's' : ''}`} />
              <StatCard icon={<FileText size={15} />}    label="Processos"      value={totalProc} color="var(--color-am-secondary)" sub="Total vinculados" />
              <StatCard icon={<AlertTriangle size={15} />} label="Em risco"     value={emRisco}   color="var(--color-am-red)"   sub="Alto ou crítico" />
              <StatCard icon={<Star size={15} />}        label="NPS médio"      value={npsMedia !== null ? `${npsMedia}%` : '—'} color="var(--color-am-green)" sub="Satisfação geral" />
            </>
          )}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6">

          {/* Alertas */}
          <div className="bg-white rounded-2xl card-shadow border border-am-border overflow-hidden card-border-hover">
            <div className="flex items-center justify-between px-5 py-3.5 border-b border-am-border bg-am-bg">
              <div className="flex items-center gap-2">
                <Shield size={13} className="text-am-red" />
                <span className="text-[10px] font-bold uppercase tracking-widest text-am-secondary">
                  Alertas de risco
                </span>
              </div>
              {alertas.length > 0 && (
                <span className="text-[9px] font-bold px-1.5 py-0.5 rounded"
                  style={{ background: 'rgba(200,48,48,0.1)', color: '#C83030' }}>
                  {alertas.length}
                </span>
              )}
            </div>

            {alertas.length === 0 ? (
              <div className="flex flex-col items-center py-10 gap-2 text-am-muted">
                <Shield size={22} strokeWidth={1.5} />
                <span className="text-xs">Sem alertas críticos</span>
              </div>
            ) : (
              <div className="divide-y divide-am-border">
                {alertas.slice(0, 6).map((c) => {
                  const r = RISK_COLOR[c.crm_nivel ?? ''] ?? RISK_COLOR.moderado
                  return (
                    <button key={c.id} onClick={() => onSelectCliente(c.id)}
                      className="w-full flex items-center gap-3 px-5 py-3 text-left hover:bg-am-bg row-press row-in group">
                      <div className="w-7 h-7 rounded-full flex items-center justify-center text-[10px] font-bold flex-shrink-0 text-white"
                        style={{ background: r.color }}>
                        {initials(c.nome)}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-xs font-semibold text-am-ink truncate">{c.nome}</div>
                        <div className="text-[10px] text-am-muted mt-0.5 truncate line-clamp-1">
                          {c.crm_acao_sugerida ?? 'Requer atenção imediata'}
                        </div>
                      </div>
                      <div className="flex items-center gap-2 flex-shrink-0">
                        <span className="text-[9px] font-bold px-1.5 py-0.5 rounded"
                          style={{ color: r.color, background: r.bg, border: `1px solid ${r.border}` }}>
                          {RISK_LABEL[c.crm_nivel ?? ''] ?? c.crm_nivel}
                        </span>
                        <ArrowRight size={11} className="text-am-muted opacity-0 group-hover:opacity-100 transition-fast" />
                      </div>
                    </button>
                  )
                })}
              </div>
            )}
          </div>

          {/* Atividade recente */}
          <div className="bg-white rounded-2xl card-shadow border border-am-border overflow-hidden card-border-hover">
            <div className="flex items-center gap-2 px-5 py-3.5 border-b border-am-border bg-am-bg">
              <Clock size={13} className="text-am-blue" />
              <span className="text-[10px] font-bold uppercase tracking-widest text-am-secondary">
                Contatos recentes
              </span>
            </div>

            {isLoading ? (
              <div className="divide-y divide-am-border">
                {Array.from({ length: 4 }).map((_, i) => (
                  <div key={i} className="flex items-center gap-3 px-5 py-3.5">
                    <div className="w-7 h-7 rounded-full skeleton flex-shrink-0" style={{ background: 'rgba(58,122,184,0.08)' }} />
                    <div className="flex-1 space-y-1.5">
                      <div className="h-2.5 w-32 rounded skeleton" style={{ background: 'rgba(58,122,184,0.08)' }} />
                      <div className="h-2 w-20 rounded skeleton" style={{ background: 'rgba(58,122,184,0.06)' }} />
                    </div>
                  </div>
                ))}
              </div>
            ) : recentes.length === 0 ? (
              <div className="flex flex-col items-center py-10 gap-2 text-am-muted">
                <TrendingUp size={22} strokeWidth={1.5} />
                <span className="text-xs">Nenhuma atividade registrada</span>
              </div>
            ) : (
              <div className="divide-y divide-am-border">
                {recentes.map((c: CRMClienteCard) => {
                  const r = c.crm_nivel ? (RISK_COLOR[c.crm_nivel] ?? null) : null
                  const data = c.ultimo_contato
                    ? new Date(c.ultimo_contato).toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' })
                    : null
                  return (
                    <button key={c.id} onClick={() => onSelectCliente(c.id)}
                      className="w-full flex items-center gap-3 px-5 py-3 text-left hover:bg-am-bg row-press row-in group">
                      <div className="w-7 h-7 rounded-full flex items-center justify-center text-[10px] font-bold flex-shrink-0"
                        style={{ background: 'var(--color-am-surface)', color: 'var(--color-am-blue)' }}>
                        {initials(c.nome)}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-xs font-semibold text-am-ink truncate">{c.nome}</div>
                        <div className="text-[10px] text-am-muted mt-0.5">
                          {c.total_processos} processo{c.total_processos !== 1 ? 's' : ''}
                          {data && <span className="mx-1">·</span>}
                          {data && <span>{data}</span>}
                        </div>
                      </div>
                      <div className="flex items-center gap-2 flex-shrink-0">
                        {r && (
                          <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: r.color }} />
                        )}
                        <ArrowRight size={11} className="text-am-muted opacity-0 group-hover:opacity-100 transition-fast" />
                      </div>
                    </button>
                  )
                })}
              </div>
            )}
          </div>
        </div>

        {/* Mini distribuição de risco */}
        {!isLoading && clientes && clientes.length > 0 && (
          <div className="bg-white rounded-2xl card-shadow border border-am-border p-5 card-border-hover">
            <div className="flex items-center gap-2 mb-4">
              <TrendingUp size={13} className="text-am-blue" />
              <span className="text-[10px] font-bold uppercase tracking-widest text-am-secondary">
                Distribuição por nível de risco
              </span>
            </div>
            <div className="flex gap-3 flex-wrap">
              {(['baixo', 'moderado', 'alto', 'critico'] as const).map((nivel) => {
                const count = clientes.filter((c) => c.crm_nivel === nivel).length
                const pct   = total > 0 ? Math.round((count / total) * 100) : 0
                const r     = RISK_COLOR[nivel]
                return (
                  <div key={nivel} className="flex-1 min-w-[80px]">
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="text-[10px] font-semibold" style={{ color: r.color }}>
                        {RISK_LABEL[nivel]}
                      </span>
                      <span className="text-[10px] font-bold text-am-ink">{count}</span>
                    </div>
                    <div className="h-1.5 rounded-full overflow-hidden" style={{ background: r.bg }}>
                      <div className="h-full rounded-full transition-all duration-500"
                        style={{ width: `${pct}%`, background: r.color }} />
                    </div>
                    <div className="text-[9px] text-am-muted mt-1">{pct}%</div>
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
