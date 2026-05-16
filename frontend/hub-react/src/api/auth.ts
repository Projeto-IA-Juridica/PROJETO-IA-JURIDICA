import axios from 'axios'

export const KEYS = {
  access:  'amicus_token',
  refresh: 'amicus_refresh_token',
  csrf:    'amicus_csrf_token',
} as const

export interface TokenResponse {
  access_token:  string
  refresh_token: string
  token_type:    string
  expires_in:    number
}

export interface User {
  id:           number
  escritorio_id: number
  nome:         string
  email:        string
  role:         string
  oab:          string | null
  ativo:        boolean
  ultimo_login: string | null
  created_at:   string
  updated_at:   string
}

/* Instância sem interceptors — evita dependência circular com client.ts */
const plain = axios.create({ baseURL: '/api', headers: { 'Content-Type': 'application/json' } })

/* ── Storage helpers ──────────────────────────────────────────────── */

export const getAccessToken  = () => localStorage.getItem(KEYS.access)
export const getRefreshToken = () => localStorage.getItem(KEYS.refresh)
export const getCsrfToken    = () => localStorage.getItem(KEYS.csrf)

export function clearAuth() {
  Object.values(KEYS).forEach((k) => localStorage.removeItem(k))
}

function storeTokens(data: TokenResponse) {
  localStorage.setItem(KEYS.access,  data.access_token)
  localStorage.setItem(KEYS.refresh, data.refresh_token)
}

/* ── Auth API calls ───────────────────────────────────────────────── */

export async function fetchCsrfToken(): Promise<string> {
  const { data } = await plain.get<{ csrf_token: string }>('/auth/csrf-token')
  localStorage.setItem(KEYS.csrf, data.csrf_token)
  return data.csrf_token
}

export async function login(email: string, senha: string): Promise<TokenResponse> {
  const { data } = await plain.post<TokenResponse>('/auth/login', { email, senha })
  storeTokens(data)
  /* CSRF token é obtido após login para proteger as próximas requisições mutantes */
  try { await fetchCsrfToken() } catch { /* falha silenciosa em dev (cookie secure) */ }
  return data
}

export async function refreshAccessToken(): Promise<TokenResponse> {
  const token = getRefreshToken()
  if (!token) throw new Error('Refresh token ausente')
  const { data } = await plain.post<TokenResponse>(
    '/auth/refresh',
    {},
    { headers: { Authorization: `Bearer ${token}` } },
  )
  storeTokens(data)
  return data
}

export async function logout(): Promise<void> {
  try {
    const token = getAccessToken()
    if (token) {
      await plain.post('/auth/logout', {}, { headers: { Authorization: `Bearer ${token}` } })
    }
  } finally {
    clearAuth()
  }
}

export async function fetchMe(): Promise<User> {
  const { data } = await plain.get<User>('/auth/me', {
    headers: { Authorization: `Bearer ${getAccessToken()}` },
  })
  return data
}
