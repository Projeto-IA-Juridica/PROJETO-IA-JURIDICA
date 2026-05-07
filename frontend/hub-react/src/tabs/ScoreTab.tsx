import { useQuery } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'
import { BarChart3 } from 'lucide-react'
import { fetchProcessos } from '../api/processos'
import type { CRMClienteCard, Processo } from '../types'
import Skeleton from '../components/Skeleton'

const COMP_LABELS: Record<string, string> = {
  complexidade_juridica: 'Complexidade jurídica',
  duracao_estimada:      'Duração estimada',
  historico_vara:        'Histórico da vara',
  valor_causa:           'Valor da causa',
  fase_processual:       'Fase processual',
}

const RISK_COLOR: Record<string, string> = {
  baixo:    '#1A9E78',
  moderado: '#D08010',
  alto:     '#C83030',
  critico:  '#C83030',
}

const RISK_DESC: Record<string, string> = {
  baixo:    'Condições favoráveis — o tipo de ação tem bom histórico neste tribunal e não há fatores agravantes identificados.',
  moderado: 'Há pontos de atenção que merecem acompanhamento próximo. Recomendamos manter o cliente bem informado sobre cada andamento.',
  alto:     'Fatores como complexidade da ação ou histórico desfavorável no tribunal aumentam a incerteza. Vale redobrar a atenção e alinhar as expectativas com clareza.',
  critico:  'Situação crítica. Ação imediata recomendada para mitigar riscos processuais e preservar os interesses do cliente.',
}

function ScoreBar({ value, color }: { value: number; color: string }) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.width = '0%'
    const raf = requestAnimationFrame(() => {
      requestAnimationFrame(() => { el.style.width = `${value}%` })
    })
    return () => cancelAnimationFrame(raf)
  }, [value])

  return (
    <div className="h-1.5 rounded-full bg-am-surface overflow-hidden flex-1">
      <div
        ref={ref}
        className="h-full rounded-full score-bar-fill"
        style={{ background: color, width: '0%' }}
      />
    </div>
  )
}

function ScoreOverview({ processo }: { processo: Processo }) {
  const nivel = processo.score_nivel ?? 'baixo'
  const valor = processo.score_risco ?? 0
  const color = RISK_COLOR[nivel] ?? '#8AAAC0'
  const desc = processo.score_interpretacao ?? RISK_DESC[nivel] ?? ''

  return (
    <div
      className="bg-white rounded-xl border border-am-border overflow-hidden"
      style={{ borderLeft: `3px solid ${color}` }}
    >
      <div className="px-5 py-4 flex items-start gap-6">
        <div className="flex-shrink-0 text-center">
          <div className="text-4xl font-bold" style={{ color }}>{valor}</div>
          <div className="text-xs font-semibold mt-1" style={{ color }}>
            {nivel.charAt(0).toUpperCase() + nivel.slice(1)}
          </div>
        </div>
        <div className="flex-1 pt-1">
          <div className="mb-3">
            <ScoreBar value={valor} color={color} />
          </div>
          <p className="text-xs text-am-secondary leading-relaxed">{desc}</p>
        </div>
      </div>
    </div>
  )
}

export default function ScoreTab({ cliente }: { cliente: CRMClienteCard }) {
  const { data, isLoading } = useQuery({
    queryKey: ['processos', cliente.id],
    queryFn: () => fetchProcessos(cliente.id),
    enabled: cliente.total_processos > 0,
  })

  const processo: Processo | null = data?.items[0] ?? null

  if (isLoading) {
    return (
      <div className="p-6 space-y-4">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-32 w-full" />
      </div>
    )
  }

  if (!processo?.score_risco) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3 text-am-muted">
        <BarChart3 size={36} strokeWidth={1.5} />
        <div className="text-sm font-medium text-am-secondary">Score indisponível</div>
        <div className="text-xs text-center max-w-xs">
          {cliente.total_processos === 0
            ? 'Processo judicial necessário para gerar a análise de risco.'
            : 'O score ainda está sendo processado. Aguarde.'}
        </div>
      </div>
    )
  }

  const componentes = processo.score_componentes ?? {}
  const nivelComps = (val: number) => val >= 65 ? 'Desfavorável' : val >= 40 ? 'Atenção' : 'Favorável'
  const colorComp = (val: number) => val >= 65 ? '#C83030' : val >= 40 ? '#D08010' : '#1A9E78'

  return (
    <div className="p-6 space-y-4">
      <ScoreOverview processo={processo} />

      <details className="group" open>
        <summary className="flex items-center gap-2 px-1 py-2 cursor-pointer text-xs font-semibold text-am-blue
          select-none list-none">
          <span className="transition-transform duration-200 group-open:rotate-90 text-base leading-none">›</span>
          Como chegamos a esta análise? Ver detalhes
        </summary>

        <div className="bg-white rounded-xl border border-am-border overflow-hidden mt-1">
          <div className="px-5 py-3.5 border-b border-am-border">
            <span className="text-[10px] font-semibold text-am-muted uppercase tracking-wider">
              Detalhamento dos componentes
            </span>
          </div>
          <div className="px-5 py-4 space-y-4">
            {Object.entries(componentes).map(([key, val]) => (
              <div key={key} className="flex items-center gap-4">
                <div className="w-36 text-xs text-am-secondary flex-shrink-0">
                  {COMP_LABELS[key] ?? key}
                </div>
                <ScoreBar value={val} color={colorComp(val)} />
                <div className="w-20 text-[10px] font-semibold text-right flex-shrink-0"
                  style={{ color: colorComp(val) }}>
                  {nivelComps(val)}
                </div>
              </div>
            ))}

            <p className="pt-2 border-t border-am-border text-[10px] text-am-muted leading-relaxed">
              Esta análise é de uso interno e não representa previsão de resultado processual (OAB Provimento 205/2021).
            </p>
          </div>
        </div>
      </details>
    </div>
  )
}
