import { api } from './client'
import type { ProcessoList } from '../types'

export async function fetchProcessos(clienteId: number): Promise<ProcessoList> {
  const { data } = await api.get<ProcessoList>('/processos', {
    params: { cliente_id: clienteId, per_page: 5 },
  })
  return data
}
