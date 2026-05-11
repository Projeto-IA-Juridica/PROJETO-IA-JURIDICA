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
