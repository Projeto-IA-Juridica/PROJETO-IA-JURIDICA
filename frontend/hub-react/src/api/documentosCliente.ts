import { api } from './client'

export type TipoDocCliente =
  | 'contrato'
  | 'procuracao'
  | 'identidade'
  | 'peticao'
  | 'comprovante'
  | 'outro'

export const TIPOS_DOC_CLIENTE: Record<TipoDocCliente, { label: string; color: string }> = {
  contrato:    { label: 'Contrato',     color: '#1248BE' },
  procuracao:  { label: 'Procuração',   color: '#7C4DFF' },
  identidade:  { label: 'Identidade',   color: '#D08010' },
  peticao:     { label: 'Petição',      color: '#2D6FD4' },
  comprovante: { label: 'Comprovante',  color: '#1A9E78' },
  outro:       { label: 'Outro',        color: '#8A9BB0' },
}

export interface DocClienteItem {
  id: number
  nome: string
  arquivo_nome: string
  mime_type: string
  tamanho_bytes: number
  tipo: TipoDocCliente
  processo_id: number | null
  created_at: string
}

export async function listarDocumentosCliente(clienteId: number): Promise<DocClienteItem[]> {
  const { data } = await api.get<DocClienteItem[]>(`/clientes/${clienteId}/documentos`)
  return data
}

export async function uploadDocumentoCliente(
  clienteId: number,
  file: File,
  nome: string,
  tipo: TipoDocCliente,
  processoId?: number | null,
): Promise<DocClienteItem> {
  const form = new FormData()
  form.append('file', file)
  const params = new URLSearchParams({ nome, tipo })
  if (processoId != null) params.append('processo_id', String(processoId))

  const { data } = await api.post<DocClienteItem>(
    `/clientes/${clienteId}/documentos?${params}`,
    form,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  )
  return data
}

export async function downloadDocumentoCliente(
  clienteId: number,
  docId: number,
  arquivoNome: string,
): Promise<void> {
  const { data } = await api.get<Blob>(
    `/clientes/${clienteId}/documentos/${docId}/download`,
    { responseType: 'blob' },
  )
  const url = URL.createObjectURL(data)
  const a = document.createElement('a')
  a.href = url
  a.download = arquivoNome
  a.click()
  URL.revokeObjectURL(url)
}

export async function deletarDocumentoCliente(
  clienteId: number,
  docId: number,
): Promise<void> {
  await api.delete(`/clientes/${clienteId}/documentos/${docId}`)
}
