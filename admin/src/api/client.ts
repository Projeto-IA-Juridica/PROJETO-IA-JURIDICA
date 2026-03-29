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

import * as MOCK from './mockData'

// --- ADAPTER MOCK PARA VISUALIZAÇÃO DE UI SEM DEPENDENCIA DO BACKEND ---
// URLs que devem ir direto pro backend real (não mockar)
const REAL_URLS = ['/auth/login', '/auth/logout', '/auth/csrf-token', '/auth/refresh', '/onboarding/register']

const xhrAdapter = axios.getAdapter('xhr')

api.defaults.adapter = async (config) => {
  const url = config.url || ''

  // Chamadas reais vão direto pro backend
  if (REAL_URLS.some(u => url.startsWith(u))) {
    return xhrAdapter(config)
  }

  // Simula um delay de rede leve pra parecer real
  await new Promise(r => setTimeout(r, 600))

  let data: any = null

  try {
    if (url === '/auth/me') data = MOCK.MOCK_ME
    else if (url.match(/^\/clientes\/\d+$/)) data = MOCK.MOCK_CLIENTES.find(c => c.id === Number(url.split('/')[2]))
    else if (url === '/clientes') data = MOCK.MOCK_CLIENTES
    else if (url === '/processos') {
      const cid = config.params?.cliente_id
      data = cid ? (MOCK.MOCK_PROCESSOS[cid as number] || []) : Object.values(MOCK.MOCK_PROCESSOS).flat()
    }
    else if (url === '/chat/historico') {
      const cid = config.params?.cliente_id
      data = cid ? (MOCK.MOCK_CHAT[cid as number] || []) : []
    }
    else if (url === '/chat/stats/dashboard') data = MOCK.MOCK_ANALYTICS
    else if (url === '/crm/clientes') data = MOCK.MOCK_CRM_CLIENTES
    else if (url === '/crm/resumo') data = MOCK.MOCK_CRM_RESUMO
    else if (url === '/rag/documentos') data = MOCK.MOCK_RAG_DOCS
    else if (url === '/onboarding/status') data = MOCK.MOCK_STATUS
    else if (url.includes('/analisar')) return { data: { nivel: 'moderado', score: 50, resumo: 'Mocked.', acao_sugerida: 'Mocked.'}, status: 200, statusText: 'OK', headers: new axios.AxiosHeaders(), config, request: {} as any }
    else if (url === '/chat/send') return { data: { resposta: 'Essa é uma resposta mockada da inteligência artificial para demonstração da interface.', intencao: 'duvida', usando_fallback: false, tokens_usados: {input: 10, output: 20} }, status: 200, statusText: 'OK', headers: new axios.AxiosHeaders(), config, request: {} as any }
  } catch (e) {
    console.error("Mock error:", e)
  }

  if (data !== null) {
    return { data, status: 200, statusText: 'OK', headers: new axios.AxiosHeaders(), config, request: {} as any }
  }

  // Fallback para o backend real
  return xhrAdapter(config)
}
// ------------------------------------------------------------------------

export default api
