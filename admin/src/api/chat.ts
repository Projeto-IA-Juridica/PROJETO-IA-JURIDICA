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

export const chatApi = {
  historico: (clienteId: number, page = 1) =>
    api.get<Mensagem[]>('/chat/historico', { params: { cliente_id: clienteId, page } }).then((r) => r.data),

  enviar: (clienteId: number, mensagem: string) =>
    api.post<{ resposta: string; intencao: string; tokens_usados: { input: number; output: number }; usando_fallback: boolean }>(
      '/chat/send',
      { mensagem, tipo: 'texto', cliente_id: clienteId }
    ).then((r) => r.data),
}
