import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { analyticsApi } from '../api/analytics'
import { MetricCard, ProgressBar, ErrorBox, SkeletonGrid } from '../components/ui'

type Dias = 7 | 30 | 90

function WeeklyChart({ tendencia }: { tendencia: Array<{ semana: string; total_interacoes: number; nps_medio: number | null; autonomia_pct: number }> }) {
  if (!tendencia?.length) return null
  const maxVal = Math.max(...tendencia.map(t => t.total_interacoes), 1)
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 4, height: 80 }}>
        {tendencia.map((t, i) => {
          const h = (t.total_interacoes / maxVal) * 100
          const cor = (t.nps_medio ?? 3) >= 4 ? 'var(--success)' : (t.nps_medio ?? 3) >= 3 ? 'var(--warning)' : 'var(--danger)'
          const semLabel = t.semana.includes('-W') ? `W${t.semana.split('-W')[1]}` : t.semana
          return (
            <div key={i} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2, height: '100%', justifyContent: 'flex-end' }}>
              <span style={{ fontSize: 9, color: 'var(--text-muted)' }}>{t.total_interacoes}</span>
              <div
                title={`${t.semana}: ${t.total_interacoes} interações, NPS ${t.nps_medio ?? '?'}`}
                style={{ width: '100%', background: cor, borderRadius: '3px 3px 0 0', minHeight: 2, height: `${Math.max(h, 3)}%`, opacity: 0.8 }}
              />
              <span style={{ fontSize: 9, color: 'var(--text-muted)' }}>{semLabel}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default function AnalyticsPage() {
  const [dias, setDias] = useState<Dias>(30)
  const [activeTab, setActiveTab] = useState<'dashboard' | 'export'>('dashboard')
  const [mesExport, setMesExport] = useState(() => new Date().toISOString().slice(0, 7))

  const { data, isLoading, error } = useQuery({
    queryKey: ['dashboard', dias],
    queryFn: () => analyticsApi.dashboard(dias),
    staleTime: 5 * 60 * 1000, // 5 min cache
    placeholderData: (prev) => prev,
  })

  const handleExport = async () => {
    const blob = await analyticsApi.exportCsv(mesExport)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `relatorio_${mesExport}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  if (error) return <ErrorBox message="Falha ao carregar analytics." />

  return (
    <>
      <div className="page-header">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <h1 className="page-title">Analytics</h1>
            <p className="page-subtitle">Satisfação, eficiência e custo</p>
          </div>
          <div style={{ display: 'flex', gap: 3 }}>
            {([7, 30, 90] as Dias[]).map(d => (
              <button key={d} className={`btn btn-sm ${dias === d ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setDias(d)}>
                {d}d
              </button>
            ))}
          </div>
        </div>
      </div>

      <div style={{ borderBottom: '1px solid var(--surface-border)', marginBottom: 20, display: 'flex' }}>
        <button className={`tab ${activeTab === 'dashboard' ? 'active' : ''}`} onClick={() => setActiveTab('dashboard')}>Dashboard</button>
        <button className={`tab ${activeTab === 'export' ? 'active' : ''}`} onClick={() => setActiveTab('export')}>Exportar CSV</button>
      </div>

      {activeTab === 'dashboard' && (
        <>
          {isLoading && !data ? <SkeletonGrid count={6} /> : data && (
            <>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 10, marginBottom: 20 }}>
                <MetricCard value={data.resumo.total_interacoes} label="Interações" />
                <MetricCard value={data.resumo.clientes_ativos} label="Clientes Ativos" />
                <MetricCard value={`${data.resumo.nps_medio.toFixed(1)}`} label="NPS Médio" delta={data.resumo.variacao_nps} deltaSign="auto" />
                <MetricCard value={`${data.eficiencia.percentual_autonomia.toFixed(0)}%`} label="Autonomia IA" />
                <MetricCard value={`$${data.eficiencia.custo_total_usd.toFixed(4)}`} label="Custo Claude" />
              </div>

              <div className="surface" style={{ padding: 18, marginBottom: 14 }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 12 }}>Eficiência da IA</div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginBottom: 12 }}>
                  <MetricCard value={`${data.eficiencia.tempo_resposta_medio_ms ?? '—'}ms`} label="Tempo Resposta" />
                  <MetricCard value={data.eficiencia.interacoes_sem_humano ?? 0} label="Sem Humano" />
                  <MetricCard value={`${data.eficiencia.horas_economizadas_estimadas?.toFixed(1) ?? 0}h`} label="Economizadas" />
                </div>
                <div style={{ marginBottom: 3 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 3 }}>
                    <span style={{ color: 'var(--text-secondary)' }}>Autonomia</span>
                    <span style={{ fontWeight: 600 }}>{data.eficiencia.percentual_autonomia?.toFixed(0) ?? 0}%</span>
                  </div>
                  <ProgressBar value={data.eficiencia.percentual_autonomia ?? 0} max={100} height={5} />
                </div>
              </div>

              {data.tendencia_semanal && (
                <div className="surface" style={{ padding: 18, marginBottom: 14 }}>
                  <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 12 }}>Tendência Semanal</div>
                  <WeeklyChart tendencia={data.tendencia_semanal} />
                </div>
              )}

              {data.por_cliente && (
                <div className="surface" style={{ padding: 18 }}>
                  <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 12 }}>
                    Ranking — Em Risco Primeiro
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                    {data.por_cliente.map((r, i) => (
                      <div key={i} style={{
                        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                        padding: '6px 10px', borderRadius: 6,
                        background: r.em_risco ? 'var(--danger-surface)' : r.sem_avaliacao ? 'rgba(245, 158, 11, 0.06)' : 'var(--surface-overlay)',
                        border: `1px solid ${r.em_risco ? 'var(--danger-border)' : r.sem_avaliacao ? 'rgba(245, 158, 11, 0.15)' : 'var(--surface-border)'}`,
                        fontSize: 12,
                      }}>
                        <div>
                          <span style={{ fontWeight: 500 }}>{r.nome}</span>
                          <span style={{ marginLeft: 8, fontSize: 11, color: r.em_risco ? 'var(--danger)' : r.sem_avaliacao ? 'var(--warning)' : 'var(--success)' }}>
                            {r.em_risco ? 'Em Risco' : r.sem_avaliacao ? 'Sem Avaliação' : 'Ok'}
                          </span>
                        </div>
                        <div style={{ fontSize: 11, color: 'var(--text-muted)', display: 'flex', gap: 12 }}>
                          <span>NPS: <strong style={{ color: 'var(--text-secondary)' }}>{r.nps_medio != null ? r.nps_medio.toFixed(1) : '—'}</strong></span>
                          <span>{r.total_interacoes} msgs</span>
                          <span>{r.ultimo_contato ? new Date(r.ultimo_contato).toLocaleDateString('pt-BR') : '—'}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </>
      )}

      {activeTab === 'export' && (
        <div className="surface" style={{ padding: 20, maxWidth: 420 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>Exportar Relatório</div>
          <p style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 14, lineHeight: 1.5 }}>
            CSV com interações do mês selecionado.
          </p>
          <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
            <div style={{ flex: 1 }}>
              <label className="label">Mês</label>
              <input className="input" type="month" value={mesExport} onChange={e => setMesExport(e.target.value)} />
            </div>
            <button className="btn btn-primary" onClick={handleExport}>Baixar CSV</button>
          </div>
        </div>
      )}
    </>
  )
}
