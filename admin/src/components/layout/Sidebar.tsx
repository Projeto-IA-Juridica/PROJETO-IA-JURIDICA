import { useState, useEffect } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import {
  Scale, FolderOpen, Handshake, BookOpen, BarChart3,
  Compass, Settings, LogOut, Sun, Moon,
} from 'lucide-react'

const NAV = [
  { to: '/hub', icon: Scale, label: 'Hub' },
  { to: '/processos', icon: FolderOpen, label: 'Processos' },
  { to: '/crm', icon: Handshake, label: 'CRM' },
  { to: '/rag', icon: BookOpen, label: 'Base RAG' },
  { to: '/analytics', icon: BarChart3, label: 'Analytics' },
  { to: '/operations', icon: Compass, label: 'Operações' },
  { to: '/settings', icon: Settings, label: 'Configurações' },
]

export default function Sidebar() {
  const { user, logout } = useAuth()
  const location = useLocation()

  const [theme, setTheme] = useState(() => {
    const stored = localStorage.getItem('theme')
    if (stored === 'light' || stored === 'dark') return stored
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  })

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    document.documentElement.style.colorScheme = theme
    localStorage.setItem('theme', theme)
  }, [theme])

  const toggleTheme = () => setTheme(prev => prev === 'dark' ? 'light' : 'dark')

  return (
    <aside className="sidebar-shell">
      <div className="sidebar-brand">
        <div className="sidebar-logo" aria-hidden>
          <Scale size={18} />
        </div>
        <div>
          <div className="sidebar-brand-title">Hub Jurídico</div>
          <div className="sidebar-brand-subtitle">Painel administrativo</div>
        </div>
      </div>

      {user && (
        <div className="sidebar-user">
          <div className="sidebar-user-name">{user.nome}</div>
          <div className="sidebar-user-role">{user.role}</div>
        </div>
      )}

      <nav className="sidebar-nav">
        {NAV.map(({ to, icon: Icon, label }) => {
          const isActive = location.pathname.startsWith(to)
          return (
            <NavLink
              key={to}
              to={to}
              className={`sidebar-link ${isActive ? 'active' : ''}`}
            >
              <Icon size={16} className="icon" />
              <span>{label}</span>
            </NavLink>
          )
        })}
      </nav>

      <div className="sidebar-footer">
        <button
          className="theme-switch"
          onClick={toggleTheme}
          type="button"
          aria-pressed={theme === 'dark'}
          title={theme === 'light' ? 'Alternar para tema escuro' : 'Alternar para tema claro'}
        >
          <span className="theme-switch-label">Tema</span>
          <span className={`theme-switch-track ${theme}`}>
            <span className="theme-switch-thumb" />
            <span className="theme-switch-option light">
              <Sun size={14} />
              <span>Claro</span>
            </span>
            <span className="theme-switch-option dark">
              <Moon size={14} />
              <span>Escuro</span>
            </span>
          </span>
        </button>

        <button
          className="sidebar-link"
          onClick={logout}
          type="button"
        >
          <LogOut size={16} className="icon" />
          <span>Sair</span>
        </button>
      </div>
    </aside>
  )
}
