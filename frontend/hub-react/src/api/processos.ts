import { api } from './client'
import type { ProcessoList, Processo } from '../types'

export interface ProcessoFilters {
  status?: 'ativo' | 'arquivado'
  search?: string
  score_nivel?: 'baixo' | 'moderado' | 'alto' | 'critico'
}

export async function fetchProcessos(clienteId: number, filters?: ProcessoFilters): Promise<ProcessoList> {
  const { data } = await api.get<ProcessoList>('/processos', {
    params: { cliente_id: clienteId, per_page: 50, ...filters },
  })
  return data
}

export interface ProcessoCreate {
  numero_cnj: string
  cliente_id: number
  polo_cliente: 'autor' | 'reu' | 'terceiro'
  tipo_acao?: string
}

export async function criarProcesso(payload: ProcessoCreate): Promise<Processo> {
  const { data } = await api.post<Processo>('/processos', payload)
  return data
}

export interface ProcessoUpdate {
  polo_cliente?: 'autor' | 'reu' | 'terceiro'
  tipo_acao?: string
  monitoramento_ativo?: boolean
}

export async function atualizarProcesso(id: number, payload: ProcessoUpdate): Promise<Processo> {
  const { data } = await api.put<Processo>(`/processos/${id}`, payload)
  return data
}

export async function deletarProcesso(id: number): Promise<void> {
  await api.delete(`/processos/${id}`)
}
