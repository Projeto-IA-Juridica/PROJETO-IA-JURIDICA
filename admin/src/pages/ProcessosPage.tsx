import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { clientesApi, processosApi, type Processo } from '../api'
import { BadgeRisco, EmptyState, ErrorBox, Pagination, Spinner, SkeletonGrid } from '../components/ui'
import { FolderOpen, Plus, RefreshCw } from 'lucide-react'

function ProcessoForm({
  onSubmit, loading, clientes,
}: {
  onSubmit: (payload: { numero_cnj: string; cliente_id: number; polo_cliente: 'autor' | 'reu' | 'terceiro'; tipo_acao?: string }) => void
  loading: boolean
  clientes: Array<{ id: number; nome: string }>
}) {
  const [numeroCnj, setNumeroCnj] = useState('')
  const [clienteId, setClienteId] = useState<number | ''>('')
  const [polo, setPolo] = useState<'autor' | 'reu' | 'terceiro'>('autor')
  const [tipoAcao, setTipoAcao] = useState('')

  return (
    <div className="surface" style={{ padding: 14, marginBottom: 14 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: 8 }}>
        <Plus size={13} /> Novo processo
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1.2fr 1fr 1.4fr auto', gap: 6 }}>
        <input className="input" placeholder="CNJ" value={numeroCnj} onChange={(e) => setNumeroCnj(e.target.value)} />
        <select className="input" value={clienteId} onChange={(e) => setClienteId(Number(e.target.value))}>
          <option value="">Selecione cliente</option>
          {clientes.map(c => <option key={c.id} value={c.id}>{c.nome}</option>)}
        </select>
        <select className="input" value={polo} onChange={(e) => setPolo(e.target.value as 'autor' | 'reu' | 'terceiro')}>
          <option value="autor">autor</option>
          <option value="reu">réu</option>
          <option value="terceiro">terceiro</option>
        </select>
        <input className="input" placeholder="Tipo de ação" value={tipoAcao} onChange={(e) => setTipoAcao(e.target.value)} />
        <button
          className="btn btn-primary"
          disabled={loading || !numeroCnj.trim() || !clienteId}
          onClick={() => {
            if (!clienteId) return
            onSubmit({ numero_cnj: numeroCnj.trim(), cliente_id: clienteId, polo_cliente: polo, tipo_acao: tipoAcao.trim() || undefined })
            setNumeroCnj(''); setClienteId(''); setPolo('autor'); setTipoAcao('')
          }}
        >
          {loading ? <Spinner size={12} /> : null} Criar
        </button>
      </div>
    </div>
  )
}

function ProcessoRow({
  processo, onSave, onArchive, saving, archiving,
}: {
  processo: Processo
  onSave: (id: number, payload: { polo_cliente: 'autor' | 'reu' | 'terceiro'; tipo_acao?: string | null; monitoramento_ativo: boolean; frequencia_monitoramento: 'diario' | 'semanal' }) => void
  onArchive: (id: number) => void
  saving: boolean
  archiving: boolean
}) {
  const [editing, setEditing] = useState(false)
  const [polo, setPolo] = useState<'autor' | 'reu' | 'terceiro'>((processo.polo_cliente as 'autor' | 'reu' | 'terceiro') ?? 'autor')
  const [tipoAcao, setTipoAcao] = useState(processo.tipo_acao ?? '')
  const [monitoramentoAtivo, setMonitoramentoAtivo] = useState(!!processo.monitoramento_ativo)
  const [frequencia, setFrequencia] = useState<'diario' | 'semanal'>((processo.frequencia_monitoramento as 'diario' | 'semanal') ?? 'diario')

  return (
    <div className="surface" style={{ padding: 10 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10 }}>
        <div>
          <div style={{ fontSize: 13, color: 'var(--text-primary)', fontWeight: 500 }}>{processo.numero_cnj}</div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
            cliente #{processo.cliente_id} · {processo.tribunal ?? 'tribunal pendente'} · {processo.status}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <BadgeRisco nivel={processo.score_nivel} />
          <button className="btn btn-secondary btn-sm" onClick={() => setEditing(v => !v)}>{editing ? 'Fechar' : 'Editar'}</button>
          <button className="btn btn-danger btn-sm" onClick={() => onArchive(processo.id)} disabled={archiving}>{archiving ? <Spinner size={12} /> : 'Arquivar'}</button>
        </div>
      </div>

      {editing && (
        <div style={{ marginTop: 10, display: 'grid', gridTemplateColumns: '1fr 1.2fr 1fr 1fr auto', gap: 6 }}>
          <select className="input" value={polo} onChange={(e) => setPolo(e.target.value as 'autor' | 'reu' | 'terceiro')}>
            <option value="autor">autor</option><option value="reu">réu</option><option value="terceiro">terceiro</option>
          </select>
          <input className="input" value={tipoAcao} onChange={(e) => setTipoAcao(e.target.value)} placeholder="Tipo de ação" />
          <select className="input" value={monitoramentoAtivo ? 'ativo' : 'inativo'} onChange={(e) => setMonitoramentoAtivo(e.target.value === 'ativo')}>
            <option value="ativo">ativo</option><option value="inativo">inativo</option>
          </select>
          <select className="input" value={frequencia} onChange={(e) => setFrequencia(e.target.value as 'diario' | 'semanal')}>
            <option value="diario">diário</option><option value="semanal">semanal</option>
          </select>
          <button className="btn btn-primary btn-sm" disabled={saving} onClick={() => onSave(processo.id, { polo_cliente: polo, tipo_acao: tipoAcao || null, monitoramento_ativo: monitoramentoAtivo, frequencia_monitoramento: frequencia })}>
            {saving ? <Spinner size={12} /> : 'Salvar'}
          </button>
        </div>
      )}

      {processo.ultimo_andamento && (
        <div style={{ marginTop: 8, fontSize: 11, color: 'var(--text-secondary)', borderTop: '1px solid var(--surface-border)', paddingTop: 8 }}>
          Último andamento: {processo.ultimo_andamento}
        </div>
      )}
    </div>
  )
}

