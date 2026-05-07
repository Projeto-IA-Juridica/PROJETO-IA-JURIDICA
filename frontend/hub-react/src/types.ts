export interface CRMClienteCard {
  id: number
  nome: string
  telefone_whatsapp: string
  crm_nivel: string | null
  crm_score: number | null
  crm_resumo: string | null
  crm_acao_sugerida: string | null
  crm_analisado_em: string | null
  total_processos: number
  nps_medio: number | null
  ultimo_contato: string | null
}

export interface Andamento {
  data: string
  descricao: string
  tipo: string
}

export interface Processo {
  id: number
  cliente_id: number
  numero_cnj: string
  tribunal: string | null
  vara: string | null
  comarca: string | null
  tipo_acao: string | null
  polo_cliente: string
  status: string
  ultimo_andamento: string | null
  data_ultimo_andamento: string | null
  data_distribuicao: string | null
  valor_causa: string | null
  score_risco: number | null
  score_nivel: string | null
  score_interpretacao: string | null
  score_componentes: Record<string, number> | null
  andamentos: Andamento[]
  created_at: string
  updated_at: string
}

export interface ProcessoList {
  items: Processo[]
  total: number
  page: number
  per_page: number
  pages: number
}

export interface ConsultaHubResponse {
  resposta: string
  modelo_ia: string
  tokens_input: number
  tokens_output: number
  custo_estimado: string
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  ragAtivo?: boolean
  escalacao?: boolean
  intencao?: string
  tokens?: number
}
