import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import { FileText, BarChart3, MessageSquare, BookOpen, ArrowLeft, Search, Users, Scale, Clock, Upload, Download, Trash2, AlertTriangle } from 'lucide-react'
import ProcessoTab from '../tabs/ProcessoTab'
import ScoreTab from '../tabs/ScoreTab'
import ChatTab from '../tabs/ChatTab'
import DocumentosTab from '../tabs/DocumentosTab'
import RiskChip from '../components/RiskChip'
import { fetchClientes } from '../api/crm'
import { fetchProcessos } from '../api/processos'
import { exportarCliente, deletarClienteLGPD } from '../api/clientes'
import CadastroCSVPage from './CadastroCSVPage'

type Tab = 'processo' | 'score' | 'chat' | 'documentos'

const TABS: { id: Tab; icon: React.ReactNode; label: string }[] = [
  { id: 'processo',   icon: <FileText size={13} />,      label: 'Processo'   },
  { id: 'score',      icon: <BarChart3 size={13} />,     label: 'Score'      },
  { id: 'chat',       icon: <MessageSquare size={13} />, label: 'Assistente' },
  { id: 'documentos', icon: <BookOpen size={13} />,      label: 'Documentos' },
]

interface Props {
  activeId: number | null
  onSelect: (id: number) => void
  onBack?: () => void
}

