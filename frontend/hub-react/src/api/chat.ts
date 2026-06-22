import { api } from './client'

export async function exportarRelatorio(mes: string): Promise<void> {
  const { data } = await api.get<Blob>('/chat/stats/export', {
    params: { mes, formato: 'csv' },
    responseType: 'blob',
  })
  const url = URL.createObjectURL(data)
  const a = document.createElement('a')
  a.href = url
  a.download = `resumo_clientes_${mes}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

export interface InteracaoItem {
  id: number
  data: string
  direcao: string
  mensagem_cliente: string | null
  mensagem_ia: string | null
  tokens_input: number
  tokens_output: number
  custo_estimado: string
}

export async function fetchChatHistory(clienteId: number, limit = 50): Promise<InteracaoItem[]> {
  const { data } = await api.get<InteracaoItem[]>(`/chat/history/${clienteId}`, {
    params: { limit },
  })
  return data
}
