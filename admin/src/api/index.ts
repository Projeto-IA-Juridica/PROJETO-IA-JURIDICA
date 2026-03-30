import api from './client'

// ─── Paginação ───────────────────────────────────────────────────────────────
export interface PaginatedResponse<T> {
  items: T[]
  page: number
  per_page: number
  total: number
}

// ─── Onboarding ───────────────────────────────────────────────────────────────
export interface OnboardingStatus {
  onboarding_completo: boolean
  etapa_atual: number
  percentual_completo: number
  proxima_etapa: number | null
  etapas: Array<{ numero: number; nome: string; concluida: boolean; descricao: string }>
  escritorio: {
    id: number
    nome: string
    persona_nome: string | null
    persona_tom: string | null
    whatsapp_conectado: boolean
  }
}

export const onboardingApi = {
  status: () => api.get<OnboardingStatus>('/onboarding/status').then((r) => r.data),

  configurarIA: (data: { persona_nome: string; persona_tom: string; horario_inicio: string; horario_fim: string }) =>
    api.post('/onboarding/configure-ia', data).then((r) => r.data),

  importProcessos: (file: File, preview = false) => {
    const form = new FormData()
    form.append('file', file)
    return api.post('/onboarding/import-processos', form, {
      params: { preview },
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then((r) => r.data)
  },

  connectWhatsapp: () => api.post('/onboarding/connect-whatsapp').then((r) => r.data),

  whatsappStatus: () => api.get<{ connected: boolean; state: string }>('/onboarding/whatsapp-status').then((r) => r.data),

  configurarTemplates: (data: { template_boas_vindas?: string; template_atualizacao?: string; template_sem_novidade?: string }) =>
    api.post('/onboarding/configure-templates', data).then((r) => r.data),

  goLive: () => api.post<{ processos_ativados: number; mensagem: string }>('/onboarding/go-live').then((r) => r.data),
}

// ─── Clientes ────────────────────────────────────────────────────────────────
export interface Cliente {
  id: number
  nome: string
  telefone_whatsapp: string
  cpf?: string
  data_nascimento?: string
  profissao?: string
  empresa?: string
  status: string
  ativo: boolean
  crm_nivel?: string | null
  crm_score?: number | null
}

export const clientesApi = {
  listar: (params?: { page?: number; page_size?: number; search?: string }) =>
    api.get<PaginatedResponse<Cliente>>('/clientes', { params }).then((r) => r.data.items || r.data),

  detalhe: (id: number) => api.get<Cliente>(`/clientes/${id}`).then((r) => r.data),
}

// ─── Processos ────────────────────────────────────────────────────────────────
export interface Processo {
  id: number
  numero_cnj: string
  tipo_acao: string | null
  polo_cliente: string
  status: string
  tribunal?: string
  vara?: string
  ultimo_andamento?: string
  data_ultimo_andamento?: string
  monitoramento_ativo: boolean
  score_risco?: number | null
  score_nivel?: string | null
  score_interpretacao?: string | null
  movimentos?: Array<{ nome: string; dataHora: string }>
}

export const processosApi = {
  porCliente: (clienteId: number) =>
    api.get<PaginatedResponse<Processo>>('/processos', { params: { cliente_id: clienteId } }).then((r) => r.data.items || r.data),

  detalhe: (id: number) => api.get<Processo>(`/processos/${id}`).then((r) => r.data),
}

// ─── RAG ──────────────────────────────────────────────────────────────────────
export interface RAGDoc {
  id: number
  titulo: string
  tipo: string
  total_chunks: number
  criado_em: string
}

export interface RAGChunk {
  id: string
  titulo: string
  tipo: string
  texto: string
  score: number
}

export const ragApi = {
  listar: () => api.get<RAGDoc[]>('/rag/documentos').then((r) => r.data),

  upload: (file: File, titulo: string, tipo: string) => {
    const form = new FormData()
    form.append('file', file)
    form.append('titulo', titulo)
    form.append('tipo', tipo)
    return api.post<{ chunks_gerados: number }>('/rag/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then((r) => r.data)
  },

  deletar: (id: number) => api.delete(`/rag/${id}`).then((r) => r.data),

  buscar: (query: string, topK = 3) =>
    api.get<RAGChunk[]>('/rag/buscar', { params: { q: query, top_k: topK } }).then((r) => r.data),
}
