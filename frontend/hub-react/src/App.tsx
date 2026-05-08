import { useState, useEffect, useRef } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Menu } from 'lucide-react'
import Sidebar from './components/Sidebar'
import DevBanner from './components/DevBanner'
import PageTransition from './components/PageTransition'
import WelcomePage from './pages/WelcomePage'
import LoadingPage  from './pages/LoadingPage'
import type { Section } from './types'

/* ── Pages ── */
import PainelPage     from './pages/PainelPage'
import HubPage        from './pages/HubPage'
import CRMPage        from './pages/CRMPage'
import HubIAPage      from './pages/HubIAPage'
import CaptacaoPage   from './pages/CaptacaoPage'
import DocumentosPage from './pages/DocumentosPage'
import ConfigPage     from './pages/ConfigPage'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
})

type Phase = 'welcome' | 'loading' | 'hub'

export default function App() {
  const [phase, setPhase]           = useState<Phase>('welcome')
  const [fadeOut, setFadeOut]       = useState(false)
  const [shellReady, setShellReady] = useState(false)
  const [minDone, setMinDone]       = useState(false)
  const advancing                   = useRef(false)

  /* Fade-out → troca de fase → fade-in */
  function advanceTo(next: Phase) {
    if (advancing.current) return
    advancing.current = true
    setFadeOut(true)
    setTimeout(() => {
      setPhase(next)
      setFadeOut(false)
      advancing.current = false
    }, 360)
  }

  /* Ao entrar em 'loading': inicia timer mínimo */
  useEffect(() => {
    if (phase !== 'loading') return
    const t = setTimeout(() => setMinDone(true), 900)
    return () => clearTimeout(t)
  }, [phase])

  /* Avança para 'hub' quando Shell montou E tempo mínimo passou */
  useEffect(() => {
    if (phase === 'loading' && shellReady && minDone) {
      advanceTo('hub')
    }
  }, [shellReady, minDone, phase])

  /* ── Welcome ── */
  if (phase === 'welcome') {
    return (
      <div style={{
        opacity: fadeOut ? 0 : 1,
        transition: 'opacity 0.36s ease',
        width: '100vw', height: '100vh',
      }}>
        <WelcomePage
          onStart={() => {
            setShellReady(false)
            setMinDone(false)
            advanceTo('loading')
          }}
        />
      </div>
    )
  }

  /* ── Loading + Shell pré-carregando em background ── */
  return (
    <QueryClientProvider client={queryClient}>

      {/* Overlay de loading — visível enquanto phase === 'loading' */}
      {phase === 'loading' && (
        <div style={{
          position: 'fixed', inset: 0, zIndex: 100,
          opacity: fadeOut ? 0 : 1,
          transition: 'opacity 0.36s ease',
        }}>
          <LoadingPage />
        </div>
      )}

      {/* Shell — renderiza em background durante loading (pré-aquece queries) */}
      <div style={{
        opacity:        phase === 'hub' ? (fadeOut ? 0 : 1) : 0,
        transition:     phase === 'hub' ? 'opacity 0.36s ease' : 'none',
        pointerEvents:  phase === 'loading' ? 'none' : 'auto',
        width: '100vw', height: '100vh',
      }}>
        <Shell onReady={() => setShellReady(true)} />
      </div>

      <DevBanner />
    </QueryClientProvider>
  )
}

/* ── Shell ── */
interface ShellProps { onReady?: () => void }

function Shell({ onReady }: ShellProps) {
  const [section, setSection]         = useState<Section>('painel')
  const [clienteId, setClienteId]     = useState<number | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(false)

  /* Sinaliza que o Shell montou (DOM pronto, queries iniciadas) */
  useEffect(() => {
    onReady?.()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function selectCliente(id: number) {
    setClienteId(id)
    setSection('clientes')
    setSidebarOpen(false)
  }

  return (
    <div className="flex h-screen overflow-hidden bg-am-bg">

      {/* Overlay mobile */}
      {sidebarOpen && (
        <div className="fixed inset-0 bg-black/40 z-40 lg:hidden"
          onClick={() => setSidebarOpen(false)} />
      )}

      {/* Sidebar */}
      <div className={`fixed inset-y-0 left-0 z-50 w-72 flex-shrink-0 h-full sidebar-drawer
        lg:relative lg:translate-x-0
        ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}`}
      >
        <Sidebar
          activeSection={section}
          onSectionChange={(s) => { setSection(s); setSidebarOpen(false) }}
          activeClienteId={clienteId}
          onClienteSelect={selectCliente}
          onClose={() => setSidebarOpen(false)}
        />
      </div>

      {/* Área principal */}
      <main className="flex-1 flex flex-col min-w-0 overflow-hidden">

        {/* Topbar mobile */}
        <div className="lg:hidden flex items-center gap-3 px-4 py-3 flex-shrink-0"
          style={{ background: 'var(--color-sidebar-bg)', borderBottom: '1px solid var(--color-sidebar-border)' }}>
          <button onClick={() => setSidebarOpen(true)} className="p-1.5 rounded-lg"
            style={{ color: 'var(--color-sidebar-muted)' }}>
            <Menu size={18} />
          </button>
          <img src="/logo.png" alt="amicus" style={{ height: '24px', width: 'auto', filter: 'brightness(0) saturate(100%) invert(23%) sepia(82%) saturate(600%) hue-rotate(196deg)' }} />
        </div>

        {/* Conteúdo por seção */}
        <PageTransition id={section} className="flex-1 overflow-hidden">
          {section === 'painel'     && <PainelPage onSelectCliente={selectCliente} />}
          {section === 'clientes'   && <HubPage activeId={clienteId} onSelect={setClienteId} />}
          {section === 'crm'        && <CRMPage onSelectCliente={selectCliente} />}
          {section === 'hub-ia'     && <HubIAPage />}
          {section === 'captacao'   && <CaptacaoPage />}
          {section === 'documentos' && <DocumentosPage />}
          {section === 'config'     && <ConfigPage />}
        </PageTransition>
      </main>
    </div>
  )
}
