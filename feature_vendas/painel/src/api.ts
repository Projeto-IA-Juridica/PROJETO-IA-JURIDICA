/**
 * Cliente de API do painel interno — self-contained (próprio axios, sem
 * dependência do client do hub dos advogados).
 *
 * O token é lido de localStorage 'vendas_token' (login do tenant de vendas).
 * As rotas /vendas/* exigem JWT do tenant de vendas no backend.
 */

import axios from 'axios'

const api = axios.create({ baseURL: '/api' })
api.interceptors.request.use((cfg) => {
  const t = localStorage.getItem('vendas_token')
  if (t) cfg.headers.Authorization = `Bearer ${t}`
  return cfg
})

export type StatusAlvo =
  | 'novo' | 'enriquecendo' | 'fila_envio' | 'fila_excecao'
  | 'abordado' | 'em_cadencia' | 'respondeu' | 'quente' | 'descartado'

export type Funil = Partial<Record<StatusAlvo, number>>

export interface AlvoExcecao {
  id: number; escritorio: string; cnj: string | null
  confianca: number | null; mensagem: string | null; observacao: string | null
}
export interface LeadQuente {
  id: number; escritorio: string; contato: string | null; cidade: string | null
  whatsapp: string; gatilho: string | null; socio: string | null; respondeu_em: string | null
}
export interface ResultadoImportacao {
  importados: number; para_enriquecer: number; desqualificados: number; classe_c_ignorados: number
}

export const getFunil = () => api.get<Funil>('/vendas/leads/funil').then((r) => r.data)
export const getExcecoes = () => api.get<AlvoExcecao[]>('/vendas/leads/excecao').then((r) => r.data)
export const getQuentes = () => api.get<LeadQuente[]>('/vendas/leads/quentes').then((r) => r.data)

export function importarPlanilha(arquivo: File) {
  const form = new FormData()
  form.append('arquivo', arquivo)
  return api
    .post<ResultadoImportacao>('/vendas/leads/importar', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    .then((r) => r.data)
}
export const editarMensagem = (id: number, mensagem_espelho: string) =>
  api.patch(`/vendas/leads/${id}`, { mensagem_espelho }).then((r) => r.data)
export const aprovarExcecao = (id: number) =>
  api.post(`/vendas/leads/${id}/aprovar`).then((r) => r.data)

export const FUNIL_ORDEM: { status: StatusAlvo; label: string; cor: string }[] = [
  { status: 'novo', label: 'Novos', cor: 'var(--muted)' },
  { status: 'enriquecendo', label: 'Enriquecendo', cor: 'var(--muted)' },
  { status: 'fila_envio', label: 'Prontos p/ envio', cor: 'var(--blue)' },
  { status: 'fila_excecao', label: 'Revisão humana', cor: 'var(--amber)' },
  { status: 'em_cadencia', label: 'Em cadência', cor: 'var(--blue)' },
  { status: 'respondeu', label: 'Responderam', cor: 'var(--green)' },
  { status: 'quente', label: 'Quentes', cor: 'var(--red)' },
  { status: 'descartado', label: 'Descartados', cor: 'var(--muted)' },
]

export const GATILHO_LABEL: Record<string, string> = {
  pediu_reuniao: 'pediu reunião',
  pediu_preco: 'perguntou preço',
  pediu_trial: 'quer testar',
  pediu_proposta: 'pediu proposta',
  escritorio_grande_engajado: 'escritório grande, engajado',
  qualificacao_completa: 'qualificado e engajado',
}
