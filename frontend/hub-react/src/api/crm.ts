import { api } from './client'
import type { CRMClienteCard } from '../types'

export async function fetchClientes(): Promise<CRMClienteCard[]> {
  const { data } = await api.get<CRMClienteCard[]>('/crm/clientes')
  return data
}
