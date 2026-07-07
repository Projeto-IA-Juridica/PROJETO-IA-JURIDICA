import { api } from './client'

export interface ClienteCreateManual {
  nome: string
  cpf: string
  telefone_whatsapp: string
  numero_cnj?: string | null
  polo_cliente?: 'autor' | 'reu' | 'terceiro'
  tipo_acao?: string | null
}

export interface ClienteCreateManualResponse {
  id: number
  nome: string
  telefone_whatsapp: string
  processo_id: number | null
}

export async function criarClienteManual(payload: ClienteCreateManual): Promise<ClienteCreateManualResponse> {
  const { data } = await api.post<ClienteCreateManualResponse>('/clientes', payload)
  return data
}

export async function exportarCliente(clienteId: number): Promise<void> {
  const { data } = await api.get<Blob>(`/clientes/${clienteId}/exportar`, {
    responseType: 'blob',
  })
  const url = URL.createObjectURL(data)
  const a = document.createElement('a')
  a.href = url
  a.download = `lgpd_cliente_${clienteId}.json`
  a.click()
  URL.revokeObjectURL(url)
}

export async function deletarClienteLGPD(clienteId: number): Promise<void> {
  await api.delete(`/clientes/${clienteId}`)
}

export async function atualizarCliente(clienteId: number, payload: { nome?: string, telefone_whatsapp?: string }): Promise<void> {
  await api.put(`/clientes/${clienteId}`, payload)
}
