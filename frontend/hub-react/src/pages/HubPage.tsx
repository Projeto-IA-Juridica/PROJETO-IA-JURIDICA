import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { FileText, BarChart3, MessageSquare, BookOpen } from 'lucide-react'
import Sidebar from '../components/Sidebar'
import ProcessoTab from '../tabs/ProcessoTab'
import ScoreTab from '../tabs/ScoreTab'
import ChatTab from '../tabs/ChatTab'
import DocumentosTab from '../tabs/DocumentosTab'
import RiskChip from '../components/RiskChip'
import { fetchClientes } from '../api/crm'
import { fetchProcessos } from '../api/processos'

type Tab = 'processo' | 'score' | 'chat' | 'documentos'

const TABS: { id: Tab; icon: React.ReactNode; label: string }[] = [
  { id: 'processo',   icon: <FileText size={12} />,    label: 'Processo' },
  { id: 'score',      icon: <BarChart3 size={12} />,   label: 'Score de Risco' },
  { id: 'chat',       icon: <MessageSquare size={12} />, label: 'IA Assistente' },
  { id: 'documentos', icon: <BookOpen size={12} />,    label: 'Documentos' },
]

export default function HubPage() {
  const [activeId, setActiveId] = useState<number | null>(null)
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

  const cliente = clientes?.find((c) => c.id === activeId) ?? null
  const processo = processoData?.items[0] ?? null

  function select(id: number) {
    setActiveId(id)
    setActiveTab('processo')
  }

  return (
    <div className="flex h-screen overflow-hidden bg-am-bg">

      {/* Sidebar — fixed width */}
      <div className="w-72 flex-shrink-0 h-full">
        <Sidebar activeId={activeId} onSelect={select} />
      </div>

      {/* Detail pane */}
      <main className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {!cliente ? (
          <EmptyState />
        ) : (
          <>
            {/* Header */}
            <header className="flex-shrink-0 px-6 py-4 border-b border-am-border bg-white">
              <div className="flex items-start justify-between">
                <div>
                  <h1 className="text-base font-semibold text-am-ink">{cliente.nome}</h1>
                  <p className="text-xs text-am-muted mt-0.5 font-mono">
                    {processo?.numero_cnj ?? 'Sem processo judicial vinculado'}
                  </p>
                </div>
                <div className="flex items-center gap-2 mt-0.5">
                  {processo?.polo_cliente && (
                    <span className={`text-[10px] font-semibold px-2 py-1 rounded-md
                      ${processo.polo_cliente === 'autor'
                        ? 'text-am-green bg-green-50 border border-green-100'
                        : 'text-am-red bg-red-50 border border-red-100'}`}
                    >
                      {processo.polo_cliente === 'autor' ? 'Autor' : 'Réu'}
                    </span>
                  )}
                  {processo?.score_risco != null && (
                    <RiskChip
                      nivel={processo.score_nivel}
                      score={processo.score_risco}
                      size="md"
                    />
                  )}
                </div>
              </div>
            </header>

            {/* Tab nav */}
            <nav className="flex-shrink-0 flex items-center gap-0 px-6 border-b border-am-border bg-white">
              {TABS.map((t) => {
                const disabled = t.id === 'score' && !processo?.score_risco
                return (
                  <button
                    key={t.id}
                    disabled={disabled}
                    onClick={() => setActiveTab(t.id)}
                    className={`flex items-center gap-1.5 px-4 py-3 text-xs font-medium border-b-2 -mb-px
                      transition-colors
                      ${activeTab === t.id
                        ? 'border-am-blue text-am-blue'
                        : 'border-transparent text-am-muted hover:text-am-secondary'}
                      ${disabled ? 'opacity-40 cursor-not-allowed' : 'cursor-pointer'}`}
                  >
                    {t.icon}
                    {t.label}
                  </button>
                )
              })}
            </nav>

            {/* Tab content */}
            <div className={`flex-1 overflow-hidden ${activeTab === 'chat' ? 'flex flex-col' : 'overflow-y-auto'}`}>
              {activeTab === 'processo'   && <ProcessoTab   cliente={cliente} />}
              {activeTab === 'score'      && <ScoreTab      cliente={cliente} />}
              {activeTab === 'chat'       && <ChatTab       cliente={cliente} />}
              {activeTab === 'documentos' && <DocumentosTab />}
            </div>
          </>
        )}
      </main>
    </div>
  )
}

function EmptyState() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-4 text-am-muted">
      <div className="w-14 h-14 rounded-2xl bg-am-surface flex items-center justify-center">
        <MessageSquare size={24} strokeWidth={1.5} className="text-am-blue-light" />
      </div>
      <div className="text-center">
        <div className="text-sm font-medium text-am-secondary">Selecione um cliente</div>
        <div className="text-xs text-am-muted mt-1">Escolha um cliente na lista à esquerda</div>
      </div>
    </div>
  )
}
