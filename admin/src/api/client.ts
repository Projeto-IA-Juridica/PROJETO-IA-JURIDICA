import axios from 'axios'

export const api = axios.create({
  baseURL: '/api',
  timeout: 30_000,
  headers: { 'Content-Type': 'application/json' },
})

// Injeta o JWT em todo request automaticamente
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
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
          const { data } = await axios.post('/api/auth/refresh', null, {
            headers: { Authorization: `Bearer ${refresh}` },
          })
          localStorage.setItem('access_token', data.access_token)
          localStorage.setItem('refresh_token', data.refresh_token)
          original.headers.Authorization = `Bearer ${data.access_token}`
          return api(original)
        } catch {
          localStorage.clear()
          window.location.href = '/login'
        }
      } else {
        localStorage.clear()
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

import * as MOCK from './mockData'

// --- ADAPTER MOCK PARA VISUALIZAÇÃO DE UI SEM DEPENDENCIA DO BACKEND ---
const originAdapter = axios.defaults.adapter;
api.defaults.adapter = async (config) => {
  // Simula um delay de rede leve pra parecer real
  await new Promise(r => setTimeout(r, 600))

  const url = config.url || ''
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

  // Falha em chamadas como login, onboarding register, e fallback real
  if (typeof originAdapter === 'function') return (originAdapter as Function)(config)
  return Promise.reject(new Error("No adapter found for " + url))
}
// ------------------------------------------------------------------------

export default api
