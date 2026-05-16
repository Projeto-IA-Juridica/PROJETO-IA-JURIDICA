import { api } from './client'

export interface EscalacaoItem {
  id: number
  cliente_id: number
  cliente_nome: string | null
  mensagem_cliente: string | null
  sugestao_resposta: string | null
  motivo: string | null
  status_escalacao: 'pendente' | 'aprovada' | 'rejeitada'
  created_at: string
}

export type StatusEscalacao = 'pendente' | 'aprovada' | 'rejeitada'

export async function listarEscalacoes(
  statusFiltro: StatusEscalacao = 'pendente',
  page = 1,
  limit = 25,
): Promise<EscalacaoItem[]> {
  const { data } = await api.get<EscalacaoItem[]>('/escalacoes', {
    params: { status: statusFiltro, page, limit },
  })
  return data
}

export async function aprovarEscalacao(
  id: number,
  respostaFinal?: string,
): Promise<{ ok: boolean; enviado: boolean; resposta: string }> {
  const { data } = await api.post(`/escalacoes/${id}/aprovar`, {
    resposta_final: respostaFinal ?? null,
  })
  return data
}

export async function rejeitarEscalacao(id: number): Promise<{ ok: boolean }> {
  const { data } = await api.post(`/escalacoes/${id}/rejeitar`)
  return data
}
