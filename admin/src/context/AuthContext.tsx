import { createContext, useContext, useState, useEffect, type ReactNode } from 'react'
import { authApi, type MeResponse } from '../api/auth'

interface AuthState {
  user: MeResponse | null
  loading: boolean
  isAuthenticated: boolean
  login: (email: string, senha: string) => Promise<void>
  register: (data: Parameters<typeof authApi.register>[0]) => Promise<{ onboarding_completo: boolean }>
  logout: () => void
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<MeResponse | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const token = localStorage.getItem('access_token')
    if (token) {
      authApi.me()
        .then(setUser)
        .catch(() => { localStorage.clear(); setUser(null) })
        .finally(() => setLoading(false))
    } else {
      setLoading(false)
    }
  }, [])

  const login = async (email: string, senha: string) => {
    const data = await authApi.login({ email, senha })
    localStorage.setItem('access_token', data.access_token)
    localStorage.setItem('refresh_token', data.refresh_token)
    const me = await authApi.me()
    setUser(me)
  }

  const register = async (payload: Parameters<typeof authApi.register>[0]) => {
    const data = await authApi.register(payload)
    localStorage.setItem('access_token', data.access_token)
    localStorage.setItem('refresh_token', data.refresh_token)
    const me = await authApi.me()
    setUser(me)
    const esc = data.escritorio as Record<string, unknown> | undefined
    return { onboarding_completo: (esc?.onboarding_completo as boolean) ?? false }
  }

  const logout = async () => {
    await authApi.logout()
    localStorage.clear()
    setUser(null)
    window.location.href = '/login'
  }

  return (
    <AuthContext.Provider value={{ user, loading, isAuthenticated: !!user, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be inside AuthProvider')
  return ctx
}
