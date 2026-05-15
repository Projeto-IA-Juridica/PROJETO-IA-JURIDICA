import { useState, useEffect, useRef } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  LayoutDashboard, Users, Heart, Brain,
  Target, FolderOpen, Settings,
} from 'lucide-react'
import DevBanner from './components/DevBanner'
import PageTransition from './components/PageTransition'
import { FloatingDock } from './components/ui/FloatingDock'
import type { DockItem } from './components/ui/FloatingDock'
import WelcomePage     from './pages/WelcomePage'
import LoadingPage      from './pages/LoadingPage'
import LoginPage        from './pages/LoginPage'
import AjudaPage        from './pages/AjudaPage'
import OnboardingPage   from './pages/OnboardingPage'
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

type Phase = 'login' | 'ajuda' | 'onboarding' | 'welcome' | 'loading' | 'hub'

export default function App() {
  const [phase, setPhase]           = useState<Phase>('login')
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

  const wrapStyle = {
    opacity: fadeOut ? 0 : 1,
    transition: 'opacity 0.22s ease',
    width: '100vw', height: '100vh',
  }

  /* ── Login ── */
  if (phase === 'login') {
    return (
      <div style={wrapStyle}>
        <LoginPage
          onLogin={() => advanceTo('welcome')}
          onRegister={() => advanceTo('onboarding')}
          onAjuda={() => advanceTo('ajuda')}
        />
      </div>
    )
  }

  /* ── Ajuda / Fale conosco ── */
  if (phase === 'ajuda') {
    return (
      <div style={wrapStyle}>
        <AjudaPage onBack={() => advanceTo('login')} />
      </div>
    )
  }

  /* ── Onboarding / Cadastro ── */
  if (phase === 'onboarding') {
    return (
      <div style={{ ...wrapStyle, overflow: 'auto', height: 'auto', minHeight: '100vh' }}>
        <OnboardingPage
          onComplete={() => { setShellReady(false); setMinDone(false); advanceTo('loading') }}
        />
      </div>
    )
  }

  /* ── Welcome ── */
  if (phase === 'welcome') {
    return (
      <div style={wrapStyle}>
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
  { id: 'hub-ia',     label: 'Hub IA',           icon: <Brain      size={18} /> },
  { id: 'clientes',   label: 'Clientes',         icon: <Users      size={18} /> },
  { id: 'crm',        label: 'Relacionamento',   icon: <Heart      size={18} /> },
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

      {/* Top bar com logo */}
      <div className="flex-shrink-0 flex items-center px-5 pt-4 pb-1">
        <img src="/logo.png" alt="amicus" style={{ width: 30, height: 30, objectFit: 'contain' }} />
        <span className="ml-2 text-base font-black tracking-tight"
          style={{
            background: 'linear-gradient(135deg, #0C1E30 0%, #1248BE 100%)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            backgroundClip: 'text',
          }}>
          amicus
        </span>
      </div>

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