export default function HubPage({ activeId, onSelect, onBack }: Props) {
  const [activeTab, setActiveTab]         = useState<Tab>('processo')
  const [search, setSearch]               = useState('')
  const [showCSV, setShowCSV]             = useState(false)
  const [confirmarDelete, setConfirmarDelete] = useState(false)

  const qc = useQueryClient()

  const exportarMut = useMutation({
    mutationFn: () => exportarCliente(activeId!),
  })

  const deletarMut = useMutation({
    mutationFn: () => deletarClienteLGPD(activeId!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['clientes'] })
      onBack?.()
    },
    onSettled: () => setConfirmarDelete(false),
  })

  const { data: clientes, isLoading } = useQuery({
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

  /* ── CSV import ── */
  if (showCSV) return <CadastroCSVPage onBack={() => setShowCSV(false)} />

  /* ── Lista de clientes ── */
  if (!cliente) {
    const filtered = (clientes ?? []).filter((c) =>
      c.nome.toLowerCase().includes(search.toLowerCase())
    )

    return (
      <div className="flex flex-col h-full overflow-hidden bg-am-bg">
        <div className="flex flex-col h-full w-full max-w-3xl mx-auto">

          {/* Header */}
          <div className="flex-shrink-0 px-4 pt-5 pb-3">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-9 h-9 rounded-2xl flex items-center justify-center flex-shrink-0"
                style={{ background: 'linear-gradient(135deg,#1248BE,#4A8ED4)', boxShadow: '0 4px 12px rgba(18,72,190,0.22)' }}>
                <Users size={16} className="text-white" />
              </div>
              <div className="flex-1">
                <h1 className="text-sm font-bold text-am-ink">Clientes</h1>
                <p className="text-[11px] text-am-muted">{clientes?.length ?? 0} cadastrados</p>
              </div>
              <button
                onClick={() => setShowCSV(true)}
                className="press flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold text-white flex-shrink-0"
                style={{ background: 'linear-gradient(135deg,#1248BE,#3A7AB8)', border: 'none', cursor: 'pointer', fontFamily: 'var(--font-sans)' }}>
                <Upload size={12} /> Importar CSV
              </button>
            </div>

            {/* Search */}
            <div className="relative">
              <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-am-muted pointer-events-none" />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Buscar cliente..."
                className="w-full pl-8 pr-4 py-2.5 rounded-xl text-xs text-am-ink placeholder:text-am-muted outline-none"
                style={{
                  background: 'white',
                  border: '1px solid var(--color-am-border)',
                  boxShadow: '0 1px 4px rgba(12,30,48,0.05)',
                }}
              />
            </div>
          </div>

          {/* Lista */}
          <div className="flex-1 overflow-y-auto px-4 pb-4 space-y-2">
            {isLoading && (
              <div className="flex items-center justify-center h-32">
                <div className="w-5 h-5 rounded-full border-2 border-am-blue border-t-transparent animate-spin" />
              </div>
            )}

            {/* Sem clientes cadastrados → CTA de importação */}
            {!isLoading && (clientes ?? []).length === 0 && (
              <div className="flex flex-col items-center justify-center gap-4 py-12">
                <div className="w-14 h-14 rounded-2xl flex items-center justify-center"
                  style={{ background: 'rgba(18,72,190,0.07)', border: '1px solid rgba(18,72,190,0.15)' }}>
                  <Users size={22} style={{ color: 'var(--color-am-blue)' }} />
                </div>
                <div className="text-center">
                  <p className="text-sm font-bold text-am-ink mb-1">Nenhum cliente ainda</p>
                  <p className="text-xs text-am-muted leading-relaxed">Importe sua base de clientes via CSV<br/>para começar a usar o amicus.</p>
                </div>
                <button
                  onClick={() => setShowCSV(true)}
                  className="press flex items-center gap-2 px-5 py-2.5 rounded-xl text-xs font-bold text-white"
                  style={{ background: 'linear-gradient(135deg,#1248BE,#3A7AB8)', boxShadow: '0 4px 14px rgba(18,72,190,0.25)', border: 'none', cursor: 'pointer', fontFamily: 'var(--font-sans)' }}>
                  <Upload size={13} /> Importar clientes via CSV
                </button>
              </div>
            )}

            {/* Sem resultado de busca */}
            {!isLoading && (clientes ?? []).length > 0 && filtered.length === 0 && (
              <div className="flex items-center justify-center h-32">
                <p className="text-xs text-am-muted">Nenhum cliente encontrado</p>
              </div>
            )}
            {filtered.map((c) => {
              const initials = c.nome.split(' ').slice(0, 2).map((n: string) => n[0].toUpperCase()).join('')
              return (
                <motion.button
                  key={c.id}
                  onClick={() => onSelect(c.id)}
                  whileHover={{ scale: 1.01 }}
                  whileTap={{ scale: 0.98 }}
                  transition={{ type: 'spring', stiffness: 400, damping: 28 }}
                  className="w-full flex items-start gap-3 px-4 py-3.5 rounded-2xl text-left"
                  style={{
                    background: 'white',
                    border: '1px solid var(--color-am-border)',
                    boxShadow: '0 1px 4px rgba(12,30,48,0.05)',
                  }}
                >
                  {/* Avatar */}
                  <div className="w-9 h-9 rounded-xl flex items-center justify-center text-xs font-bold text-white flex-shrink-0 mt-0.5"
                    style={{ background: 'linear-gradient(135deg,#1248BE,#4A8ED4)' }}>
                    {initials}
                  </div>

                  {/* Info */}
                  <div className="min-w-0 flex-1">
                    {/* Nome + nível CRM */}
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-semibold text-am-ink truncate">{c.nome}</p>
                      {c.crm_nivel && (
                        <span className="flex-shrink-0 text-[10px] font-semibold px-1.5 py-0.5 rounded-md"
                          style={
                            c.crm_nivel === 'alto'
                              ? { color: '#C83030', background: 'rgba(200,48,48,0.08)', border: '1px solid rgba(200,48,48,0.18)' }
                              : c.crm_nivel === 'medio'
                              ? { color: '#D97706', background: 'rgba(217,119,6,0.08)',  border: '1px solid rgba(217,119,6,0.18)' }
                              : { color: '#1A9E78', background: 'rgba(26,158,120,0.08)', border: '1px solid rgba(26,158,120,0.18)' }
                          }>
                          {c.crm_nivel.charAt(0).toUpperCase() + c.crm_nivel.slice(1)}
                        </span>
                      )}
                    </div>

                    {/* Chips de info */}
                    <div className="flex items-center gap-3 mt-1.5">
                      <span className="flex items-center gap-1 text-[11px] text-am-muted">
                        <Scale size={11} />
                        {c.total_processos} processo{c.total_processos !== 1 ? 's' : ''}
                      </span>
                      {c.ultimo_contato && (
                        <span className="flex items-center gap-1 text-[11px] text-am-muted">
                          <Clock size={11} />
                          {new Date(c.ultimo_contato).toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' })}
                        </span>
                      )}
                      {c.telefone_whatsapp && (
                        <span className="text-[11px] text-am-muted truncate">{c.telefone_whatsapp}</span>
                      )}
                    </div>

                    {/* Resumo CRM */}
                    {c.crm_resumo && (
                      <p className="text-[11px] text-am-muted mt-1.5 leading-relaxed line-clamp-1">
                        {c.crm_resumo}
                      </p>
                    )}
                  </div>

                  <ArrowLeft size={13} className="text-am-muted rotate-180 flex-shrink-0 mt-1" />
                </motion.button>
              )
            })}
          </div>
        </div>
      </div>
    )
  }

  /* ── Detalhe do cliente ── */
  const initials = cliente.nome
    .split(' ').slice(0, 2).map((n: string) => n[0].toUpperCase()).join('')

  return (
    <div className="flex flex-col h-full overflow-hidden bg-am-bg">
      <div className="flex flex-col h-full w-full max-w-3xl mx-auto">

        {/* Header */}
        <div className="flex-shrink-0 px-4 pt-5 pb-4">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-3 min-w-0">
              <button onClick={onBack}
                className="flex-shrink-0 w-8 h-8 rounded-xl flex items-center justify-center text-am-muted hover:text-am-ink transition-colors"
                style={{ border: '1px solid var(--color-am-border)', background: 'white' }}>
                <ArrowLeft size={14} />
              </button>
              <div className="w-10 h-10 rounded-2xl flex items-center justify-center text-sm font-bold text-white flex-shrink-0"
                style={{ background: 'linear-gradient(135deg,#1248BE,#4A8ED4)', boxShadow: '0 4px 12px rgba(18,72,190,0.22)' }}>
                {initials}
              </div>
              <div className="min-w-0">
                <h1 className="text-sm font-bold text-am-ink truncate">{cliente.nome}</h1>
                <p className="text-[11px] text-am-muted mt-0.5 font-mono truncate">
                  {processo?.numero_cnj ?? 'Sem processo vinculado'}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2 flex-shrink-0">
              {processo?.polo_cliente && (
                <span className="text-[10px] font-semibold px-2 py-1 rounded-lg"
                  style={processo.polo_cliente === 'autor'
                    ? { color: '#1A9E78', background: 'rgba(26,158,120,0.08)', border: '1px solid rgba(26,158,120,0.20)' }
                    : { color: '#C83030', background: 'rgba(200,48,48,0.08)',  border: '1px solid rgba(200,48,48,0.20)'  }
                  }>
                  {processo.polo_cliente === 'autor' ? 'Autor' : 'Réu'}
                </span>
              )}
              {processo?.score_risco != null && (
                <RiskChip nivel={processo.score_nivel} score={processo.score_risco} size="md" />
              )}
            </div>
          </div>

          {/* LGPD */}
          <div className="flex items-center justify-end gap-2 mt-3">
            {confirmarDelete ? (
              <>
                <span className="flex items-center gap-1 text-[10px] text-am-muted font-medium">
                  <AlertTriangle size={11} style={{ color: '#C83030' }} />
                  Confirmar exclusão dos dados?
                </span>
                <button
                  onClick={() => deletarMut.mutate()}
                  disabled={deletarMut.isPending}
                  className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-[10px] font-bold press"
                  style={{ background: 'rgba(200,48,48,0.10)', color: '#C83030', border: '1px solid rgba(200,48,48,0.25)', cursor: 'pointer' }}>
                  {deletarMut.isPending
                    ? <span className="w-3 h-3 rounded-full border border-current border-t-transparent animate-spin" />
                    : 'Confirmar'}
                </button>
                <button
                  onClick={() => setConfirmarDelete(false)}
                  disabled={deletarMut.isPending}
                  className="px-2.5 py-1 rounded-lg text-[10px] font-semibold press"
                  style={{ background: 'var(--color-am-surface)', color: 'var(--color-am-secondary)', border: '1px solid var(--color-am-border)', cursor: 'pointer' }}>
                  Cancelar
                </button>
              </>
            ) : (
              <>
                <button
                  onClick={() => exportarMut.mutate()}
                  disabled={exportarMut.isPending}
                  title="Exportar dados pessoais (LGPD Art. 18, V)"
                  className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-[10px] font-semibold press"
                  style={{ background: 'rgba(18,72,190,0.06)', color: 'var(--color-am-blue)', border: '1px solid rgba(18,72,190,0.18)', cursor: 'pointer' }}>
                  {exportarMut.isPending
                    ? <span className="w-3 h-3 rounded-full border border-current border-t-transparent animate-spin" />
                    : <Download size={10} />}
                  Exportar dados
                </button>
                <button
                  onClick={() => setConfirmarDelete(true)}
                  title="Direito ao esquecimento (LGPD Art. 18, IV)"
                  className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-[10px] font-semibold press"
                  style={{ background: 'rgba(200,48,48,0.06)', color: '#C83030', border: '1px solid rgba(200,48,48,0.18)', cursor: 'pointer' }}>
                  <Trash2 size={10} />
                  Apagar dados
                </button>
              </>
            )}
          </div>

          {/* Tab switcher */}
          <div className="flex gap-1 p-1 rounded-2xl mt-4" style={{ background: 'rgba(12,30,48,0.05)' }}>
            {TABS.map((t) => {
              const disabled = t.id === 'score' && !processo?.score_risco
              const active   = activeTab === t.id
              return (
                <motion.button
                  key={t.id}
                  disabled={disabled}
                  onClick={() => !disabled && setActiveTab(t.id)}
                  whileHover={{ scale: active || disabled ? 1 : 1.04 }}
                  whileTap={{ scale: disabled ? 1 : 0.95 }}
                  transition={{ type: 'spring', stiffness: 380, damping: 22 }}
                  className="relative flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold whitespace-nowrap flex-1 justify-center"
                  style={{
                    color:   active ? 'var(--color-am-blue)' : 'var(--color-am-muted)',
                    opacity: disabled ? 0.4 : 1,
                    cursor:  disabled ? 'not-allowed' : 'pointer',
                  }}
                >
                  <AnimatePresence>
                    {active && (
                      <motion.span
                        layoutId="hub-tab-pill"
                        className="absolute inset-0 rounded-xl"
                        style={{ background: 'white', boxShadow: '0 1px 6px rgba(18,72,190,0.12), 0 0 0 1px rgba(18,72,190,0.08)' }}
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        transition={{ type: 'spring', stiffness: 400, damping: 28 }}
                      />
                    )}
                  </AnimatePresence>
                  <span className="relative">{t.icon}</span>
                  <span className="relative hidden sm:inline">{t.label}</span>
                </motion.button>
              )
            })}
          </div>
        </div>

        {/* Conteúdo */}
        <div className={`flex-1 overflow-hidden px-4 pb-4 ${activeTab === 'chat' ? 'flex flex-col' : 'overflow-y-auto'}`}>
          {activeTab === 'processo'   && <ProcessoTab   cliente={cliente} />}
          {activeTab === 'score'      && <ScoreTab      cliente={cliente} />}
          {activeTab === 'chat'       && <ChatTab       cliente={cliente} />}
          {activeTab === 'documentos' && <DocumentosTab />}
        </div>

      </div>
    </div>
  )
}
