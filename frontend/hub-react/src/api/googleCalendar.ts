import { api } from './client'

export interface GoogleCalendarStatus {
  /** servidor tem GOOGLE_CALENDAR_CLIENT_ID/SECRET/REDIRECT_URI */
  configurado: boolean
  conectado: boolean
  conectado_em: string | null
  calendar_id: string
}

export async function fetchGoogleCalendarStatus(): Promise<GoogleCalendarStatus> {
  const { data } = await api.get<GoogleCalendarStatus>('/google-calendar/status')
  return data
}

export async function fetchGoogleCalendarAuthUrl(): Promise<string> {
  const { data } = await api.get<{ url: string }>('/google-calendar/auth-url')
  return data.url
}

export async function desconectarGoogleCalendar(): Promise<void> {
  await api.post('/google-calendar/disconnect')
}
