import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'
import { BarChart3, RefreshCw, Loader2 } from 'lucide-react'
import { fetchProcessos } from '../api/processos'
import { analisarCliente, fetchClienteCRM } from '../api/crm'
import type { CRMClienteCard, Processo } from '../types'
import Skeleton from '../components/Skeleton'

const COMP_LABELS: Record<string, string> = {
  complexidade_juridica: 'Complexidade jurídica',
  duracao_estimada:      'Duração estimada',
  historico_vara:        'Histórico da vara',
  valor_causa:           'Valor da causa',
  fase_processual:       'Fase processual',
}

/* Cores semânticas Amicus */
const RISK_CFG: Record<string, { color: string; bg: string; border: string; label: string }> = {
  baixo:    { color: '#1A9E78', bg: 'rgba(26,158,120,0.07)',  border: 'rgba(26,158,120,0.22)',  label: 'Baixo Risco'    },
  moderado: { color: '#D08010', bg: 'rgba(208,128,16,0.07)',  border: 'rgba(208,128,16,0.22)',  label: 'Risco Moderado' },
  alto:     { color: '#C83030', bg: 'rgba(200,48,48,0.07)',   border: 'rgba(200,48,48,0.22)',   label: 'Alto Risco'     },
  critico:  { color: '#C83030', bg: 'rgba(200,48,48,0.07)',   border: 'rgba(200,48,48,0.22)',   label: 'Risco Crítico'  },
}

const RISK_DESC: Record<string, string> = {
  baixo:    'Condições favoráveis — o tipo de ação tem bom histórico neste tribunal e não há fatores agravantes identificados.',
  moderado: 'Há pontos de atenção que merecem acompanhamento próximo. Recomendamos manter o cliente bem informado sobre cada andamento.',
  alto:     'Fatores como complexidade da ação ou histórico desfavorável no tribunal aumentam a incerteza. Recomendamos alinhar as expectativas com clareza.',
  critico:  'Situação crítica. Ação imediata recomendada para mitigar riscos processuais e preservar os interesses do cliente.',
}

/* ── Gauge SVG circular ── */
function ScoreGauge({ value, color }: { value: number; color: string }) {
  const ref = useRef<SVGCircleElement>(null)
  const r    = 48
  const circ = 2 * Math.PI * r

  useEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.strokeDasharray = `0 ${circ}`
    const raf = requestAnimationFrame(() =>
      requestAnimationFrame(() => {
        el.style.strokeDasharray = `${(value / 100) * circ} ${circ}`
      })
    )
    return () => cancelAnimationFrame(raf)
  }, [value, circ])

  return (
    <div className="relative flex items-center justify-center flex-shrink-0" style={{ width: 112, height: 112 }}>
      <svg width="112" height="112" viewBox="0 0 112 112" className="absolute inset-0"
        style={{ transform: 'rotate(-90deg)' }}>
        <circle cx="56" cy="56" r={r} fill="none" stroke="var(--color-am-surface)" strokeWidth="9" />
        <circle ref={ref} cx="56" cy="56" r={r} fill="none"
          stroke={color} strokeWidth="9" strokeLinecap="round"
          style={{
            strokeDasharray: `0 ${circ}`,
            transition: 'stroke-dasharray 0.9s cubic-bezier(0.4,0,0.2,1)',
          }}
        />
      </svg>
      <div className="relative text-center z-10">
        <div className="text-2xl font-extrabold leading-none" style={{ color }}>{value}</div>
        <div className="text-[9px] font-bold uppercase tracking-wider mt-0.5 text-am-muted">/ 100</div>
      </div>
    </div>
  )
}

/* ── Barra de componente ── */
function ScoreBar({ value, color }: { value: number; color: string }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.width = '0%'
    const raf = requestAnimationFrame(() =>
      requestAnimationFrame(() => { el.style.width = `${value}%` })
    )
    return () => cancelAnimationFrame(raf)
  }, [value])

  return (
    <div className="h-1.5 rounded-full flex-1 overflow-hidden bg-am-surface">
      <div ref={ref} className="h-full rounded-full score-bar-fill"
        style={{ background: color, width: '0%' }} />
    </div>
  )
}

/* ── Visão geral ── */
function ScoreOverview({ processo }: { processo: Processo }) {
  const nivel = processo.score_nivel ?? 'baixo'
  const valor = processo.score_risco ?? 0
  const cfg   = RISK_CFG[nivel] ?? RISK_CFG.baixo
  const desc  = processo.score_interpretacao ?? RISK_DESC[nivel] ?? ''

  return (
    <div className="bg-white rounded-xl overflow-hidden card-shadow"
      style={{ border: `1px solid ${cfg.border}`, borderLeft: `3px solid ${cfg.color}` }}>

      {/* Cabeçalho do card */}
      <div className="flex items-center gap-2 px-4 sm:px-5 py-3"
        style={{ background: cfg.bg, borderBottom: `1px solid ${cfg.border}` }}>
        <BarChart3 size={13} style={{ color: cfg.color }} />
        <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: cfg.color }}>
          Score de Risco — {cfg.label}
        </span>
      </div>

      {/* Gauge + info */}
      <div className="flex flex-col sm:flex-row items-center gap-5 sm:gap-8 px-4 sm:px-6 py-5">
        <ScoreGauge value={valor} color={cfg.color} />
        <div className="flex-1 w-full min-w-0">
          {/* Mini barra */}
          <div className="mb-3">
            <ScoreBar value={valor} color={cfg.color} />
            <div className="flex justify-between mt-1">
              <span className="text-[9px] text-am-muted font-medium">0 — Favorável</span>
              <span className="text-[9px] text-am-muted font-medium">100 — Crítico</span>
            </div>
          </div>
          <p className="text-xs text-am-secondary leading-relaxed">{desc}</p>
        </div>
      </div>
    </div>
  )
}

