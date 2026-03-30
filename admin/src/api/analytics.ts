import api from './client'

export interface DashboardResumo {
  total_interacoes: number
  clientes_ativos: number
  nps_medio: number
  nps_anterior: number
  variacao_nps: string
}

export interface DashboardEficiencia {
  percentual_autonomia: number
  tempo_resposta_medio_ms: number
  interacoes_sem_humano: number
  horas_economizadas_estimadas: number
  custo_total_usd: number
}

export interface DashboardStats {
  resumo: DashboardResumo
  eficiencia: DashboardEficiencia
  tendencia_semanal: Array<{
    semana: string
    total_interacoes: number
    nps_medio: number
    autonomia_pct: number
  }>
  por_cliente: Array<{
    cliente_id: number
    nome: string
    nps_medio: number | null
    total_interacoes: number
    ultimo_contato: string | null
    em_risco: boolean
    sem_avaliacao: boolean
  }>
  score_risco_distribuicao: Record<string, number>
}

export const analyticsApi = {
  dashboard: (dias: 7 | 30 | 90 = 30) =>
    api.get<DashboardStats>('/chat/stats/dashboard', { params: { dias } }).then((r) => r.data),

  exportCsv: (mes: string) =>
    api.get('/chat/stats/export', { params: { mes, formato: 'csv' }, responseType: 'blob' }).then((r) => r.data),
}
