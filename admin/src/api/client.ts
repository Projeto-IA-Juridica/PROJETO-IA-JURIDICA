import axios from 'axios'
import axiosRetry from 'axios-retry'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api'

export const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 45_000, // Aumentado para 45s para operações pesadas (CRM, RAG, IA)
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true, // Necessário para enviar cookies CSRF
})

// Configurar retry automático para requests que falharam
axiosRetry(api, {
  retries: 3, // Tentar até 3 vezes
  retryDelay: axiosRetry.exponentialDelay, // Delay exponencial entre tentativas
  retryCondition: (error) => {
    // Retry em erros de rede ou timeout, mas não em erros 4xx (client errors)
    return axiosRetry.isNetworkOrIdempotentRequestError(error) || error.code === 'ECONNABORTED'
  },
  onRetry: (retryCount, error, requestConfig) => {
    console.log(`Retry ${retryCount} para ${requestConfig.url}: ${error.message}`)
  },
})

// Armazena o token CSRF em memória
let csrfToken: string | null = null

// Busca o token CSRF do backend
export async function fetchCsrfToken(): Promise<string | null> {
  if (csrfToken) return csrfToken
  try {
    const { data } = await axios.get(`${API_BASE_URL}/auth/csrf-token`, { withCredentials: true })
    csrfToken = data.csrf_token
    if (csrfToken) {
      const secure = window.location.protocol === 'https:' ? '; Secure' : ''
      document.cookie = `csrf_token=${csrfToken}; Path=/; SameSite=Strict${secure}`
    }
    return csrfToken
  } catch (err) {
    console.error('Falha ao buscar CSRF token:', err)
    return null
  }
}

// Limpa o token CSRF (usado no logout)
export function clearCsrfToken(): void {
  csrfToken = null
}

// Métodos que exigem CSRF
const CSRF_METHODS = ['post', 'put', 'patch', 'delete']

// Injeta JWT e CSRF em todo request automaticamente
api.interceptors.request.use(async (config) => {
  // JWT
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`

  // CSRF para métodos mutantes
  if (CSRF_METHODS.includes(config.method?.toLowerCase() || '')) {
    if (!csrfToken) {
      await fetchCsrfToken()
    }
    if (csrfToken) {
      config.headers['X-CSRF-Token'] = csrfToken
    }
  }

  return config
})

// Tenta refresh automático em 401
api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const original = error.config
    // Permitir lidar com erros no login/register para renderizar mensagens
    if (original.url?.includes('/auth/login') || original.url?.includes('/onboarding/register')) {
      return Promise.reject(error)
    }

    if (error.response?.status === 401 && !original._retry) {
      original._retry = true
      const refresh = localStorage.getItem('refresh_token')
      if (refresh) {
        try {
          // Busca CSRF se não tiver
          if (!csrfToken) {
            await fetchCsrfToken()
          }
          const { data } = await axios.post(`${API_BASE_URL}/auth/refresh`, null, {
            headers: {
              Authorization: `Bearer ${refresh}`,
              'X-CSRF-Token': csrfToken || '',
            },
            withCredentials: true,
          })
          localStorage.setItem('access_token', data.access_token)
          localStorage.setItem('refresh_token', data.refresh_token)
          original.headers.Authorization = `Bearer ${data.access_token}`
          return api(original)
        } catch {
          localStorage.clear()
          clearCsrfToken()
          window.location.href = '/login'
        }
      } else {
        localStorage.clear()
        clearCsrfToken()
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

export default api
