import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Heart, Search, ArrowRight, Shield, Clock, Star, Zap, RefreshCw, AlertCircle } from 'lucide-react'
import { fetchClientes, analisarCliente, analisarEscritorioCompleto } from '../api/crm'
import type { CRMClienteCard } from '../types'

const NIVEIS = ['todos', 'critico', 'alto', 'moderado', 'baixo', 'sem_analise'] as const
type Nivel = typeof NIVEIS[number]

const NIVEL_CFG: Record<string, { color: string; bg: string; border: string; label: string }> = {
  baixo:       { color: '#1A9E78', bg: 'rgba(26,158,120,0.08)',  border: 'rgba(26,158,120,0.22)',  label: 'Baixo'      },
  moderado:    { color: '#D08010', bg: 'rgba(208,128,16,0.08)',  border: 'rgba(208,128,16,0.22)',  label: 'Moderado'   },
  alto:        { color: '#C83030', bg: 'rgba(200,48,48,0.08)',   border: 'rgba(200,48,48,0.22)',   label: 'Alto'       },
  critico:     { color: '#C83030', bg: 'rgba(200,48,48,0.08)',   border: 'rgba(200,48,48,0.22)',   label: 'Crítico'    },
  em_risco:    { color: '#C83030', bg: 'rgba(200,48,48,0.08)',   border: 'rgba(200,48,48,0.22)',   label: 'Em risco'   },
  sem_analise: { color: '#8AAAC0', bg: 'rgba(138,170,192,0.08)', border: 'rgba(138,170,192,0.22)', label: 'Sem análise'},
}

function initials(nome: string) {
  return nome.split(' ').slice(0, 2).map(n => n[0].toUpperCase()).join('')
}

function formatDate(iso: string | null) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' })
}

interface Props { onSelectCliente: (id: number) => void }

