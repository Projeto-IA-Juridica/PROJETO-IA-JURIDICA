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

export async function analisarPeticao(file: File): Promise<PeticaoAnalise> {
  const form = new FormData()
  form.append('arquivo', file)
  const { data } = await api.post<PeticaoAnalise>('/hub/analisar-peticao', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}
