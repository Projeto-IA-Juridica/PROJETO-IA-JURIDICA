import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  LayoutDashboard, Users, Heart, Sparkles, Target, MessageSquare,
  FolderOpen, Settings, Search, Shield, X, ChevronDown,
} from 'lucide-react'
import { fetchClientes } from '../api/crm'
import type { CRMClienteCard, Section } from '../types'

const NAV: { id: Section; icon: React.ReactNode; label: string }[] = [
  { id: 'painel',     icon: <LayoutDashboard size={15} />, label: 'Painel'          },
  { id: 'clientes',   icon: <Users size={15} />,           label: 'Clientes'        },
  { id: 'crm',        icon: <Heart size={15} />,           label: 'Relacionamento'  },
  { id: 'hub-ia',     icon: <Sparkles size={15} />,        label: 'Hub IA'          },
  { id: 'whatsapp',   icon: <MessageSquare size={15} />,   label: 'WhatsApp'        },
  { id: 'captacao',   icon: <Target size={15} />,          label: 'Captação'        },
  { id: 'documentos', icon: <FolderOpen size={15} />,      label: 'Documentos'      },
  { id: 'config',     icon: <Settings size={15} />,        label: 'Configurações'   },
]

const RISK_DOT: Record<string, string> = {
  baixo: '#1A9E78', moderado: '#D08010', alto: '#C83030', critico: '#C83030',
}

interface Props {
  activeSection: Section
  onSectionChange: (s: Section) => void
  activeClienteId: number | null
  onClienteSelect: (id: number) => void
  onClose?: () => void
}

function initials(nome: string) {
  return nome.split(' ').slice(0, 2).map((n) => n[0].toUpperCase()).join('')
}

const s = {
  bg:      'var(--color-sidebar-bg)',
  surface: 'var(--color-sidebar-surface)',
  hover:   'var(--color-sidebar-hover)',
  border:  'var(--color-sidebar-border)',
  ink:     'var(--color-sidebar-ink)',
  muted:   'var(--color-sidebar-muted)',
  blue:    'var(--color-am-blue)',
  blueL:   'var(--color-am-blue-light)',
}

