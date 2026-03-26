import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { crmApi, type CRMCard } from '../api/crm'
import { BadgeCRM, MetricCard, ProgressBar, Spinner, EmptyState, ErrorBox } from '../components/ui'

type NivelFilter = 'todos' | 'critico' | 'em_risco' | 'neutro' | 'satisfeito' | 'excelente'

function CRMClienteRow({ card, onAnalyze }: { card: CRMCard; onAnalyze: (id: number) => void }) {
  const [expanded, setExpanded] = useState(false)
  const diasContato = card.ultimo_contato
    ? Math.floor((Date.now() - new Date(card.ultimo_contato).getTime()) / 86400000)
    : null

  return (
    <div className="surface" style={{ padding: 0, overflow: 'hidden' }}>
      <div
        style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '12px 16px', cursor: 'pointer' }}
        onClick={() => setExpanded(e => !e)}
      >
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontWeight: 600, fontSize: 13, color: 'var(--text-primary)', marginBottom: 2 }}>{card.nome}</div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{card.telefone_whatsapp}</div>
        </div>

        <BadgeCRM nivel={card.crm_nivel as never} />

        <div style={{ textAlign: 'center', minWidth: 70 }}>
          <div style={{ fontWeight: 700, fontSize: 16 }}>{card.crm_score ?? '—'}</div>
          <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>score</div>
        </div>

        <div style={{ textAlign: 'center', minWidth: 60 }}>
          <div style={{ fontSize: 13 }}>{card.nps_medio?.toFixed(1) ?? '—'}</div>
          <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>NPS</div>
        </div>

        <div style={{ textAlign: 'center', minWidth: 70 }}>
          <div style={{ fontSize: 13 }}>{diasContato != null ? `${diasContato}d` : '—'}</div>
          <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>últ. contato</div>
        </div>

        <button
          className="btn btn-secondary btn-sm"
          onClick={e => { e.stopPropagation(); onAnalyze(card.id) }}
          title="Reanalisar com Claude"
        >🔄</button>

        <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>{expanded ? '▲' : '▼'}</span>
      </div>

      {expanded && (
        <div style={{ borderTop: '1px solid var(--surface-border)', padding: '12px 16px', background: 'var(--surface-base)' }}>
          {card.crm_resumo && <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 10, lineHeight: 1.5 }}>{card.crm_resumo}</p>}
          {card.crm_acao_sugerida && (
            <div style={{ background: 'var(--surface-overlay)', borderRadius: 6, padding: '8px 12px', fontSize: 12, color: 'var(--text-secondary)' }}>
              <strong style={{ color: 'var(--text-primary)' }}>Ação sugerida:</strong> {card.crm_acao_sugerida}
            </div>
          )}
          {card.crm_score != null && (
            <div style={{ marginTop: 10 }}>
              <ProgressBar value={card.crm_score} max={100} height={4} />
            </div>
          )}
          <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 8 }}>
            {card.total_processos} processo(s) · analisado em {card.crm_analisado_em ? new Date(card.crm_analisado_em).toLocaleString('pt-BR') : 'não analisado'}
          </div>
        </div>
      )}
    </div>
  )
}

export default function CRMPage() {
  const qc = useQueryClient()
  const [filtro, setFiltro] = useState<NivelFilter>('todos')
  const [busca, setBusca] = useState('')

  const { data: resumo, isLoading: lr } = useQuery({ queryKey: ['crm-resumo'], queryFn: () => crmApi.resumo() })
  const { data: clientes, isLoading: lc, error } = useQuery({
    queryKey: ['crm-clientes', filtro],
    queryFn: () => crmApi.listar({ nivel: filtro === 'todos' ? undefined : filtro, page_size: 100 }),
  })

  const { mutate: analisarTudo, isPending: analisando } = useMutation({
    mutationFn: crmApi.analisarEscritorio,
    onSuccess: () => { setTimeout(() => qc.invalidateQueries({ queryKey: ['crm'] }), 2000) },
  })

  const { mutate: analisarCliente } = useMutation({
    mutationFn: (id: number) => crmApi.analisar(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['crm'] }),
  })

  const NIVEIS = ['todos', 'critico', 'em_risco', 'neutro', 'satisfeito', 'excelente'] as const

  const filtrados = (clientes ?? []).filter(c =>
    !busca || c.nome.toLowerCase().includes(busca.toLowerCase())
  ).sort((a, b) => (a.crm_score ?? 999) - (b.crm_score ?? 999))

  if (error) return <ErrorBox message="Falha ao carregar CRM." />

  return (
    <>
      <div className="page-header">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <h1 className="page-title">CRM Inteligente</h1>
            <p className="page-subtitle">Classificação de satisfação e ações sugeridas por IA</p>
          </div>
          <button className="btn btn-primary" onClick={() => analisarTudo()} disabled={analisando}>
            {analisando ? <><Spinner size={12} /> Analisando...</> : '🔄 Analisar escritório'}
          </button>
        </div>
      </div>

      {/* KPI Header */}
      {lr ? <Spinner /> : resumo && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 12, marginBottom: 24 }}>
          {(['critico', 'em_risco', 'neutro', 'satisfeito', 'excelente'] as const).map(n => {
            const icons = { critico: '🔴', em_risco: '🟠', neutro: '🟡', satisfeito: '🟢', excelente: '🟢' }
            const labels = { critico: 'Crítico', em_risco: 'Em Risco', neutro: 'Neutro', satisfeito: 'Satisfeito', excelente: 'Excelente' }
            return (
              <MetricCard key={n} value={resumo[n]} label={`${icons[n]} ${labels[n]}`} />
            )
          })}
          <MetricCard value={resumo.sem_analise} label="⚪ Sem análise" />
        </div>
      )}

      {/* Filtros */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
        <div style={{ flex: 1, minWidth: 200 }}>
          <input className="input" value={busca} onChange={e => setBusca(e.target.value)} placeholder="Buscar por nome..." />
        </div>
        <div style={{ display: 'flex', gap: 4 }}>
          {NIVEIS.map(n => (
            <button key={n} className={`btn btn-sm ${filtro === n ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setFiltro(n)}>
              {n === 'todos' ? 'Todos' : n.replace('_', ' ')}
            </button>
          ))}
        </div>
      </div>

      {/* Lista */}
      {lc ? <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 40 }}><Spinner /></div> : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {filtrados.length === 0 ? (
            <EmptyState icon="🤝" title="Nenhum cliente encontrado" desc="Ajuste os filtros ou analise o escritório." />
          ) : filtrados.map(c => (
            <CRMClienteRow key={c.id} card={c} onAnalyze={id => analisarCliente(id)} />
          ))}
        </div>
      )}
    </>
  )
}
