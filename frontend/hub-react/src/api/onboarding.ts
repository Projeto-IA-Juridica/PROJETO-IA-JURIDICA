import axios from 'axios'
import { KEYS, fetchCsrfToken } from './auth'
import { api } from './client'

/* Instância sem interceptors — /onboarding/register é público */
const plain = axios.create({ baseURL: '/api', headers: { 'Content-Type': 'application/json' } })

/* ── Extrai mensagem de erro do FastAPI (string 4xx ou array 422) ─ */
export function extractDetail(err: unknown): string {
  const data = (err as { response?: { data?: unknown } })?.response?.data
  if (!data) return ''
  const d = (data as { detail?: unknown }).detail
  if (typeof d === 'string') return d
  if (Array.isArray(d)) {
    return d
      .map((e: { msg?: string }) => e.msg?.replace(/^Value error, /, '') ?? '')
      .filter(Boolean)
      .join(' | ')
  }
  return ''
}

/* ── Mapeamento tom frontend → backend ───────────────────────────── */
export function mapTom(ton: string): 'formal' | 'amigavel' | 'neutro' {
  const t = ton.toLowerCase()
  if (t.includes('próximo') || t.includes('cordial')) return 'amigavel'
  if (t.includes('neutro'))                            return 'neutro'
  return 'formal'
}

/* ── Tipos ───────────────────────────────────────────────────────── */

export type PlanoOnboarding = 'basico' | 'profissional' | 'escritorio'

export interface RegisterPayload {
  nome_escritorio: string
  cnpj: string
  email_admin: string
  senha: string
  nome_responsavel: string
  oab_responsavel: string
  plano?: PlanoOnboarding
}

export interface RegisterResponse {
  access_token: string
  refresh_token: string
  expires_in: number
  escritorio: { id: number; nome: string; cnpj: string }
  /** URL do Stripe Checkout. null se Stripe não configurado. */
  checkout_url: string | null
}

export interface ConfigurarIAPayload {
  persona_nome: string
  persona_tom: 'formal' | 'amigavel' | 'neutro'
  horario_inicio: string
  horario_fim: string
}

export interface WhatsappStatus {
  connected: boolean
  state: string
}

export interface GoLiveResponse {
  onboarding_completo: boolean
  processos_ativados: number
  mensagem: string
}

/* ── Etapa 0 — Registro (público, CSRF isento) ───────────────────── */
export async function register(payload: RegisterPayload): Promise<RegisterResponse> {
  const { data } = await plain.post<RegisterResponse>('/onboarding/register', payload)
  localStorage.setItem(KEYS.access, data.access_token)
  localStorage.setItem(KEYS.refresh, data.refresh_token)
  /* Busca CSRF token para proteger chamadas seguintes */
  try { await fetchCsrfToken() } catch { /* falha silenciosa em HTTP puro */ }
  return data
}

/* ── Etapa 1 — Configurar IA (requer JWT + CSRF) ────────────────── */
export async function configurarIA(payload: ConfigurarIAPayload) {
  const { data } = await api.post('/onboarding/configure-ia', payload)
  return data
}

/* ── Etapa 3 — Conectar WhatsApp (requer JWT + CSRF) ────────────── */
export async function conectarWhatsapp(): Promise<{ qr_code: string | null; instance_name: string; status: string }> {
  const { data } = await api.post('/onboarding/connect-whatsapp')
  return data
}

/* ── Polling status WhatsApp (GET, sem CSRF) ─────────────────────── */
export async function statusWhatsapp(): Promise<WhatsappStatus> {
  const { data } = await api.get<WhatsappStatus>('/onboarding/whatsapp-status')
  return data
}

/* ── Etapa 2 — Importar processos via CSV (requer JWT admin) ─────── */
export interface ImportErro {
  linha: number
  dados: string
  motivo: string
}

export interface ImportProcessosResult {
  etapa: number | null
  importados: number
  atualizados: number
  processos_novos: number
  processos_atualizados: number
  ignorados: number
  erros: ImportErro[]
  preview: Record<string, string>[]
}

export async function importarProcessos(file: File, preview = false): Promise<ImportProcessosResult> {
  const form = new FormData()
  form.append('file', file)
  const { data } = await api.post<ImportProcessosResult>('/onboarding/import-processos', form, {
    headers: { 'Content-Type': undefined },
    params: { preview },
  })
  return data
}

/* ── Etapa 4 — Configurar templates (requer JWT + CSRF) ─────────── */
export interface ConfigurarTemplatesPayload {
  template_boas_vindas?:  string
  template_atualizacao?:  string
  template_sem_novidade?: string
}

export async function configurarTemplates(payload: ConfigurarTemplatesPayload = {}): Promise<{ etapa: number; mensagem: string }> {
  const { data } = await api.post<{ etapa: number; mensagem: string }>('/onboarding/configure-templates', payload)
  return data
}

/* ── Etapa 5 — Go Live (requer JWT + CSRF) ───────────────────────── */
export async function goLive(): Promise<GoLiveResponse> {
  const { data } = await api.post<GoLiveResponse>('/onboarding/go-live')
  return data
}

/* ── Status do onboarding ────────────────────────────────────────── */
export interface OnboardingEtapaItem {
  numero:    number
  nome:      string
  concluida: boolean
  descricao: string
}

export interface OnboardingStatus {
  onboarding_completo:  boolean
  etapa_atual:          number
  percentual_completo:  number
  proxima_etapa:        number | null
  etapas:               OnboardingEtapaItem[]
  escritorio: {
    id:               number
    nome:             string
    persona_nome:     string | null
    persona_tom:      string | null
    whatsapp_conectado: boolean
  }
}

export async function fetchOnboardingStatus(): Promise<OnboardingStatus> {
  const { data } = await api.get<OnboardingStatus>('/onboarding/status')
  return data
}