export default function ScoreTab({ cliente }: { cliente: CRMClienteCard }) {
  const qc = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['processos', cliente.id],
    queryFn: () => fetchProcessos(cliente.id),
    enabled: cliente.total_processos > 0,
  })
  const processo: Processo | null = data?.items[0] ?? null

  const analisarMut = useMutation({
    mutationFn: () => analisarCliente(cliente.id),
    onSuccess: async () => {
      const atualizado = await fetchClienteCRM(cliente.id)
      qc.setQueryData<CRMClienteCard[]>(['clientes'], (prev) =>
        prev?.map((c) => (c.id === cliente.id ? atualizado : c)) ?? prev
      )
      qc.invalidateQueries({ queryKey: ['processos', cliente.id] })
    },
  })

  if (isLoading) return (
    <div className="p-4 sm:p-6 space-y-4">
      <Skeleton className="h-40 w-full" />
      <Skeleton className="h-32 w-full" />
    </div>
  )

  if (!processo?.score_risco) return (
    <div className="flex flex-col items-center justify-center py-20 gap-4 px-6 text-center">
      <div className="w-14 h-14 rounded-2xl flex items-center justify-center bg-am-surface border border-am-border">
        <BarChart3 size={26} strokeWidth={1.5} className="text-am-blue" />
      </div>
      <div>
        <div className="text-sm font-bold text-am-ink mb-1">Score indisponível</div>
        <div className="text-xs text-am-muted max-w-xs leading-relaxed">
          {cliente.total_processos === 0
            ? 'É necessário um processo judicial vinculado para gerar a análise de risco.'
            : 'O score ainda está sendo processado. Aguarde alguns instantes.'}
        </div>
      </div>
      {cliente.total_processos > 0 && (
        <button
          onClick={() => analisarMut.mutate()}
          disabled={analisarMut.isPending}
          className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-white text-xs font-bold transition-fast disabled:opacity-50"
          style={{ background: 'var(--color-am-blue)' }}
        >
          {analisarMut.isPending
            ? <><Loader2 size={13} className="animate-spin" /> Analisando…</>
            : <><RefreshCw size={13} /> Gerar análise de risco</>}
        </button>
      )}
      {analisarMut.isError && (
        <p className="text-xs" style={{ color: '#C83030' }}>
          Erro ao gerar análise. Tente novamente.
        </p>
      )}
    </div>
  )

  const componentes = processo.score_componentes ?? {}
  const colorComp   = (v: number) => v >= 65 ? '#C83030' : v >= 40 ? '#D08010' : '#1A9E78'
  const labelComp   = (v: number) => v >= 65 ? 'Desfavorável' : v >= 40 ? 'Atenção' : 'Favorável'

  return (
    <div className="p-4 sm:p-6 space-y-4">
      <ScoreOverview processo={processo} />

      {Object.keys(componentes).length > 0 && (
        <details className="group" open>
          <summary className="flex items-center gap-2 px-1 py-2 cursor-pointer select-none list-none">
            <span className="text-[9px] font-bold uppercase tracking-widest text-am-muted">
              Componentes da análise
            </span>
            <span className="text-am-blue text-xs font-semibold ml-auto group-open:hidden">ver ›</span>
            <span className="text-am-blue text-xs font-semibold ml-auto hidden group-open:block">ocultar ‹</span>
          </summary>

          <div className="bg-white rounded-xl border border-am-border overflow-hidden card-shadow mt-1">
            <div className="px-4 sm:px-5 py-4 space-y-4">
              {Object.entries(componentes).map(([key, val]) => (
                <div key={key} className="space-y-1.5">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-medium text-am-secondary truncate">
                      {COMP_LABELS[key] ?? key}
                    </span>
                    {/* Badge semântico: bg baixa opacidade + texto saturado */}
                    <span
                      className="text-[10px] font-bold px-2 py-0.5 rounded-md flex-shrink-0"
                      style={{
                        color: colorComp(val),
                        background: `${colorComp(val)}12`,
                        border: `1px solid ${colorComp(val)}30`,
                      }}
                    >
                      {labelComp(val)}
                    </span>
                  </div>
                  <ScoreBar value={val} color={colorComp(val)} />
                </div>
              ))}
            </div>
            <div className="flex items-center justify-between gap-3 px-4 sm:px-5 py-3 border-t border-am-border bg-am-bg">
              <p className="text-[10px] text-am-muted leading-relaxed">
                Esta análise é de uso interno e não representa previsão de resultado processual (OAB Provimento 205/2021).
              </p>
              <button
                onClick={() => analisarMut.mutate()}
                disabled={analisarMut.isPending}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[10px] font-bold flex-shrink-0 transition-fast disabled:opacity-50"
                style={{ color: 'var(--color-am-blue)', background: 'rgba(18,72,190,0.07)', border: '1px solid rgba(18,72,190,0.18)' }}
              >
                {analisarMut.isPending
                  ? <><Loader2 size={11} className="animate-spin" /> Analisando…</>
                  : <><RefreshCw size={11} /> Atualizar</>}
              </button>
            </div>
          </div>
        </details>
      )}
    </div>
  )
}