export default function Sidebar({ activeSection, onSectionChange, activeClienteId, onClienteSelect, onClose }: Props) {
  const [search, setSearch] = useState('')
  const [clientListOpen, setClientListOpen] = useState(true)

  const isClientes = activeSection === 'clientes'

  const { data: clientes, isLoading, isError } = useQuery({
    queryKey: ['clientes'],
    queryFn: fetchClientes,
    staleTime: 60_000,
  })

  const filtered = clientes?.filter((c: CRMClienteCard) =>
    c.nome.toLowerCase().includes(search.toLowerCase())
  ) ?? []

  const riscoAlto = clientes?.filter((c: CRMClienteCard) =>
    c.crm_nivel === 'critico' || c.crm_nivel === 'em_risco'
  ).length ?? 0

  return (
    <aside className="flex flex-col h-full scrollbar-dark"
      style={{ background: s.bg, borderRight: `1px solid ${s.border}` }}>

      {/* ── Brand ── */}
      <div className="flex items-center justify-between px-5 py-4 flex-shrink-0"
        style={{ borderBottom: `1px solid ${s.border}` }}>
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 flex items-center justify-center flex-shrink-0">
            <img src="/logo.png" alt="amicus" className="w-full h-full object-contain" />
          </div>
          <div>
            <div className="font-bold text-sm tracking-tight" style={{ color: s.ink }}>amicus</div>
            <div className="text-[10px]" style={{ color: s.muted }}>Hub do Advogado</div>
          </div>
        </div>
        {onClose && (
          <button onClick={onClose} aria-label="Fechar menu" className="lg:hidden p-1.5 rounded-lg transition-fast"
            style={{ color: s.muted }}>
            <X size={16} />
          </button>
        )}
      </div>

      {/* ── IA status ── */}
      <div className="mx-4 mt-4 flex items-center gap-3 px-3.5 py-2.5 rounded-xl flex-shrink-0"
        style={{ background: s.surface, border: `1px solid ${s.border}` }}>
        <div className="relative flex-shrink-0">
          <div className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold"
            style={{ background: '#1A9E78', color: '#fff' }}>C</div>
          <span className="absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full glow-green"
            style={{ background: '#1A9E78', border: `2px solid ${s.bg}` }} />
        </div>
        <div className="min-w-0">
          <div className="text-xs font-semibold" style={{ color: s.ink }}>Dra. Camila</div>
          <div className="text-[10px]" style={{ color: s.muted }}>IA Ativa · Tom formal</div>
        </div>
        <span className="ml-auto text-[9px] font-bold px-1.5 py-0.5 rounded flex-shrink-0"
          style={{ background: 'rgba(26,158,120,0.18)', color: '#1A9E78' }}>
          ONLINE
        </span>
      </div>

      {/* ── Navegação de seções ── */}
      <div className="px-3 mt-4 space-y-0.5 flex-shrink-0">
        <div className="text-[9px] font-bold uppercase tracking-widest px-2 mb-2"
          style={{ color: s.muted }}>Menu</div>
        {NAV.map((item) => {
          const active = activeSection === item.id
          return (
            <button key={item.id} onClick={() => onSectionChange(item.id)}
              aria-current={active ? 'page' : undefined}
              className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-left press"
              style={{
                background:  active ? s.hover : 'transparent',
                color:       active ? s.ink : s.muted,
                border:      active ? `1px solid rgba(58,122,184,0.2)` : '1px solid transparent',
                borderLeft:  active ? `3px solid ${s.blue}` : '3px solid transparent',
              }}
              onMouseEnter={(e) => { if (!active) e.currentTarget.style.background = s.surface }}
              onMouseLeave={(e) => { if (!active) e.currentTarget.style.background = 'transparent' }}
            >
              <span style={{ color: active ? s.blueL : s.muted }}>{item.icon}</span>
              <span className="text-xs font-medium">{item.label}</span>
              {item.id === 'clientes' && riscoAlto > 0 && (
                <span className="ml-auto text-[9px] font-bold px-1.5 py-0.5 rounded"
                  style={{ background: 'rgba(200,48,48,0.18)', color: '#C83030' }}>
                  {riscoAlto}
                </span>
              )}
            </button>
          )
        })}
      </div>

      {/* ── Lista de clientes (só na seção clientes) ── */}
      {isClientes && (
        <>
          <div className="px-3 mt-4 flex-shrink-0" style={{ borderTop: `1px solid ${s.border}`, paddingTop: 16 }}>
            {/* Toggle lista */}
            <button
              onClick={() => setClientListOpen((v) => !v)}
              aria-expanded={clientListOpen}
              aria-controls="client-list"
              className="w-full flex items-center justify-between px-2 mb-2 transition-fast"
            >
              <span className="text-[9px] font-bold uppercase tracking-widest" style={{ color: s.muted }}>
                Clientes
              </span>
              <ChevronDown size={12} style={{
                color: s.muted,
                transform: clientListOpen ? 'rotate(0deg)' : 'rotate(-90deg)',
                transition: 'transform 0.2s',
              }} />
            </button>

            {/* Busca */}
            {clientListOpen && (
              <div className="relative">
                <Search size={11} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: s.muted }} aria-hidden="true" />
                <label htmlFor="sidebar-search" className="sr-only">Buscar clientes</label>
                <input id="sidebar-search" type="text" value={search} onChange={(e) => setSearch(e.target.value)}
                  placeholder="Buscar…"
                  className="w-full pl-8 pr-3 py-2 text-xs rounded-lg outline-none transition-fast"
                  style={{ background: s.surface, border: `1px solid ${s.border}`, color: s.ink }}
                  onFocus={(e) => (e.target.style.borderColor = 'rgba(58,122,184,0.5)')}
                  onBlur={(e)  => (e.target.style.borderColor = s.border)}
                />
              </div>
            )}
          </div>

          {clientListOpen && (
            <div id="client-list" className="flex-1 overflow-y-auto pb-4 scrollbar-dark px-3 space-y-0.5 mt-1">
              {isLoading && Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="h-12 rounded-xl skeleton mx-1"
                  style={{ background: 'rgba(255,255,255,0.04)' }} />
              ))}

              {isError && (
                <div className="flex items-center gap-2 mx-1 mt-2 p-3 rounded-xl"
                  style={{ background: 'rgba(200,48,48,0.1)', border: '1px solid rgba(200,48,48,0.2)' }}>
                  <Shield size={12} style={{ color: '#C83030' }} className="flex-shrink-0" />
                  <span className="text-xs" style={{ color: '#e8a0a0' }}>Erro ao carregar.</span>
                </div>
              )}

              {!isLoading && !isError && filtered.length === 0 && (
                <p className="text-xs text-center mt-4 px-4" style={{ color: s.muted }}>
                  Nenhum cliente encontrado
                </p>
              )}

              {filtered.map((c) => {
                const dotColor = c.crm_nivel ? (RISK_DOT[c.crm_nivel] ?? 'transparent') : 'transparent'
                const active   = c.id === activeClienteId
                return (
                  <button key={c.id} onClick={() => onClienteSelect(c.id)}
                    className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-left press"
                    style={{
                      background:  active ? s.hover : 'transparent',
                      border:      active ? `1px solid rgba(58,122,184,0.25)` : '1px solid transparent',
                      borderLeft:  active ? `3px solid ${s.blue}` : '3px solid transparent',
                    }}
                    onMouseEnter={(e) => { if (!active) e.currentTarget.style.background = s.surface }}
                    onMouseLeave={(e) => { if (!active) e.currentTarget.style.background = 'transparent' }}
                  >
                    <div className="w-7 h-7 rounded-full flex items-center justify-center text-[10px] font-bold flex-shrink-0"
                      style={{ background: 'rgba(168,200,232,0.12)', color: s.blueL }}>
                      {initials(c.nome)}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-xs font-medium truncate" style={{ color: s.ink }}>{c.nome}</div>
                      <div className="text-[10px] truncate mt-0.5" style={{ color: s.muted }}>
                        {c.total_processos > 0 ? `${c.total_processos} processo${c.total_processos > 1 ? 's' : ''}` : 'Sem processo'}
                      </div>
                    </div>
                    {dotColor !== 'transparent' && (
                      <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: dotColor }} />
                    )}
                  </button>
                )
              })}
            </div>
          )}
        </>
      )}

      {!isClientes && <div className="flex-1" />}
    </aside>
  )
}
