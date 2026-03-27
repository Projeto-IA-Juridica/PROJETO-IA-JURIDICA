import { useState, useEffect } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'

const NAV = [
  { to: '/hub', icon: '⚖️', label: 'Hub do Advogado' },
  { to: '/crm', icon: '🤝', label: 'CRM' },
  { to: '/rag', icon: '📚', label: 'Base RAG' },
  { to: '/analytics', icon: '📊', label: 'Analytics' },
  { to: '/settings', icon: '⚙️', label: 'Configurações' },
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
      width: 220,
      minWidth: 220,
      background: 'var(--surface-raised)',
      borderRight: '1px solid var(--surface-border)',
      display: 'flex',
      flexDirection: 'column',
      padding: '0',
      height: '100vh',
      position: 'sticky',
      top: 0,
    }}>
      {/* Logo */}
      <div style={{ padding: '20px 16px 14px', borderBottom: '1px solid var(--surface-border)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 20 }}>⚖️</span>
          <div>
            <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }}>Hub Jurídico</div>
            <div style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Painel Interno</div>
          </div>
        </div>
      </div>

      {/* Escritório */}
      {user && (
        <div style={{ padding: '10px 16px', borderBottom: '1px solid var(--surface-border-muted)' }}>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 2 }}>Escritório</div>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)', fontWeight: 500, wordBreak: 'break-all' }}>
            {user.nome}
          </div>
          <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>{user.role}</div>
        </div>
      )}

      {/* Nav links */}
      <nav style={{ flex: 1, padding: '8px 8px', overflowY: 'auto' }}>
        {NAV.map(({ to, icon, label }) => {
          const isActive = location.pathname.startsWith(to)
          return (
            <NavLink
              key={to}
              to={to}
              className={`sidebar-link ${isActive ? 'active' : ''}`}
            >
              <span style={{ fontSize: 15 }}>{icon}</span>
              <span>{label}</span>
            </NavLink>
          )
        })}
      </nav>

      {/* Footer */}
      <div style={{ padding: '12px 8px', borderTop: '1px solid var(--surface-border)' }}>
        <button
          className="sidebar-link btn-ghost"
          onClick={toggleTheme}
          style={{ width: '100%', cursor: 'pointer', background: 'none', border: 'none', marginBottom: 4 }}
        >
          <div style={{ fontSize: 16, width: 20, height: 20, display: 'flex', alignItems: 'center', justifyContent: 'center', position: 'relative' }}>
            <span className={`theme-icon ${theme === 'light' ? 'active' : ''}`}>☀️</span>
            <span className={`theme-icon ${theme === 'dark' ? 'active' : ''}`}>🌙</span>
          </div>
          <span style={{ fontSize: 13, marginLeft: 4 }}>Modo {theme === 'light' ? 'Claro' : 'Escuro'}</span>
        </button>

        <button
          className="sidebar-link btn-ghost"
          onClick={logout}
          style={{ width: '100%', cursor: 'pointer', background: 'none', border: 'none' }}
        >
          <div style={{ fontSize: 15, width: 20, display: 'flex', justifyContent: 'center' }}>🚪</div>
          <span style={{ fontSize: 13, marginLeft: 4 }}>Sair</span>
        </button>
      </div>
    </aside>
  )
}
