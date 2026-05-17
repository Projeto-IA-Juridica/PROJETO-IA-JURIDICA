import axios from 'axios'
import { KEYS, getAccessToken, getCsrfToken, refreshAccessToken, clearAuth } from './auth'

/* Mantido para compatibilidade com DevBanner */
export const TOKEN_KEY = KEYS.access

const MUTATING = new Set(['post', 'put', 'patch', 'delete'])

// Em desenvolvimento: aponta para backend em localhost:8000
// Em produção: usa /api relativo (mesmo domínio no Railway)
const baseURL = import.meta.env.DEV
  ? import.meta.env.VITE_API_URL || 'http://localhost:8000/api'
  : '/api'

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

api.interceptors.response.use(
  (r) => r,
  async (err) => {
    const original = err.config

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
