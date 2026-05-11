/* Badge pattern Amicus: fundo cor em baixíssima opacidade + texto saturado */

interface Props {
  nivel: string | null
  score?: number | null
  size?: 'sm' | 'md'
}

const CONFIG: Record<string, { color: string; bg: string; border: string; label: string }> = {
  baixo:    { color: '#1A9E78', bg: 'rgba(26,158,120,0.08)',  border: 'rgba(26,158,120,0.22)',  label: 'Baixo'    },
  moderado: { color: '#D08010', bg: 'rgba(208,128,16,0.08)',  border: 'rgba(208,128,16,0.22)',  label: 'Moderado' },
  alto:     { color: '#C83030', bg: 'rgba(200,48,48,0.08)',   border: 'rgba(200,48,48,0.22)',   label: 'Alto'     },
  critico:  { color: '#C83030', bg: 'rgba(200,48,48,0.08)',   border: 'rgba(200,48,48,0.22)',   label: 'Crítico'  },
}

export default function RiskChip({ nivel, score, size = 'sm' }: Props) {
  if (!nivel) return <span className="text-xs text-am-muted">—</span>

  const cfg = CONFIG[nivel] ?? { color: '#8AAAC0', bg: 'rgba(138,170,192,0.08)', border: 'rgba(138,170,192,0.2)', label: nivel }
  const isMd = size === 'md'

  return (
    <span
      className="inline-flex items-center gap-1.5 font-semibold rounded-lg"
      style={{
        color: cfg.color,
        background: cfg.bg,
        border: `1px solid ${cfg.border}`,
        padding: isMd ? '4px 10px' : '2px 7px',
        fontSize: isMd ? '11px' : '10px',
      }}
    >
      <span
        className="rounded-full flex-shrink-0"
        style={{ width: isMd ? 6 : 5, height: isMd ? 6 : 5, background: cfg.color }}
      />
      {score != null && <span className="font-bold">{score}</span>}
      {cfg.label}
    </span>
  )
}
