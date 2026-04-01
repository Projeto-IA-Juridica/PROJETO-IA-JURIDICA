import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { clientesApi, type Cliente } from '../api'
import { BadgeCRM, Spinner, EmptyState, ErrorBox, Pagination } from '../components/ui'
import { Users, Search } from 'lucide-react'

function ClienteCard({ cliente, onClick }: { cliente: Cliente; onClick: () => void }) {
  const iniciais = cliente.nome.split(' ').slice(0, 2).map(n => n[0]).join('')
  return (
    <div
      onClick={onClick}
      className="surface"
      style={{
        padding: '14px 16px',
        cursor: 'pointer',
        display: 'flex',
        gap: 12,
        alignItems: 'center',
      }}
    >
      <div style={{
        width: 36, height: 36, borderRadius: '50%', flexShrink: 0,
        background: 'var(--surface-overlay)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)',
      }}>
        {iniciais}
      </div>

      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: 500, fontSize: 13, color: 'var(--text-primary)', marginBottom: 2, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {cliente.nome}
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'monospace' }}>
          {cliente.telefone_whatsapp}
        </div>
      </div>

      <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexShrink: 0 }}>
        <BadgeCRM nivel={cliente.crm_nivel} />
        {cliente.crm_score != null && (
          <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{cliente.crm_score}</span>
        )}
      </div>
    </div>
  )
}

export default function HubPage() {
  const navigate = useNavigate()
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const pageSize = 20

  const { data, isLoading, error } = useQuery({
    queryKey: ['clientes', page],
    queryFn: () => clientesApi.listar({ page, page_size: pageSize }),
  })

  const clientes = data?.items || []
  const filtered = search.trim()
    ? clientes.filter(c => c.nome.toLowerCase().includes(search.toLowerCase()))
    : clientes
  const totalPages = data ? Math.ceil(data.total / data.per_page) : 1

  if (error) return <ErrorBox message="Falha ao carregar clientes." />

  return (
    <>
      <div className="page-header">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <h1 className="page-title">Hub do Advogado</h1>
            <p className="page-subtitle">{data?.total ?? 0} clientes</p>
          </div>
        </div>
      </div>

      {/* Search */}
      <div style={{ position: 'relative', maxWidth: 320, marginBottom: 16 }}>
        <Search size={14} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
        <input
          className="input"
          style={{ paddingLeft: 30 }}
          placeholder="Buscar cliente..."
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
      </div>

      {isLoading ? (
        <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 60 }}><Spinner size={20} /></div>
      ) : !filtered.length ? (
        <EmptyState
          icon={<Users size={32} style={{ color: 'var(--text-muted)' }} />}
          title="Nenhum cliente encontrado"
          desc="Complete o onboarding e importe clientes via CSV."
          action={<button className="btn btn-primary" onClick={() => navigate('/settings')}>Ir para Configurações</button>}
        />
      ) : (
        <>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {filtered.map(c => (
              <ClienteCard key={c.id} cliente={c} onClick={() => navigate(`/hub/clientes/${c.id}`)} />
            ))}
          </div>
          {totalPages > 1 && (
            <Pagination currentPage={page} totalPages={totalPages} onPageChange={setPage} totalItems={data?.total} />
          )}
        </>
      )}
    </>
  )
}