export default function CRMPage({ onSelectCliente }: Props) {
  const qc = useQueryClient()
  const [search, setSearch]           = useState('')
  const [nivel, setNivel]             = useState<Nivel>('todos')
  const [analisandoId, setAnalisandoId] = useState<number | null>(null)
  const [erroId, setErroId]           = useState<{ id: number; msg: string } | null>(null)
  const [batchMsg, setBatchMsg]       = useState<string | null>(null)
  const [batchErro, setBatchErro]     = useState<string | null>(null)

  const { data: clientes, isLoading, isError } = useQuery({
    queryKey: ['clientes'],
    queryFn: fetchClientes,
    staleTime: 60_000,
  })

  const analisarClienteMut = useMutation({
    mutationFn: (clienteId: number) => analisarCliente(clienteId),
    onMutate: (clienteId) => { setAnalisandoId(clienteId); setErroId(null) },
    onSuccess: () => {
      setAnalisandoId(null)
      qc.invalidateQueries({ queryKey: ['clientes'] })
    },
    onError: (e: unknown, clienteId) => {
      setAnalisandoId(null)
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        ?? 'Erro ao analisar'
      setErroId({ id: clienteId, msg })
      setTimeout(() => setErroId(null), 5000)
    },
  })

  const analisarEscritoriMut = useMutation({
    mutationFn: () => analisarEscritorioCompleto(),
    onSuccess: () => {
      setBatchErro(null)
      setBatchMsg('Análise do escritório iniciada! Os resultados aparecem em alguns minutos.')
      setTimeout(() => setBatchMsg(null), 8000)
    },
    onError: (e: unknown) => {
      setBatchMsg(null)
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        ?? 'Erro ao iniciar análise'
      setBatchErro(msg)
      setTimeout(() => setBatchErro(null), 6000)
    },
  })

  const filtered = (clientes ?? []).filter((c: CRMClienteCard) => {
    const matchSearch = c.nome.toLowerCase().includes(search.toLowerCase())
    const matchNivel  = nivel === 'todos' ? true
      : nivel === 'sem_analise' ? !c.crm_nivel
      : c.crm_nivel === nivel
    return matchSearch && matchNivel
  })

  const countFor = (n: Nivel) =>
    n === 'todos'       ? (clientes?.length ?? 0)
    : n === 'sem_analise' ? (clientes?.filter(c => !c.crm_nivel).length ?? 0)
    : (clientes?.filter(c => c.crm_nivel === n).length ?? 0)

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="p-4 sm:p-6 max-w-5xl mx-auto space-y-5 page-enter">

        {/* Header */}
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0"
              style={{ background: 'rgba(200,48,48,0.08)', border: '1px solid rgba(200,48,48,0.2)' }}>
              <Heart size={16} style={{ color: '#C83030' }} />
            </div>
            <div>
              <h2 className="text-lg font-extrabold text-am-ink tracking-tight">Relacionamento de Clientes</h2>
              <p className="text-xs text-am-muted mt-0.5">CRM · Análise de saúde e ações recomendadas</p>
            </div>
          </div>

          {/* Botão análise do escritório */}
          <button
            onClick={() => analisarEscritoriMut.mutate()}
            disabled={analisarEscritoriMut.isPending}
            className="press flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-semibold text-white flex-shrink-0"
            style={{
              background: 'linear-gradient(135deg,#1248BE,#3A7AB8)',
              border: 'none', cursor: analisarEscritoriMut.isPending ? 'not-allowed' : 'pointer',
              fontFamily: 'var(--font-sans)', opacity: analisarEscritoriMut.isPending ? 0.6 : 1,
            }}>
            {analisarEscritoriMut.isPending
              ? <><span className="w-3.5 h-3.5 rounded-full border-2 border-white border-t-transparent animate-spin" /> Analisando...</>
              : <><RefreshCw size={12} /> Analisar escritório</>
            }
          </button>
        </div>

        {/* Feedback batch */}
        {batchMsg && (
          <div className="flex items-center gap-2 px-4 py-3 rounded-xl text-xs font-medium"
            style={{ background: 'rgba(26,158,120,0.07)', border: '1px solid rgba(26,158,120,0.22)', color: '#1A9E78' }}>
            <Zap size={13} /> {batchMsg}
          </div>
        )}
        {batchErro && (
          <div className="flex items-center gap-2 px-4 py-3 rounded-xl text-xs font-medium"
            style={{ background: 'rgba(200,48,48,0.07)', border: '1px solid rgba(200,48,48,0.20)', color: '#C83030' }}>
            <AlertCircle size={13} /> {batchErro}
          </div>
        )}

        {/* Filtros de nível */}
        <div className="flex gap-2 flex-wrap">
          {NIVEIS.map(n => {
            const cfg   = n === 'todos' || n === 'sem_analise' ? null : NIVEL_CFG[n]
            const count = countFor(n)
            const active = nivel === n
            return (
              <button key={n} onClick={() => setNivel(n)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold press"
                style={active
                  ? { background: cfg?.bg ?? 'var(--color-am-surface)', color: cfg?.color ?? 'var(--color-am-blue)', border: `1px solid ${cfg?.border ?? 'var(--color-am-border)'}` }
                  : { background: 'var(--color-am-surface)', color: 'var(--color-am-secondary)', border: '1px solid var(--color-am-border)' }
                }>
                {cfg && <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ background: cfg.color }} />}
                {n === 'todos' ? 'Todos' : n === 'sem_analise' ? 'Sem análise' : NIVEL_CFG[n]?.label ?? n}
                <span className="ml-1 text-[10px] font-bold opacity-70">{count}</span>
              </button>
            )
          })}
        </div>

        {/* Busca */}
        <div className="relative">
          <Search size={13} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-am-muted" />
          <input type="text" value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Buscar cliente…"
            className="w-full pl-9 pr-4 py-2.5 text-xs rounded-xl bg-white border border-am-border text-am-ink outline-none transition-fast placeholder:text-am-muted card-shadow"
            onFocus={e => (e.target.style.borderColor = 'var(--color-am-blue)')}
            onBlur={e =>  (e.target.style.borderColor = 'var(--color-am-border)')}
          />
        </div>

        {/* Lista */}
        <div className="bg-white rounded-2xl card-shadow border border-am-border overflow-hidden card-border-hover">
          <div className="hidden sm:grid grid-cols-[1fr_auto_auto_auto_auto_auto] gap-4 px-5 py-2.5 bg-am-bg border-b border-am-border">
            {['Cliente', 'Processos', 'Último contato', 'Score', 'Nível', ''].map(h => (
              <span key={h} className="text-[9px] font-bold uppercase tracking-widest text-am-muted">{h}</span>
            ))}
          </div>

          {isLoading && Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="flex items-center gap-3 px-5 py-4 border-b border-am-border last:border-0">
              <div className="w-8 h-8 rounded-full skeleton flex-shrink-0" style={{ background: 'rgba(58,122,184,0.08)' }} />
              <div className="flex-1 space-y-1.5">
                <div className="h-3 w-36 rounded skeleton" style={{ background: 'rgba(58,122,184,0.08)' }} />
                <div className="h-2 w-24 rounded skeleton" style={{ background: 'rgba(58,122,184,0.06)' }} />
              </div>
            </div>
          ))}

          {isError && (
            <div className="flex items-center gap-2 m-4 p-3 rounded-xl"
              style={{ background: 'rgba(200,48,48,0.06)', border: '1px solid rgba(200,48,48,0.2)' }}>
              <Shield size={13} style={{ color: '#C83030' }} />
              <span className="text-xs text-am-secondary">Erro ao carregar clientes.</span>
            </div>
          )}

          {!isLoading && !isError && filtered.length === 0 && (
            <div className="flex flex-col items-center py-12 gap-2 text-am-muted">
              <Search size={22} strokeWidth={1.5} />
              <span className="text-xs">Nenhum cliente encontrado</span>
            </div>
          )}

          {filtered.map((c: CRMClienteCard) => {
            const cfg = c.crm_nivel ? (NIVEL_CFG[c.crm_nivel] ?? NIVEL_CFG.sem_analise) : NIVEL_CFG.sem_analise
            const accentColor = c.crm_nivel === 'alto' || c.crm_nivel === 'critico'
              ? 'rgba(200,48,48,0.55)'
              : c.crm_nivel === 'moderado' ? 'rgba(208,128,16,0.55)' : 'transparent'
            const isAnalysing = analisandoId === c.id
            const hasErro     = erroId?.id === c.id

            return (
              <div key={c.id}
                className="flex items-center gap-3 sm:grid sm:grid-cols-[1fr_auto_auto_auto_auto_auto] sm:gap-4 px-5 border-b border-am-border last:border-0"
                style={{ borderLeft: `3px solid ${accentColor}` }}>
                {/* Linha clicável para navegar */}
                <button
                  onClick={() => onSelectCliente(c.id)}
                  className="flex items-center gap-3 min-w-0 py-3.5 text-left flex-1 hover:opacity-80 transition-opacity row-press group">
                  <div className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0"
                    style={{ background: 'var(--color-am-surface)', color: 'var(--color-am-blue)' }}>
                    {initials(c.nome)}
                  </div>
                  <div className="min-w-0">
                    <div className="text-xs font-semibold text-am-ink truncate">{c.nome}</div>
                    <div className="text-[10px] text-am-muted mt-0.5 sm:hidden">
                      {c.total_processos} proc. · {formatDate(c.ultimo_contato)}
                    </div>
                    {c.crm_resumo && (
                      <div className="text-[10px] text-am-muted mt-0.5 truncate max-w-xs hidden sm:block">
                        {hasErro ? <span style={{ color: '#C83030' }}>{erroId.msg}</span> : c.crm_resumo}
                      </div>
                    )}
                  </div>
                </button>

                {/* Processos */}
                <div className="hidden sm:flex items-center gap-1 text-xs text-am-secondary font-medium whitespace-nowrap">
                  <Heart size={10} className="text-am-muted" />{c.total_processos}
                </div>

                {/* Último contato */}
                <div className="hidden sm:flex items-center gap-1 text-[11px] text-am-muted whitespace-nowrap">
                  <Clock size={10} />{formatDate(c.ultimo_contato)}
                </div>

                {/* Score */}
                <div className="hidden sm:block text-xs font-bold text-am-ink whitespace-nowrap">
                  {c.crm_score !== null ? `${c.crm_score}` : '—'}
                  {c.nps_medio !== null && (
                    <span className="ml-1 text-[10px] font-medium" style={{ color: '#1A9E78' }}>
                      <Star size={8} className="inline mb-0.5" /> {c.nps_medio}
                    </span>
                  )}
                </div>

                {/* Nível */}
                <div className="hidden sm:flex items-center gap-2 justify-end">
                  <span className="text-[9px] font-bold px-1.5 py-0.5 rounded whitespace-nowrap"
                    style={{ color: cfg.color, background: cfg.bg, border: `1px solid ${cfg.border}` }}>
                    {cfg.label}
                  </span>
                </div>

                {/* Botão analisar */}
                <div className="hidden sm:flex items-center gap-1 flex-shrink-0">
                  <button
                    onClick={e => { e.stopPropagation(); analisarClienteMut.mutate(c.id) }}
                    disabled={isAnalysing || analisarClienteMut.isPending}
                    title="Analisar cliente com IA"
                    className="flex items-center gap-1 px-2 py-1 rounded-lg text-[10px] font-semibold transition-all"
                    style={isAnalysing
                      ? { background: 'rgba(18,72,190,0.08)', color: 'var(--color-am-blue)', border: '1px solid rgba(18,72,190,0.20)', cursor: 'not-allowed' }
                      : { background: 'rgba(18,72,190,0.05)', color: 'var(--color-am-blue)', border: '1px solid rgba(18,72,190,0.15)', cursor: 'pointer' }
                    }>
                    {isAnalysing
                      ? <span className="w-3 h-3 rounded-full border border-am-blue border-t-transparent animate-spin" />
                      : <Zap size={10} />
                    }
                    {isAnalysing ? 'IA...' : 'Analisar'}
                  </button>
                  <ArrowRight size={11} className="text-am-muted" />
                </div>
              </div>
            )
          })}
        </div>

        {!isLoading && !isError && (
          <p className="text-[10px] text-am-muted text-right">
            {filtered.length} de {clientes?.length ?? 0} clientes
          </p>
        )}
      </div>
    </div>
  )
}
