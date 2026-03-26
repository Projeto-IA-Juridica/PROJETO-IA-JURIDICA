import api from './client'

export interface DashboardStats {
  total_interacoes: number
  clientes_ativos: number
  nps_medio: number | null
  percentual_autonomia: number
  tempo_resposta_medio_ms: number
  interacoes_sem_humano: number
  horas_economizadas: number
  custo_total_usd: number
  escalacoes_pendentes: number
  tendencia_semanal?: Array<{
    semana: string
    total_interacoes: number
    nps_medio: number | null
    autonomia_pct: number
  }>
  por_cliente?: Array<{
    cliente_id: number
    nome: string
    nps_medio: number | null
    total_interacoes: number
    ultimo_contato_dias: number
    em_risco: boolean
    sem_avaliacao: boolean
  }>
}

export const analyticsApi = {
  dashboard: (dias: 7 | 30 | 90 = 30) =>
    api.get<DashboardStats>('/chat/stats/dashboard', { params: { dias } }).then((r) => r.data),

  exportCsv: (mes: string) =>
    api.get('/chat/stats/export', { params: { mes, formato: 'csv' }, responseType: 'blob' }).then((r) => r.data),
}
