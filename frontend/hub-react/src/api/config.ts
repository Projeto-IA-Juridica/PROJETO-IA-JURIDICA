import { api } from './client'
import type { Configuracoes } from '../types'

export type ConfigPayload = Omit<Configuracoes, 'cnpj'>

export async function getConfig(): Promise<Configuracoes> {
  const { data } = await api.get<Configuracoes>('/escritorios/config')
  return data
}

export async function saveConfig(payload: Partial<ConfigPayload>): Promise<Configuracoes> {
  const { data } = await api.put<Configuracoes>('/escritorios/config', payload)
  return data
}
