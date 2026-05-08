import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { FileText, BarChart3, MessageSquare, BookOpen, Scale } from 'lucide-react'
import ProcessoTab from '../tabs/ProcessoTab'
import ScoreTab from '../tabs/ScoreTab'
import ChatTab from '../tabs/ChatTab'
import DocumentosTab from '../tabs/DocumentosTab'
import RiskChip from '../components/RiskChip'
import { fetchClientes } from '../api/crm'
import { fetchProcessos } from '../api/processos'

type Tab = 'processo' | 'score' | 'chat' | 'documentos'

const TABS: { id: Tab; icon: React.ReactNode; label: string }[] = [
  { id: 'processo',   icon: <FileText size={13} />,      label: 'Processo'       },
  { id: 'score',      icon: <BarChart3 size={13} />,     label: 'Score de Risco' },
  { id: 'chat',       icon: <MessageSquare size={13} />, label: 'IA Assistente'  },
  { id: 'documentos', icon: <BookOpen size={13} />,      label: 'Documentos'     },
]

interface Props {
  activeId: number | null
  onSelect: (id: number) => void
}

export default function HubPage({ activeId, onSelect: _onSelect }: Props) {
  const [activeTab, setActiveTab] = useState<Tab>('processo')

  const { data: clientes } = useQuery({
    queryKey: ['clientes'],
    queryFn: fetchClientes,
    staleTime: 60_000,
  })

  const { data: processoData } = useQuery({
    queryKey: ['processos', activeId],
    queryFn: () => fetchProcessos(activeId!),
    enabled: activeId != null,
  })

  const cliente  = clientes?.find((c) => c.id === activeId) ?? null
  const processo = processoData?.items[0] ?? null

  return (
    <div className="flex flex-col h-full overflow-hidden bg-am-bg">

      {!cliente ? (
        <EmptyState />
      ) : (
          <>
            {/* Header */}
            <header className="flex-shrink-0 px-4 sm:px-6 py-4 border-b border-am-border bg-white card-shadow">
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <div className="flex items-center gap-3 min-w-0">
                  <div
                    className="hidden sm:flex w-9 h-9 rounded-xl items-center justify-center text-sm font-bold text-white flex-shrink-0"
                    style={{ background: 'var(--color-am-blue)' }}
                  >
                    {cliente.nome.split(' ').slice(0, 2).map((n: string) => n[0].toUpperCase()).join('')}
                  </div>
                  <div className="min-w-0">
                    <h1 className="text-sm sm:text-base font-bold text-am-ink truncate">
                      {cliente.nome}
                    </h1>
                    <p className="text-[11px] text-am-muted mt-0.5 font-mono truncate">
                      {processo?.numero_cnj ?? 'Sem processo judicial vinculado'}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2 flex-shrink-0">
                  {processo?.polo_cliente && (
                    <span
                      className="text-[10px] sm:text-xs font-bold px-2 py-1 rounded-lg"
                      style={processo.polo_cliente === 'autor'
                        ? { color: '#1A9E78', background: 'rgba(26,158,120,0.08)', border: '1px solid rgba(26,158,120,0.22)' }
                        : { color: '#C83030', background: 'rgba(200,48,48,0.08)',  border: '1px solid rgba(200,48,48,0.22)'  }
                      }
                    >
                      {processo.polo_cliente === 'autor' ? 'Autor' : 'Réu'}
                    </span>
                  )}
                  {processo?.score_risco != null && (
                    <RiskChip nivel={processo.score_nivel} score={processo.score_risco} size="md" />
                  )}
                </div>
              </div>
            </header>

            {/* Tab nav */}
            <nav className="flex-shrink-0 flex items-center gap-0.5 px-3 sm:px-6 py-2 border-b border-am-border bg-white overflow-x-auto">
              {TABS.map((t) => {
                const disabled = t.id === 'score' && !processo?.score_risco
                const active   = activeTab === t.id
                return (
                  <button
                    key={t.id}
                    disabled={disabled}
                    onClick={() => setActiveTab(t.id)}
                    className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold whitespace-nowrap press flex-shrink-0"
                    style={{
                      background:  active ? 'var(--color-am-surface)' : 'transparent',
                      color:       active ? 'var(--color-am-blue)'
                                 : disabled ? 'var(--color-am-muted)'
                                 : 'var(--color-am-secondary)',
                      borderBottom: active ? `2px solid var(--color-am-blue)` : '2px solid transparent',
                      cursor: disabled ? 'not-allowed' : 'pointer',
                      opacity: disabled ? 0.45 : 1,
                    }}
                  >
                    {t.icon}
                    <span className="hidden sm:inline">{t.label}</span>
                  </button>
                )
              })}
            </nav>

            {/* Conteúdo */}
            <div className={`flex-1 overflow-hidden ${activeTab === 'chat' ? 'flex flex-col' : 'overflow-y-auto'}`}>
              {activeTab === 'processo'   && <ProcessoTab   cliente={cliente} />}
              {activeTab === 'score'      && <ScoreTab      cliente={cliente} />}
              {activeTab === 'chat'       && <ChatTab       cliente={cliente} />}
              {activeTab === 'documentos' && <DocumentosTab />}
            </div>
          </>
        )}
    </div>
  )
}

function EmptyState() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-5 px-6 text-center">
      <div
        className="w-16 h-16 rounded-2xl flex items-center justify-center"
        style={{ background: 'var(--color-am-surface)', border: '1px solid var(--color-am-border)' }}
      >
        <Scale size={28} strokeWidth={1.5} className="text-am-blue" />
      </div>
      <div>
        <div className="text-base font-bold text-am-ink mb-1">Selecione um cliente</div>
        <div className="text-sm text-am-muted max-w-xs leading-relaxed">
          Escolha um cliente na lista para ver processos, score de risco e conversar com a IA.
        </div>
      </div>
      <div className="flex items-center gap-4 mt-1">
        {[
          { icon: <FileText size={13} />,      label: 'Processos'  },
          { icon: <BarChart3 size={13} />,     label: 'Score IA'   },
          { icon: <MessageSquare size={13} />, label: 'Assistente' },
        ].map(({ icon, label }) => (
          <div key={label} className="flex flex-col items-center gap-1.5">
            <div
              className="w-9 h-9 rounded-xl flex items-center justify-center text-am-blue"
              style={{ background: 'var(--color-am-surface)', border: '1px solid var(--color-am-border)' }}
            >
              {icon}
            </div>
            <span className="text-[10px] font-medium text-am-muted">{label}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
