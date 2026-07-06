import axios from 'axios'
import { KEYS, getAccessToken, getCsrfToken, refreshAccessToken, fetchCsrfToken, clearAuth } from './auth'

/* Mantido para compatibilidade com DevBanner */
export const TOKEN_KEY = KEYS.access

const MUTATING = new Set(['post', 'put', 'patch', 'delete'])

// Em desenvolvimento: usa /api relativo (Vite proxy redireciona para localhost:8000)
// Em produção: usa /api relativo (mesmo domínio)
const baseURL = '/api'

export const api = axios.create({
  baseURL,
  headers: { 'Content-Type': 'application/json' },
})

/* ── Request: injeta JWT + CSRF ───────────────────────────────────── */
api.interceptors.request.use((config) => {
  const token = getAccessToken()
  if (token) config.headers.Authorization = `Bearer ${token}`

  const method = (config.method ?? '').toLowerCase()
  if (MUTATING.has(method)) {
    const csrf = getCsrfToken()
    if (csrf) config.headers['X-CSRF-Token'] = csrf
  }

  return config
})

/* ── Response: renova token em 401 + expira sessão se falhar ─────── */
let isRefreshing = false
let pendingQueue: Array<{ resolve: (t: string) => void; reject: (e: unknown) => void }> = []

function drainQueue(token: string | null, err: unknown = null) {
  pendingQueue.forEach((p) => (token ? p.resolve(token) : p.reject(err)))
  pendingQueue = []
}

function isCsrfError(status: number | undefined, detail: unknown): boolean {
  return status === 403 && typeof detail === 'string' && detail.toLowerCase().includes('csrf')
}

api.interceptors.response.use(
  (r) => r,
  async (err) => {
    const original = err.config

    // O token CSRF (cookie de 24h) pode expirar no meio de uma sessão longa,
    // ou nunca ter sido obtido (ex: falha silenciosa no fetchCsrfToken() pós-login).
    // Sem este retry, qualquer POST/PUT/PATCH/DELETE falha para sempre com 403
    // até o usuário deslogar e logar de novo manualmente.
    if (isCsrfError(err.response?.status, err.response?.data?.detail) && !original?._csrfRetry) {
      original._csrfRetry = true
      try {
        const csrf = await fetchCsrfToken()
        original.headers['X-CSRF-Token'] = csrf
        return api(original)
      } catch (csrfErr) {
        return Promise.reject(csrfErr)
      }
    }

    if (err.response?.status !== 401 || original?._retry) {
      if (err.response?.status === 401) {
        console.warn('[Amicus] 401 sem retry possível')
      }
      return Promise.reject(err)
    }

    original._retry = true

    if (isRefreshing) {
      return new Promise<string>((resolve, reject) => {
        pendingQueue.push({ resolve, reject })
      }).then((token) => {
        original.headers.Authorization = `Bearer ${token}`
        return api(original)
      })
    }

    isRefreshing = true
    try {
      const { access_token } = await refreshAccessToken()
      drainQueue(access_token)
      original.headers.Authorization = `Bearer ${access_token}`
      return api(original)
    } catch (refreshErr) {
      drainQueue(null, refreshErr)
      clearAuth()
      window.dispatchEvent(new Event('amicus:session-expired'))
      return Promise.reject(refreshErr)
    } finally {
      isRefreshing = false
    }
  },
)
