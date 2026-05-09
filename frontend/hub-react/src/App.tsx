import { useState, useEffect, useRef } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  LayoutDashboard, Users, Heart, Sparkles,
  Target, FolderOpen, Settings,
} from 'lucide-react'
import DevBanner from './components/DevBanner'
import PageTransition from './components/PageTransition'
import { FloatingDock } from './components/ui/FloatingDock'
import type { DockItem } from './components/ui/FloatingDock'
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
    }, 220)
  }

  /* Ao entrar em 'loading': inicia timer mínimo */
  useEffect(() => {
    if (phase !== 'loading') return
    const t = setTimeout(() => setMinDone(true), 300)
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
        transition: 'opacity 0.22s ease',
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
          transition: 'opacity 0.22s ease',
        }}>
          <LoadingPage />
        </div>
      )}

      {/* Shell — renderiza em background durante loading (pré-aquece queries) */}
      <div style={{
        opacity:        phase === 'hub' ? (fadeOut ? 0 : 1) : 0,
        transition:     phase === 'hub' ? 'opacity 0.22s ease' : 'none',
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

const NAV_ITEMS: { id: Section; label: string; icon: React.ReactNode }[] = [
  { id: 'painel',     label: 'Painel',          icon: <LayoutDashboard size={18} /> },
  { id: 'clientes',   label: 'Clientes',         icon: <Users      size={18} /> },
  { id: 'crm',        label: 'Relacionamento',   icon: <Heart      size={18} /> },
  { id: 'hub-ia',     label: 'Hub IA',           icon: <Sparkles   size={18} /> },
  { id: 'captacao',   label: 'Captação',         icon: <Target     size={18} /> },
  { id: 'documentos', label: 'Documentos',       icon: <FolderOpen size={18} /> },
  { id: 'config',     label: 'Configurações',    icon: <Settings   size={18} /> },
]

function Shell({ onReady }: ShellProps) {
  const [section, setSection]     = useState<Section>('painel')
  const [clienteId, setClienteId] = useState<number | null>(null)

  useEffect(() => {
    onReady?.()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function selectCliente(id: number) {
    setClienteId(id)
    setSection('clientes')
  }

  const dockItems: DockItem[] = NAV_ITEMS.map((n) => ({
    id:      n.id,
    title:   n.label,
    icon:    n.icon,
    active:  section === n.id,
    onClick: () => setSection(n.id),
  }))

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-am-bg">

      {/* Conteúdo — padding-bottom para não ficar atrás da dock */}
      <PageTransition id={section} className="flex-1 overflow-hidden pb-24">
        {section === 'painel'     && <PainelPage onSelectCliente={selectCliente} />}
        {section === 'clientes'   && <HubPage activeId={clienteId} onSelect={setClienteId} onBack={() => setClienteId(null)} />}
        {section === 'crm'        && <CRMPage onSelectCliente={selectCliente} />}
        {section === 'hub-ia'     && <HubIAPage />}
        {section === 'captacao'   && <CaptacaoPage />}
        {section === 'documentos' && <DocumentosPage />}
        {section === 'config'     && <ConfigPage />}
      </PageTransition>

      {/* Floating Dock */}
      <FloatingDock items={dockItems} />
    </div>
  )
}
