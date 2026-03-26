import api from './client'

export interface CRMCard {
  id: number
  nome: string
  telefone_whatsapp: string
  crm_nivel: 'excelente' | 'satisfeito' | 'neutro' | 'em_risco' | 'critico' | null
  crm_score: number | null
  crm_resumo: string | null
  crm_acao_sugerida: string | null
  crm_analisado_em: string | null
  total_processos: number
  nps_medio: number | null
  ultimo_contato: string | null
}

export interface CRMResumo {
  excelente: number
  satisfeito: number
  neutro: number
  em_risco: number
  critico: number
  score_medio_escritorio: number | null
  sem_analise: number
}

export const crmApi = {
  listar: (params?: { nivel?: string; sem_analise?: boolean; page?: number; page_size?: number }) =>
    api.get<CRMCard[]>('/crm/clientes', { params }).then((r) => r.data),

  resumo: () => api.get<CRMResumo>('/crm/resumo').then((r) => r.data),

  analisar: (clienteId: number) =>
    api.post<{ nivel: string; score: number; resumo: string; acao_sugerida: string }>(`/crm/clientes/${clienteId}/analisar`).then((r) => r.data),

  analisarEscritorio: () =>
    api.post<{ job_id: string }>('/crm/analisar-escritorio').then((r) => r.data),
}
