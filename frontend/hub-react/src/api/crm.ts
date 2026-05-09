import { api } from './client'
import type { CRMClienteCard } from '../types'

export async function fetchClientes(): Promise<CRMClienteCard[]> {
  const { data } = await api.get<CRMClienteCard[]>('/crm/clientes')
  return data
}

export interface ResumoCRM {
  baixo: number
  moderado: number
  alto: number
  critico: number
  score_medio_escritorio: number | null
  sem_analise: number
}

export async function fetchResumoCRM(): Promise<ResumoCRM> {
  const { data } = await api.get<ResumoCRM>('/crm/resumo')
  return data
}
