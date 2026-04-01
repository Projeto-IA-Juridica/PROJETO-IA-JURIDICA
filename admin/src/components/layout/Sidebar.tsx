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

  const [theme, setTheme] = useState(localStorage.getItem('theme') || 'dark')

  useEffect(() => {
    document.documentElement.className = theme === 'light' ? 'light-theme' : ''
    localStorage.setItem('theme', theme)
  }, [theme])

  const toggleTheme = () => setTheme(prev => prev === 'dark' ? 'light' : 'dark')

  return (
    <aside style={{
      width: 200,
      minWidth: 200,
      background: 'var(--surface-raised)',
      borderRight: '1px solid var(--surface-border)',
      display: 'flex',
      flexDirection: 'column',
      height: '100vh',
      position: 'sticky',
      top: 0,
    }}>
      {/* Logo */}
      <div style={{ padding: '16px 14px 12px', borderBottom: '1px solid var(--surface-border)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Scale size={18} style={{ color: 'var(--accent)' }} />
          <div>
            <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '-0.01em' }}>Hub Jurídico</div>
            <div style={{ fontSize: 10, color: 'var(--text-muted)', letterSpacing: '0.03em' }}>PAINEL</div>
          </div>
        </div>
      </div>

      {/* User info */}
      {user && (
        <div style={{ padding: '10px 14px', borderBottom: '1px solid var(--surface-border)' }}>
          <div style={{ fontSize: 12, color: 'var(--text-primary)', fontWeight: 500 }}>{user.nome}</div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{user.role}</div>
        </div>
      )}

      {/* Nav */}
      <nav style={{ flex: 1, padding: '6px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 1 }}>
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

      {/* Footer */}
      <div style={{ padding: '8px 6px', borderTop: '1px solid var(--surface-border)', display: 'flex', flexDirection: 'column', gap: 1 }}>
        <button
          className="sidebar-link"
          onClick={toggleTheme}
          style={{ width: '100%', cursor: 'pointer', background: 'none', border: 'none', fontFamily: 'inherit' }}
        >
          <div className="theme-toggle">
            <Sun size={16} className={`icon ${theme === 'light' ? 'active' : ''}`} />
            <Moon size={16} className={`icon ${theme === 'dark' ? 'active' : ''}`} />
          </div>
          <span style={{ fontSize: 13 }}>{theme === 'light' ? 'Claro' : 'Escuro'}</span>
        </button>

        <button
          className="sidebar-link"
          onClick={logout}
          style={{ width: '100%', cursor: 'pointer', background: 'none', border: 'none', fontFamily: 'inherit' }}
        >
          <LogOut size={16} className="icon" />
          <span style={{ fontSize: 13 }}>Sair</span>
        </button>
      </div>
    </aside>
  )
}
