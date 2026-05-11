import axios from 'axios'

export const TOKEN_KEY = 'amicus_dev_token'

export const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      console.warn('[Amicus] 401 — defina o token em localStorage:', TOKEN_KEY)
    }
    return Promise.reject(err)
  }
)
