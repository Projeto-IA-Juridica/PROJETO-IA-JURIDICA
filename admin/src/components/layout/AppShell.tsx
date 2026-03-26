import type { ReactNode } from 'react'
import Sidebar from './Sidebar'

export default function AppShell({ children }: { children: ReactNode }) {
  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
      <Sidebar />
      <main style={{ flex: 1, overflowY: 'auto', background: 'var(--surface-base)' }}>
        <div style={{ maxWidth: 1400, margin: '0 auto', padding: '28px 32px' }}>
          {children}
        </div>
      </main>
    </div>
  )
}
