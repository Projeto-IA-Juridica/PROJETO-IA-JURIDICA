import { useState, useEffect, useRef } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import {
  LayoutDashboard, Users, Heart, Brain,
  Target, FolderOpen, CreditCard, Settings,
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
import { getAccessToken, refreshAccessToken, fetchMe, clearAuth } from './api/auth'

/* ── Pages ── */
import PainelPage     from './pages/PainelPage'
import HubPage        from './pages/HubPage'
import CRMPage        from './pages/CRMPage'
import HubIAPage      from './pages/HubIAPage'
import CaptacaoPage   from './pages/CaptacaoPage'
import DocumentosPage from './pages/DocumentosPage'
import PlanosPage     from './pages/PlanosPage'
import ConfigPage     from './pages/ConfigPage'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
})

type Phase = 'login' | 'ajuda' | 'onboarding' | 'welcome' | 'loading' | 'hub'

export default function App() {
  // Se já há token no localStorage, pula direto para loading (restaura sessão)
  const [phase, setPhase]           = useState<Phase>(() => getAccessToken() ? 'loading' : 'welcome')
  const [fadeOut, setFadeOut]       = useState(false)
  const [shellReady, setShellReady] = useState(false)
  const [minDone, setMinDone]       = useState(false)
  const advancing                   = useRef(false)
  // false enquanto valida o token existente; true quando validado ou quando não há token
  const [sessionChecked, setSessionChecked] = useState<boolean>(() => !getAccessToken())

  /* Valida token existente ao recarregar a página */
  useEffect(() => {
    if (sessionChecked) return
    fetchMe()
      .then(() => setSessionChecked(true))
      .catch(async () => {
        try {
          await refreshAccessToken()
          setSessionChecked(true)
        } catch {
          clearAuth()
          setSessionChecked(true)
          setPhase('login')
        }
      })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  /* Sessão expirada (refresh token inválido) — volta para login */
  useEffect(() => {
    function onExpired() { advanceTo('login') }
    window.addEventListener('amicus:session-expired', onExpired)
    return () => window.removeEventListener('amicus:session-expired', onExpired)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

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

  /* Avança para 'hub' quando Shell montou, tempo mínimo passou E sessão foi validada */
  useEffect(() => {
    if (phase === 'loading' && shellReady && minDone && sessionChecked) {
      advanceTo('hub')
    }
  }, [shellReady, minDone, phase, sessionChecked])

  const wrapStyle = {
    opacity: fadeOut ? 0 : 1,
    transition: 'opacity 0.22s ease',
    width: '100vw', height: '100vh',
  }

  /* ── Welcome (splash inicial) ── */
  if (phase === 'welcome') {
    return (
      <div style={wrapStyle}>
        <WelcomePage onStart={() => advanceTo('login')} />
      </div>
    )
  }

  /* ── Login ── */
  if (phase === 'login') {
    return (
      <div style={wrapStyle}>
        <LoginPage
          onLogin={() => { setShellReady(false); setMinDone(false); setSessionChecked(true); advanceTo('loading') }}
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
          onComplete={() => { setShellReady(false); setMinDone(false); setSessionChecked(true); advanceTo('loading') }}
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
  { id: 'planos',     label: 'Planos',           icon: <CreditCard size={18} /> },
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

      {/* Skip to content */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-[200] focus:px-4 focus:py-2 focus:rounded-lg focus:text-xs focus:font-semibold focus:bg-am-blue focus:text-white"
      >
        Pular para o conteúdo
      </a>

      {/* Top bar */}
      <header className="flex-shrink-0 flex items-center px-6 pt-5 pb-2">
        <img src="/logo.png" alt="" aria-hidden="true" style={{ width: 28, height: 28, objectFit: 'contain', opacity: 0.85 }} />
        <span className="ml-2.5 text-xl font-black tracking-tight select-none"
          style={{
            background: 'linear-gradient(135deg, #0C1E30 0%, #1248BE 100%)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            backgroundClip: 'text',
          }}>
          amicus
        </span>
      </header>

      {/* Conteúdo — padding-bottom para não ficar atrás da dock */}
      <main id="main-content" className="flex-1 overflow-hidden">
        <PageTransition id={section} className="h-full overflow-hidden pb-20">
          {section === 'painel'     && <PainelPage onSelectCliente={selectCliente} />}
          {section === 'clientes'   && <HubPage activeId={clienteId} onSelect={setClienteId} onBack={() => setClienteId(null)} />}
          {section === 'crm'        && <CRMPage onSelectCliente={selectCliente} />}
          {section === 'hub-ia'     && <HubIAPage />}
          {section === 'captacao'   && <CaptacaoPage />}
          {section === 'documentos' && <DocumentosPage />}
          {section === 'planos'     && <PlanosPage />}
          {section === 'config'     && <ConfigPage />}
        </PageTransition>
      </main>

      {/* Floating Dock */}
      <nav aria-label="Navegação principal">
        <FloatingDock items={dockItems} />
      </nav>
    </div>
  )
}
