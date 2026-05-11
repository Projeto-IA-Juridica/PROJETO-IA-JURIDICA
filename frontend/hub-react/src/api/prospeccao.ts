import { api } from './client'
import type {
  DNAEscritorioResponse,
  PipelineResponse,
  LeadProspeccaoResponse,
  DescobertaRequest,
  LeadStatusUpdate,
} from '../types'

export async function fetchDNA(): Promise<DNAEscritorioResponse> {
  const { data } = await api.get<DNAEscritorioResponse>('/prospeccao/dna')
  return data
}

export async function atualizarDNA(): Promise<DNAEscritorioResponse> {
  const { data } = await api.post<DNAEscritorioResponse>('/prospeccao/dna/atualizar')
  return data
}

export async function descobrirLeads(body: DescobertaRequest): Promise<PipelineResponse> {
  const { data } = await api.post<PipelineResponse>('/prospeccao/descobrir', body)
  return data
}

export async function fetchPipeline(params?: {
  tipo_lead?: string
  status?: string
  score_minimo?: number
  pagina?: number
}): Promise<PipelineResponse> {
  const { data } = await api.get<PipelineResponse>('/prospeccao/pipeline', { params })
  return data
}

export async function atualizarStatus(
  leadId: number,
  body: LeadStatusUpdate,
): Promise<LeadProspeccaoResponse> {
  const { data } = await api.patch<LeadProspeccaoResponse>(`/prospeccao/${leadId}/status`, body)
  return data
}

export async function deletarLead(leadId: number): Promise<void> {
  await api.delete(`/prospeccao/${leadId}`)
}
