interface Props {
  nivel: string | null
  score?: number | null
  size?: 'sm' | 'md'
}

const COLOR: Record<string, string> = {
  baixo:    '#1A9E78',
  moderado: '#D08010',
  alto:     '#C83030',
  critico:  '#C83030',
}

const LABEL: Record<string, string> = {
  baixo:    'Baixo',
  moderado: 'Moderado',
  alto:     'Alto',
  critico:  'Crítico',
}

export default function RiskChip({ nivel, score, size = 'sm' }: Props) {
  if (!nivel) return <span className="text-xs text-am-muted">—</span>

  const color = COLOR[nivel] ?? '#8AAAC0'
  const label = LABEL[nivel] ?? nivel
  const pad = size === 'sm' ? 'px-2 py-0.5 text-[10px]' : 'px-2.5 py-1 text-xs'

  return (
    <span
      className={`inline-flex items-center gap-1 font-semibold rounded-md ${pad}`}
      style={{ color, background: `${color}10`, border: `1px solid ${color}28` }}
    >
      {score != null && <span>{score}</span>}
      {label}
    </span>
  )
}
