import api from './client'

export interface PaginatedResponse<T> {
  items: T[]
  page: number
  per_page: number
  total: number
}

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

export interface CRMCliente {
  id: number
  nome: string
  telefone_whatsapp: string
  crm_nivel: 'excelente' | 'satisfeito' | 'neutro' | 'em_risco' | 'critico' | null
  crm_score: number | null
  crm_resumo: string | null
  crm_acao_sugerida: string | null
  crm_analisado_em: string | null
  total_processos: number
  nps_medio: number | null
  ultimo_contato: string | null
}

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
  crm_nivel?: 'excelente' | 'satisfeito' | 'neutro' | 'em_risco' | 'critico' | null
  crm_score?: number | null
  total_processos?: number
  nps_medio?: number | null
  ultimo_contato?: string | null
}

export interface ClienteExport {
  cliente: {
    id: number
    nome: string
    telefone_whatsapp?: string
    cpf?: string | null
    cpf_presente?: boolean
    data_nascimento?: string | null
    profissao?: string | null
    empresa?: string | null
    empresa_atual?: string | null
    cargo?: string | null
    ativo?: boolean
  }
  processos?: Array<Record<string, unknown>>
  interacoes?: Array<Record<string, unknown>>
}

export const clientesApi = {
  listar: async (params?: { page?: number; page_size?: number; search?: string }) => {
    const page = params?.page ?? 1
    const pageSize = params?.page_size ?? 20

    // Usa paginação no BACKEND diretamente
    const data = await api.get<CRMCliente[]>('/crm/clientes', {
      params: {
        page,
        page_size: pageSize,
      }
    }).then((r) => r.data)

    // Filtra busca no frontend (idealmente seria no backend também)
    const search = params?.search?.trim().toLowerCase()
    const filtered = search ? data.filter((item) => item.nome.toLowerCase().includes(search)) : data

    // IMPORTANTE: Backend não retorna total, então estimamos baseado no tamanho da resposta
    // Se retornou menos que page_size, assumimos que é a última página
    const isLastPage = filtered.length < pageSize
    const estimatedTotal = isLastPage ? (page - 1) * pageSize + filtered.length : page * pageSize + 1

    return {
      items: filtered.map((item) => ({
        id: item.id,
        nome: item.nome,
        telefone_whatsapp: item.telefone_whatsapp,
        status: 'ativo',
        ativo: true,
        crm_nivel: item.crm_nivel,
        crm_score: item.crm_score,
        total_processos: item.total_processos,
        nps_medio: item.nps_medio,
        ultimo_contato: item.ultimo_contato,
      })),
      page,
      per_page: pageSize,
      total: estimatedTotal,
    } satisfies PaginatedResponse<Cliente>
  },

  detalhe: async (id: number): Promise<Cliente> => {
    const crmCard = await api.get<CRMCliente>(`/crm/clientes/${id}`).then((r) => r.data)

    // Em alguns ambientes /clientes/{id}/exportar pode estar indisponível.
    // Mantemos o detalhe funcional com os dados de CRM e completamos campos extras quando possível.
    let base: ClienteExport['cliente'] | undefined
    try {
      const exportData = await api.get<ClienteExport>(`/clientes/${id}/exportar`).then((r) => r.data)
      base = exportData.cliente
    } catch (error) {
      console.warn('Falha ao obter dados LGPD exportáveis do cliente; usando fallback CRM.', error)
    }

    return {
      id: crmCard.id,
      nome: base?.nome || crmCard.nome,
      telefone_whatsapp: base?.telefone_whatsapp || crmCard.telefone_whatsapp,
      cpf: base?.cpf ?? (base?.cpf_presente ? 'Protegido (LGPD)' : undefined),
      data_nascimento: base?.data_nascimento ?? undefined,
      profissao: base?.profissao ?? undefined,
      empresa: base?.empresa ?? base?.empresa_atual ?? undefined,
      status: base?.ativo === false ? 'inativo' : 'ativo',
      ativo: base?.ativo !== false,
      crm_nivel: crmCard.crm_nivel,
      crm_score: crmCard.crm_score,
      total_processos: crmCard.total_processos,
      nps_medio: crmCard.nps_medio,
      ultimo_contato: crmCard.ultimo_contato,
    }
  },

  exportar: (id: number) => api.get<ClienteExport>(`/clientes/${id}/exportar`).then((r) => r.data),

  anonimizar: (id: number) => api.delete(`/clientes/${id}`).then((r) => r.data),
}

export interface Processo {
  id: number
  cliente_id: number
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
  frequencia_monitoramento?: 'diario' | 'semanal' | null
  advogado_responsavel_id?: number | null
}

export interface ProcessoCreatePayload {
  numero_cnj: string
  cliente_id: number
  polo_cliente: 'autor' | 'reu' | 'terceiro'
  tipo_acao?: string | null
}

export interface ProcessoUpdatePayload {
  polo_cliente?: 'autor' | 'reu' | 'terceiro'
  tipo_acao?: string | null
  advogado_responsavel_id?: number | null
  monitoramento_ativo?: boolean
  frequencia_monitoramento?: 'diario' | 'semanal'
}

