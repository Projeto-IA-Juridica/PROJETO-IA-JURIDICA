export type Section =
  | 'painel'
  | 'clientes'
  | 'hub-ia'
  | 'whatsapp'
  | 'captacao'
  | 'documentos'
  | 'planos'
  | 'config'

/* ── Clientes / Processos (existentes) ── */

export interface CRMClienteCard {
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

export interface Andamento {
  data: string | null
  descricao: string
  tipo?: string
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
  conversa_id: string | null
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  ragAtivo?: boolean
  escalacao?: boolean
  intencao?: string
  tokens?: number
}

/* ── Prospecção Inteligente ── */

export type LeadStatus = 'novo' | 'contatado' | 'qualificado' | 'descartado'
export type TipoLead  = 'empresa' | 'pessoa'

export interface LeadProspeccaoResponse {
  id: number
  tipo_lead: TipoLead
  nome: string
  score_match: number | null
  score_motivo: string | null
  abordagem_sugerida: string | null
  status: LeadStatus
  notas_advogado: string | null
  fonte_descoberta: string | null
  criado_em: string
  // empresa
  cnpj: string | null
  empresa_setor: string | null
  empresa_porte: string | null
  socios: { nome: string; qualificacao: string }[]
  contatos_linkedin: { nome: string; cargo: string; url_perfil: string }[]
  linkedin_disponivel: boolean
  // pessoa (LGPD: nunca CPF/tel/email)
  polo_processo: string | null
  tipo_acao_origem: string | null
  numero_cnj_exemplo: string | null
  processos_publicos_count: number
}

export interface DNAEscritorioResponse {
  dados_insuficientes: boolean
  especialidades: string[]
  setores_alvo: string[]
  tipo_lead_predominante: 'empresa' | 'pessoa' | 'ambos' | null
  perfil_cliente_ideal: string | null
  diferenciais: string[]
  gerado_em: string | null
}

export interface PipelineResponse {
  total: number
  leads: LeadProspeccaoResponse[]
  dna_disponivel: boolean
  linkedin_disponivel: boolean
  aviso_lgpd: string | null
}

export interface DescobertaRequest {
  tipo_lead: TipoLead | 'auto'
  tipo_acao: string
  tribunal: string | null
  limite: number
  score_minimo: number
}

export interface LeadStatusUpdate {
  status: LeadStatus
  notas_advogado?: string | null
}

/* ── Hub IA — sessão ── */

export interface HubIASessao {
  id: number
  intencao: string
  preview: string
  resposta: string
  tokens_input: number
  tokens_output: number
  criado_em: string
}

/* ── Configurações do escritório ── */

export interface Configuracoes {
  nome: string
  cnpj: string
  email: string
  telefone?: string
  persona_nome: string
  persona_tom: 'formal' | 'amigavel' | 'neutro'
  horario_inicio: string
  horario_fim: string
  template_boas_vindas: string
  template_atualizacao: string
  template_sem_novidade: string
}