export default function ProcessosPage() {
  const qc = useQueryClient()
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState('')
  const [search, setSearch] = useState('')

  const { data: clientesData } = useQuery({
    queryKey: ['clientes-processos-form'],
    queryFn: () => clientesApi.listar({ page: 1, page_size: 100 }),
    staleTime: 5 * 60_000, // 5 min cache — essa lista muda pouco
    placeholderData: (prev) => prev,
  })

  const { data, isLoading, error } = useQuery({
    queryKey: ['processos', page, status, search],
    queryFn: () => processosApi.listar({ page, per_page: 20, status: status || undefined, search: search.trim() || undefined }),
    staleTime: 60 * 1000, // 60s cache
    placeholderData: (prev) => prev,
  })

  const { mutate: criarProcesso, isPending: creating } = useMutation({
    mutationFn: processosApi.criar,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['processos'] }),
  })

  const { mutate: atualizarProcesso, isPending: saving } = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: { polo_cliente: 'autor' | 'reu' | 'terceiro'; tipo_acao?: string | null; monitoramento_ativo: boolean; frequencia_monitoramento: 'diario' | 'semanal' } }) =>
      processosApi.atualizar(id, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['processos'] }),
  })

  const { mutate: arquivarProcesso, isPending: archiving } = useMutation({
    mutationFn: processosApi.arquivar,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['processos'] }),
  })

  const items = data?.items ?? []
  const totalPages = useMemo(() => {
    if (!data) return 1
    return Math.max(1, Math.ceil(data.total / data.per_page))
  }, [data])

  if (error) return <ErrorBox message="Falha ao carregar processos." />

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">Processos</h1>
        <p className="page-subtitle">Gestão de processos monitorados</p>
      </div>

      <ProcessoForm
        onSubmit={criarProcesso}
        loading={creating}
        clientes={(clientesData?.items ?? []).map(c => ({ id: c.id, nome: c.nome }))}
      />

      <div className="surface" style={{ padding: 10, marginBottom: 10 }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 160px auto', gap: 6 }}>
          <input className="input" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Buscar por CNJ" />
          <select className="input" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">todos</option>
            <option value="ativo">ativo</option>
            <option value="arquivado">arquivado</option>
            <option value="suspenso">suspenso</option>
            <option value="encerrado">encerrado</option>
          </select>
          <button className="btn btn-secondary" onClick={() => setPage(1)}><RefreshCw size={12} /></button>
        </div>
      </div>

      {isLoading && !data ? (
        <div style={{ paddingTop: 20 }}><SkeletonGrid count={5} /></div>
      ) : items.length === 0 ? (
        <EmptyState icon={<FolderOpen size={24} style={{ color: 'var(--text-muted)' }} />} title="Nenhum processo encontrado" desc="Cadastre um processo para iniciar o monitoramento." />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {items.map(p => (
            <ProcessoRow
              key={p.id} processo={p}
              onSave={(id, payload) => atualizarProcesso({ id, payload })}
              onArchive={(id) => arquivarProcesso(id)}
              saving={saving} archiving={archiving}
            />
          ))}
          <Pagination currentPage={page} totalPages={totalPages} onPageChange={setPage} totalItems={data?.total} />
        </div>
      )}
    </>
  )
}
