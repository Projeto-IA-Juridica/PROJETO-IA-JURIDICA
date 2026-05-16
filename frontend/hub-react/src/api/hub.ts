import { api } from './client'
import type { ConsultaHubResponse } from '../types'

export async function consultar(params: {
  pergunta: string
  cliente_id?: number
  processo_id?: number
}): Promise<ConsultaHubResponse> {
  const { data } = await api.post<ConsultaHubResponse>('/hub/consultar', params)
  return data
}

export interface SessaoListItem {
  id: number
  intencao: string
  modelo_ia: string
  mensagem_preview: string
  created_at: string
}

export async function listarHistorico(page = 1, limit = 25): Promise<SessaoListItem[]> {
  const { data } = await api.get<SessaoListItem[]>('/hub/historico', { params: { page, limit } })
  return data
}

export interface SessaoDetalhe {
  id: number
  intencao: string
  modelo_ia: string
  mensagem_advogado: string
  resposta_hub: string
  tokens_input: number
  tokens_output: number
  custo_estimado: string
  cliente_referenciado_id: number | null
  processo_referenciado_id: number | null
  metadata_json: Record<string, unknown>
  created_at: string
}

export async function detalharSessao(sessaoId: number): Promise<SessaoDetalhe> {
  const { data } = await api.get<SessaoDetalhe>(`/hub/historico/${sessaoId}`)
  return data
}

export interface PeticaoAnalise {
  tipo_peca: string
  pontos_fortes: string[]
  vulnerabilidades: string[]
  argumentos_ausentes: string[]
  precedentes_relevantes: string[]
  sugestoes: string[]
  score_geral: number
  texto_truncado: boolean
  percentual_analisado: number
  tokens_input: number
  tokens_output: number
  custo_estimado: string
}

export interface HubJobStatus {
  status: 'processando' | 'concluido' | 'erro'
  resultado: PeticaoAnalise | null
  erro: string | null
}

export async function analisarPeticaoAsync(file: File): Promise<{ job_id: string; status: string }> {
  const form = new FormData()
  form.append('arquivo', file)
  const { data } = await api.post<{ job_id: string; status: string }>('/hub/analisar-peticao', form, {
    headers: { 'Content-Type': undefined },
  })
  return data
}

export async function pollHubJob(jobId: string): Promise<HubJobStatus> {
  const { data } = await api.get<HubJobStatus>(`/hub/jobs/${jobId}`)
  return data
}

export interface MetricasHub {
  mes_atual: string
  total_sessoes: number
  tokens_input_total: number
  tokens_output_total: number
  custo_total_usd: string
  intencoes_top5: { intencao: string; total: number }[]
  advogados_mais_ativos: { usuario_id: number; total_sessoes: number }[]
}

export async function fetchMetricasHub(): Promise<MetricasHub> {
  const { data } = await api.get<MetricasHub>('/hub/metricas')
  return data
}
