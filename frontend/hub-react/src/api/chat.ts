import { api } from './client'

export async function exportarRelatorio(mes: string): Promise<void> {
  const { data } = await api.get<Blob>('/chat/stats/export', {
    params: { mes, formato: 'csv' },
    responseType: 'blob',
  })
  const url = URL.createObjectURL(data)
  const a = document.createElement('a')
  a.href = url
  a.download = `relatorio_interacoes_${mes}.csv`
  a.click()
  URL.revokeObjectURL(url)
}
