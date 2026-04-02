// Badge de nível CRM/risco
export type NivelCRM = 'excelente' | 'satisfeito' | 'neutro' | 'em_risco' | 'critico'
export type NivelRisco = 'baixo' | 'moderado' | 'alto' | 'critico'

const CRM_STYLES: Record<string, string> = {
  excelente: 'badge-success',
  satisfeito: 'badge-success',
  neutro: 'badge-warning',
  em_risco: 'badge-danger',
  critico: 'badge-danger',
}
const RISCO_STYLES: Record<string, string> = {
  baixo: 'badge-success',
  moderado: 'badge-warning',
  alto: 'badge-danger',
  critico: 'badge-purple',
}
const CRM_LABEL: Record<string, string> = {
  excelente: 'Excelente', satisfeito: 'Satisfeito', neutro: 'Neutro',
  em_risco: 'Em Risco', critico: 'Crítico',
}
const RISCO_LABEL: Record<string, string> = {
  baixo: 'Baixo', moderado: 'Moderado', alto: 'Alto', critico: 'Crítico',
}

export function BadgeCRM({ nivel }: { nivel: NivelCRM | null | undefined }) {
  if (!nivel) return <span className="badge badge-muted">Sem análise</span>
  return <span className={`badge ${CRM_STYLES[nivel] ?? 'badge-muted'}`}>{CRM_LABEL[nivel] ?? nivel}</span>
}

export function BadgeRisco({ nivel }: { nivel: string | null | undefined }) {
  if (!nivel) return null
  return <span className={`badge ${RISCO_STYLES[nivel] ?? 'badge-muted'}`}>{RISCO_LABEL[nivel] ?? nivel}</span>
}

export function BadgeStatus({ ativo }: { ativo: boolean }) {
  return ativo
    ? <span className="badge badge-success">Ativo</span>
    : <span className="badge badge-muted">Inativo</span>
}

// ProgressBar
interface ProgressBarProps { value: number; max?: number; color?: string; height?: number }
export function ProgressBar({ value, max = 100, color, height = 5 }: ProgressBarProps) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100))
  const barColor = color ?? (pct >= 70 ? 'var(--success)' : pct >= 40 ? 'var(--warning)' : 'var(--danger)')
  return (
    <div className="progress-track" style={{ height }}>
      <div className="progress-fill" style={{ width: `${pct}%`, background: barColor, height }} />
    </div>
  )
}

// MetricCard
interface MetricCardProps { value: string | number; label: string; delta?: string; deltaSign?: 'pos' | 'neg' | 'auto'; sub?: string }
export function MetricCard({ value, label, delta, deltaSign, sub }: MetricCardProps) {
  const sign = deltaSign === 'auto' && delta
    ? delta.startsWith('+') ? 'pos' : delta.startsWith('-') ? 'neg' : undefined
    : deltaSign
  return (
    <div className="metric-card">
      <div className="metric-value">{value}</div>
      <div className="metric-label">{label}</div>
      {delta && <div className={`metric-delta ${sign === 'pos' ? 'positive' : sign === 'neg' ? 'negative' : ''}`}>{delta}</div>}
      {sub && <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>{sub}</div>}
    </div>
  )
}

// Spinner
export function Spinner({ size = 18 }: { size?: number }) {
  return (
    <span style={{
      display: 'inline-block', width: size, height: size,
      border: `2px solid var(--surface-border)`,
      borderTopColor: 'var(--accent)',
      borderRadius: '50%',
      animation: 'spin 0.7s linear infinite',
    }} />
  )
}

// Inject spin keyframe once
if (typeof document !== 'undefined' && !document.getElementById('spin-style')) {
  const s = document.createElement('style')
  s.id = 'spin-style'
  s.textContent = '@keyframes spin { to { transform: rotate(360deg); } }'
  document.head.appendChild(s)
}

// EmptyState
interface EmptyStateProps { icon?: string; title: string; desc?: string; action?: React.ReactNode }
export function EmptyState({ icon = '📭', title, desc, action }: EmptyStateProps) {
  return (
    <div className="empty-state">
      <div className="empty-state-icon">{icon}</div>
      <div className="empty-state-title">{title}</div>
      {desc && <div className="empty-state-desc">{desc}</div>}
      {action && <div style={{ marginTop: 16 }}>{action}</div>}
    </div>
  )
}

// ErrorBox
export function ErrorBox({ message }: { message: string }) {
  return (
    <div className="error-box" role="alert">
      <span style={{ fontSize: 14 }}>⚠️</span>
      <div style={{ marginLeft: 8 }}>{message}</div>
    </div>
  )
}

// Pagination
export { Pagination } from './Pagination'
