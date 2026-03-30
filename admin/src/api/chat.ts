import api from './client'

export interface Mensagem {
  id: number
  data: string
  direcao: 'recebida' | 'enviada'
  mensagem_cliente: string | null
  mensagem_ia: string | null
  tokens_input: number
  tokens_output: number
  custo_estimado: string
  intencao?: string
  usando_fallback?: boolean
  rag_ativo?: boolean
}

export interface SendMessageResponse {
  status: string
  message: string
}

export const chatApi = {
  historico: (clienteId: number, limit = 50) =>
    api.get<Mensagem[]>(`/chat/history/${clienteId}`, { params: { limit } }).then((r) => r.data),

  enviar: (clienteId: number, mensagem: string) =>
    api.post<SendMessageResponse>(`/chat/send/${clienteId}`, { mensagem, tipo: 'texto' }).then((r) => r.data),
}