export const processosApi = {
  listar: (params?: {
    page?: number
    per_page?: number
    status?: string
    cliente_id?: number
    search?: string
    score_nivel?: string
  }) => api.get<PaginatedResponse<Processo>>('/processos', { params }).then((r) => r.data),

  porCliente: (clienteId: number) =>
    api.get<PaginatedResponse<Processo>>('/processos', { params: { cliente_id: clienteId, per_page: 100 } }).then((r) => r.data.items),

  criar: (payload: ProcessoCreatePayload) => api.post<Processo>('/processos', payload).then((r) => r.data),

  detalhe: (id: number) => api.get<Processo>(`/processos/${id}`).then((r) => r.data),

  atualizar: (id: number, payload: ProcessoUpdatePayload) => api.put<Processo>(`/processos/${id}`, payload).then((r) => r.data),

  arquivar: (id: number) => api.delete(`/processos/${id}`).then((r) => r.data),
}

export interface RAGDoc {
  doc_hash: string
  titulo: string
  tipo: string
  chunks: number
  metadata_json: Record<string, unknown>
}

export interface RAGChunk {
  texto: string
}

export const ragApi = {
  listar: () =>
    api.get<RAGDoc[] | { items: RAGDoc[] }>('/rag/documentos').then((r) => {
      const d = r.data
      return Array.isArray(d) ? d : d.items ?? []
    }),

  upload: (file: File, titulo: string, tipo: string) => {
    const form = new FormData()
    form.append('file', file)
    return api.post<{ job_id: string; status: string }>('/rag/upload', form, {
      params: { titulo, tipo },
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then((r) => r.data)
  },

  statusIngestao: (jobId: string) => api.get<Record<string, unknown>>(`/rag/status/${jobId}`).then((r) => r.data),

  deletar: (docHash: string) => api.delete(`/rag/documentos/${docHash}`).then((r) => r.data),

  buscar: (query: string, tipo?: string) =>
    api.post<{ contexto: string }>('/rag/buscar', { query, tipo }).then((r) => {
      const texto = r.data.contexto || ''
      return texto
        .split(/\n\n+/)
        .filter(Boolean)
        .slice(0, 8)
        .map((chunk) => ({ texto: chunk })) as RAGChunk[]
    }),
}

export interface HealthCheck {
  status: string
  detail?: string
  latency_ms?: number
}

export interface HealthDetailed {
  status: string
  total_ms: number
  checks: Record<string, HealthCheck>
}

export const healthApi = {
  basic: () => api.get<{ status: string; service: string }>('/health').then((r) => r.data),
  ready: () => api.get<{ status: string; db: HealthCheck; redis: HealthCheck }>('/health/ready').then((r) => r.data),
  detailed: () => api.get<HealthDetailed>('/health/detailed').then((r) => r.data),
}

export interface DnaResponse {
  dados_insuficientes: boolean
  tipo_lead_predominante?: string
  especialidades?: string[]
  setores_alvo?: string[]
  perfil_cliente_ideal?: string | null
}

export interface Lead {
  id: number
  nome: string
  tipo_lead: string
  score_match: number
  status: string
  abordagem_sugerida?: string | null
  score_motivo?: string | null
  fonte_descoberta?: string | null
  criado_em?: string
}

export interface PipelineResponse {
  leads: Lead[]
  total: number
  dna_disponivel: boolean
  aviso_lgpd?: string | null
  linkedin_disponivel: boolean
}

export const prospeccaoApi = {
  dna: () => api.get<DnaResponse>('/prospeccao/dna').then((r) => r.data),

  atualizarDna: () => api.post<DnaResponse>('/prospeccao/dna/atualizar').then((r) => r.data),

  pipeline: (params?: { tipo_lead?: string; status?: string; score_minimo?: number; pagina?: number; por_pagina?: number }) =>
    api.get<PipelineResponse>('/prospeccao/pipeline', { params }).then((r) => r.data),

  descobrir: (payload: { tipo_acao: string; tribunal: string; limite: number; score_minimo: number; tipo_lead: string }) =>
    api.post<PipelineResponse>('/prospeccao/descobrir', payload).then((r) => r.data),

  atualizarStatus: (leadId: number, payload: { status: string; notas_advogado?: string }) =>
    api.patch<Lead>(`/prospeccao/${leadId}/status`, payload).then((r) => r.data),

  deletar: (leadId: number) => api.delete(`/prospeccao/${leadId}`).then((r) => r.data),
}

export const adminImportApi = {
  importarClientes: (file: File, preview = true) => {
    const form = new FormData()
    form.append('file', file)
    return api.post<{
      importados: number
      atualizados: number
      processos_novos: number
      processos_atualizados: number
      ignorados: number
      erros: Array<{ linha: number; motivo: string; dados?: string }>
      preview?: Array<Record<string, unknown>>
    }>('/admin/import/clientes', form, {
      params: { preview },
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then((r) => r.data)
  },
}
