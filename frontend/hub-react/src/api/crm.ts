import { api } from './client'
import type { CRMClienteCard } from '../types'

export async function fetchClientes(): Promise<CRMClienteCard[]> {
  const { data } = await api.get<CRMClienteCard[]>('/crm/clientes')
  return data
}

export async function fetchClienteCRM(clienteId: number): Promise<CRMClienteCard> {
  const { data } = await api.get<CRMClienteCard>(`/crm/clientes/${clienteId}`)
  return data
}

export interface ResumoCRM {
  excelente: number
  satisfeito: number
  neutro: number
  em_risco: number
  critico: number
  score_medio_escritorio: number | null
  sem_analise: number
}

export async function fetchResumoCRM(): Promise<ResumoCRM> {
  const { data } = await api.get<ResumoCRM>('/crm/resumo')
  return data
}

export interface AnaliseSingleResult {
  nivel: string
  score: number
  resumo: string
  acao_sugerida: string
  cache_hit: boolean
  tokens_input: number
  tokens_output: number
  custo_usd: string
}

export interface AnaliseEscritorioResult {
  job_id: string
  escritorio_id: number
}

export async function analisarCliente(clienteId: number): Promise<AnaliseSingleResult> {
  const { data } = await api.post<AnaliseSingleResult>(`/crm/clientes/${clienteId}/analisar`)
  return data
}

export async function analisarEscritorioCompleto(): Promise<AnaliseEscritorioResult> {
  const { data } = await api.post<AnaliseEscritorioResult>('/crm/analisar-escritorio')
  return data
}
