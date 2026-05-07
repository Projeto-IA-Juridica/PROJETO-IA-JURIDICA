import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Search, Shield } from 'lucide-react'
import { fetchClientes } from '../api/crm'
import type { CRMClienteCard } from '../types'
import RiskChip from './RiskChip'
import { ClienteSkeleton } from './Skeleton'

const RISK_COLOR: Record<string, string> = {
  baixo:    '#1A9E78',
  moderado: '#D08010',
  alto:     '#C83030',
  critico:  '#C83030',
}

interface Props {
  activeId: number | null
  onSelect: (id: number) => void
}

function initials(nome: string) {
  return nome.split(' ').slice(0, 2).map((n) => n[0].toUpperCase()).join('')
}

export default function Sidebar({ activeId, onSelect }: Props) {
  const [search, setSearch] = useState('')

  const { data: clientes, isLoading, isError } = useQuery({
    queryKey: ['clientes'],
    queryFn: fetchClientes,
    staleTime: 60_000,
  })

  const filtered = clientes?.filter((c) =>
    c.nome.toLowerCase().includes(search.toLowerCase())
  ) ?? []

  const total = clientes?.length ?? 0
  const comProc = clientes?.filter((c) => c.total_processos > 0).length ?? 0
  const riscoAlto = clientes?.filter((c) => c.crm_nivel === 'critico' || c.crm_nivel === 'em_risco').length ?? 0

  return (
    <aside className="flex flex-col h-full bg-am-bg border-r border-am-border">

      {/* Brand */}
      <div className="flex items-center gap-3 px-5 py-5 border-b border-am-border flex-shrink-0">
        <div className="w-8 h-8 rounded-lg bg-am-blue flex items-center justify-center text-white font-bold text-sm select-none">
          a
        </div>
        <div>
          <div className="text-sm font-semibold text-am-ink tracking-tight">amicus</div>
          <div className="text-[10px] text-am-muted">Hub do Advogado</div>
        </div>
      </div>

      {/* IA card */}
      <div className="mx-4 mt-4 flex items-center gap-2.5 px-3.5 py-3 rounded-xl bg-am-surface border border-am-border flex-shrink-0">
        <span className="w-2 h-2 rounded-full bg-am-green animate-pulse flex-shrink-0" />
        <div>
          <div className="text-xs font-semibold text-am-ink">Dra. Camila</div>
          <div className="text-[10px] text-am-muted">IA Ativa · Tom formal · 08h–18h</div>
        </div>
      </div>

      {/* Stats strip */}
      <div className="grid grid-cols-3 gap-px mx-4 mt-3 rounded-xl overflow-hidden border border-am-border flex-shrink-0">
        {[
          { val: total, lbl: 'Clientes' },
          { val: comProc, lbl: 'C/ processo' },
          { val: riscoAlto, lbl: 'Em risco', red: riscoAlto > 0 },
        ].map(({ val, lbl, red }) => (
          <div key={lbl} className="flex flex-col items-center py-2.5 bg-am-surface">
            <div className={`text-base font-bold leading-none ${red ? 'text-am-red' : 'text-am-ink'}`}>{val}</div>
            <div className="text-[9px] text-am-muted mt-0.5">{lbl}</div>
          </div>
        ))}
      </div>

      {/* Search */}
      <div className="mx-4 mt-3 flex-shrink-0">
        <div className="relative">
          <Search size={12} className="absolute left-3 top-1/2 -translate-y-1/2 text-am-muted" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar cliente…"
            className="w-full pl-8 pr-3 py-2 text-xs rounded-lg border border-am-border bg-white
              text-am-ink outline-none focus:border-am-blue transition-colors placeholder:text-am-muted"
          />
        </div>
      </div>

      {/* Client list */}
      <div className="flex-1 overflow-y-auto mt-2 pb-4">
        {isLoading && Array.from({ length: 5 }).map((_, i) => <ClienteSkeleton key={i} />)}

        {isError && (
          <div className="flex items-center gap-2 mx-4 mt-3 p-3 rounded-lg bg-red-50 border border-red-100">
            <Shield size={12} className="text-am-red flex-shrink-0" />
            <span className="text-xs text-am-red">
              Erro ao carregar. Verifique o token e o backend.
            </span>
          </div>
        )}

        {!isLoading && !isError && filtered.length === 0 && (
          <p className="text-xs text-am-muted text-center mt-6">Nenhum cliente encontrado</p>
        )}

        {filtered.map((c) => (
          <ClienteItem
            key={c.id}
            cliente={c}
            active={c.id === activeId}
            onClick={() => onSelect(c.id)}
          />
        ))}
      </div>
    </aside>
  )
}

function ClienteItem({ cliente: c, active, onClick }: {
  cliente: CRMClienteCard
  active: boolean
  onClick: () => void
}) {
  const borderColor = c.crm_nivel ? (RISK_COLOR[c.crm_nivel] ?? '#A8C8E8') : '#A8C8E8'
  const init = initials(c.nome)

  return (
    <button
      onClick={onClick}
      className={`w-full flex items-center gap-3 px-4 py-3 border-l-2 text-left transition-sidebar-item
        hover:bg-am-surface
        ${active ? 'bg-am-surface' : 'bg-transparent'}`}
      style={{ borderLeftColor: active ? borderColor : 'transparent' }}
    >
      {/* Avatar */}
      <div
        className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-semibold text-white flex-shrink-0"
        style={{ background: borderColor }}
      >
        {init}
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0">
        <div className="text-xs font-medium text-am-ink truncate">{c.nome}</div>
        <div className="text-[10px] text-am-muted truncate mt-0.5">
          {c.total_processos > 0
            ? `${c.total_processos} processo${c.total_processos > 1 ? 's' : ''}`
            : 'Sem processo'}
        </div>
      </div>

      {/* Risk chip */}
      <RiskChip nivel={c.crm_nivel} />
    </button>
  )
}
