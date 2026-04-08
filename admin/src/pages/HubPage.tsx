import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { clientesApi, type Cliente } from '../api'
import { BadgeCRM, EmptyState, ErrorBox, Pagination, SkeletonGrid } from '../components/ui'

function ClienteCard({ cliente, onClick }: { cliente: Cliente; onClick: () => void }) {
  const iniciais = cliente.nome.split(' ').slice(0, 2).map(n => n[0]).join('')
  return (
    <div
      onClick={onClick}
      style={{
        background: 'var(--surface-raised)',
        border: '1px solid var(--surface-border)',
        borderRadius: 8,
        padding: '16px',
        cursor: 'pointer',
        transition: 'border-color 0.15s, background 0.15s',
        display: 'flex',
        gap: 14,
        alignItems: 'flex-start',
      }}
      onMouseEnter={e => { (e.currentTarget as HTMLElement).style.borderColor = 'var(--accent)' }}
      onMouseLeave={e => { (e.currentTarget as HTMLElement).style.borderColor = 'var(--surface-border)' }}
    >
      {/* Avatar */}
      <div style={{
        width: 40, height: 40, borderRadius: '50%', flexShrink: 0,
        background: 'var(--surface-overlay)',
        border: '1px solid var(--surface-border)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 14, fontWeight: 600, color: 'var(--text-secondary)',
      }}>
        {iniciais}
      </div>

      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: 600, fontSize: 13, color: 'var(--text-primary)', marginBottom: 3, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {cliente.nome}
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 8, fontFamily: 'monospace' }}>
          {cliente.telefone_whatsapp}
        </div>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
          <BadgeCRM nivel={cliente.crm_nivel} />
          {cliente.crm_score != null && (
            <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>score {cliente.crm_score}/100</span>
          )}
        </div>
      </div>
    </div>
  )
}

export default function HubPage() {
  const navigate = useNavigate()
  const [page, setPage] = useState(1)
  const pageSize = 20

  const { data, isLoading, error } = useQuery({
    queryKey: ['clientes', page],
    queryFn: () => clientesApi.listar({ page, page_size: pageSize }),
    staleTime: 60 * 1000, // 60s cache
    placeholderData: (prev) => prev, // Mantém dados antigos enquanto carrega novos
  })

  const clientes = data?.items || []
  const totalPages = data ? Math.ceil(data.total / data.per_page) : 1

  if (isLoading && !data) return (
    <div style={{ paddingTop: 20 }}>
      <SkeletonGrid count={9} />
    </div>
  )

  if (error) return <ErrorBox message="Falha ao carregar clientes. Verifique sua conexão com a API." />

  return (
    <>
      <div className="page-header">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <h1 className="page-title">Hub do Advogado</h1>
            <p className="page-subtitle">{data?.total ?? 0} clientes no total</p>
          </div>
        </div>
      </div>

      {!clientes.length ? (
        <EmptyState
          icon="👥"
          title="Nenhum cliente encontrado"
          desc="Complete o onboarding e importe clientes via CSV para começar."
          action={<button className="btn btn-primary" onClick={() => navigate('/settings')}>Ir para Configurações</button>}
        />
      ) : (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 12 }}>
            {clientes.map(c => (
              <ClienteCard
                key={c.id}
                cliente={c}
                onClick={() => navigate(`/hub/clientes/${c.id}`)}
              />
            ))}
          </div>

          {totalPages > 1 && (
            <Pagination
              currentPage={page}
              totalPages={totalPages}
              onPageChange={setPage}
              totalItems={data?.total}
            />
          )}
        </>
      )}
    </>
  )
}
