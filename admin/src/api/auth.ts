import api from './client'

export interface LoginPayload { email: string; senha: string }
export interface RegisterPayload {
  nome_escritorio: string
  cnpj: string
  email_admin: string
  senha: string
  nome_responsavel: string
  oab_responsavel: string
}
export interface AuthTokens {
  access_token: string
  refresh_token: string
  expires_in: number
  escritorio?: Record<string, unknown>
}
export interface MeResponse {
  id: number
  nome: string
  email: string
  role: string
  escritorio_id: number
  oab: string | null
}

export const authApi = {
  login: (data: LoginPayload) =>
    api.post<AuthTokens>('/auth/login', data).then((r) => r.data),

  register: (data: RegisterPayload) =>
    api.post<AuthTokens>('/onboarding/register', data).then((r) => r.data),

  me: () => api.get<MeResponse>('/auth/me').then((r) => r.data),

  logout: () => api.post('/auth/logout').catch(() => {}),
}
