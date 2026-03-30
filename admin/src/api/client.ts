import axios from 'axios'

export const api = axios.create({
  baseURL: '/api',
  timeout: 30_000,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true, // Necessário para enviar cookies CSRF
})

// Armazena o token CSRF em memória
let csrfToken: string | null = null

// Busca o token CSRF do backend
export async function fetchCsrfToken(): Promise<string | null> {
  if (csrfToken) return csrfToken
  try {
    const { data } = await axios.get('/api/auth/csrf-token', { withCredentials: true })
    csrfToken = data.csrf_token
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
    if (error.response?.status === 401 && !original._retry) {
      original._retry = true
      const refresh = localStorage.getItem('refresh_token')
      if (refresh) {
        try {
          // Busca CSRF se não tiver
          if (!csrfToken) {
            await fetchCsrfToken()
          }
          const { data } = await axios.post('/api/auth/refresh', null, {
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
