import { api } from './client'

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
