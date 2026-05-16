import { api } from './client'

export interface DocItem {
  doc_hash: string
  titulo: string
  tipo: string
  chunks: number
  metadata_json: Record<string, unknown>
}

export interface DocListResponse {
  items: DocItem[]
  total: number
  page: number
  per_page: number
}

export interface UploadJobResult {
  job_id: string
  status: string
}

export interface JobStatus {
  status: 'pendente' | 'em_andamento' | 'concluido' | 'erro'
  titulo: string
  tipo: string
  chunks: number
  erro: string | null
}

export async function listarDocumentos(tipo?: string): Promise<DocListResponse> {
  const { data } = await api.get<DocListResponse>('/rag/documentos', {
    params: tipo ? { tipo } : undefined,
  })
  return data
}

export async function uploadDocumento(
  file: File,
  titulo: string,
  tipo: string,
): Promise<UploadJobResult> {
  const form = new FormData()
  form.append('file', file)
  const { data } = await api.post<UploadJobResult>(
    `/rag/upload?titulo=${encodeURIComponent(titulo)}&tipo=${encodeURIComponent(tipo)}`,
    form,
    // Sem Content-Type manual: browser/axios define multipart com boundary correto
    { headers: { 'Content-Type': undefined } },
  )
  return data
}

export async function statusJob(jobId: string): Promise<JobStatus> {
  const { data } = await api.get<JobStatus>(`/rag/status/${jobId}`)
  return data
}

export async function deletarDocumento(docHash: string): Promise<void> {
  await api.delete(`/rag/documentos/${docHash}`)
}

export interface BuscarResult {
  query: string
  contexto: string
}

export async function buscarSemantico(
  query: string,
  tipo?: string,
  tribunal?: string,
): Promise<BuscarResult> {
  const { data } = await api.post<BuscarResult>('/rag/buscar', {
    query,
    tipo:     tipo     || undefined,
    tribunal: tribunal || undefined,
  })
  return data
}
