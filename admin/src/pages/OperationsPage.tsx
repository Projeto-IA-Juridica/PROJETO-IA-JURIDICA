import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { healthApi, prospeccaoApi, type Lead } from '../api'
import { EmptyState, ErrorBox, Spinner } from '../components/ui'

const STATUSS: Array<Lead['status']> = ['novo', 'contatado', 'qualificado', 'descartado']

export default function OperationsPage() {
  const qc = useQueryClient()
  const [tipoAcao, setTipoAcao] = useState('reclamacao trabalhista')
  const [tribunal, setTribunal] = useState('TRT15')
  const [limite, setLimite] = useState(15)
  const [scoreMinimo, setScoreMinimo] = useState(40)
  const [tipoLead, setTipoLead] = useState('auto')

  const { data: basic, isLoading: loadingBasic } = useQuery({
    queryKey: ['health-basic'],
    queryFn: healthApi.basic,
    refetchInterval: 30_000,
  })

  const { data: ready, isLoading: loadingReady } = useQuery({
    queryKey: ['health-ready'],
    queryFn: healthApi.ready,
    refetchInterval: 30_000,
  })

  const { data: detailed, isLoading: loadingDetailed } = useQuery({
    queryKey: ['health-detailed'],
    queryFn: healthApi.detailed,
    refetchInterval: 60_000,
  })

  const { data: dna } = useQuery({
    queryKey: ['prospeccao-dna'],
    queryFn: prospeccaoApi.dna,
  })

  const { data: pipeline, isLoading: loadingPipeline, error: pipelineError } = useQuery({
    queryKey: ['prospeccao-pipeline'],
    queryFn: () => prospeccaoApi.pipeline({ por_pagina: 30 }),
  })

  const { mutate: atualizarDna, isPending: atualizandoDna } = useMutation({
    mutationFn: prospeccaoApi.atualizarDna,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['prospeccao-dna'] })
    },
  })

  const { mutate: descobrir, isPending: descobrindo } = useMutation({
    mutationFn: () => prospeccaoApi.descobrir({ tipo_acao: tipoAcao, tribunal, limite, score_minimo: scoreMinimo, tipo_lead: tipoLead }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['prospeccao-pipeline'] })
      qc.invalidateQueries({ queryKey: ['prospeccao-dna'] })
    },
  })

  const { mutate: atualizarStatus, isPending: atualizandoStatus } = useMutation({
    mutationFn: ({ leadId, status }: { leadId: number; status: string }) => prospeccaoApi.atualizarStatus(leadId, { status }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['prospeccao-pipeline'] })
    },
  })

  const { mutate: excluirLead, isPending: excluindo } = useMutation({
    mutationFn: prospeccaoApi.deletar,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['prospeccao-pipeline'] })
    },
  })

  const loadingHealth = loadingBasic || loadingReady || loadingDetailed

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">Operacoes da API</h1>
        <p className="page-subtitle">Saude da infraestrutura e prospeccao inteligente com dados reais</p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
        <div className="surface" style={{ padding: 16 }}>
          <div style={{ fontSize: 12, textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 10 }}>Health</div>
          {loadingHealth ? (
            <Spinner />
          ) : (
            <div style={{ display: 'grid', gap: 8 }}>
              <div style={{ fontSize: 13 }}>
                API: <strong style={{ color: 'var(--text-primary)' }}>{basic?.status ?? '—'}</strong>
              </div>
              <div style={{ fontSize: 13 }}>
                Ready: <strong style={{ color: 'var(--text-primary)' }}>{ready?.status ?? '—'}</strong>
              </div>
              <div style={{ fontSize: 13 }}>
                Detailed: <strong style={{ color: 'var(--text-primary)' }}>{detailed?.status ?? '—'}</strong>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginTop: 8 }}>
                {Object.entries(detailed?.checks ?? {}).map(([name, info]) => (
                  <div key={name} style={{ border: '1px solid var(--surface-border)', borderRadius: 8, padding: 10 }}>
                    <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{name}</div>
                    <div style={{ fontSize: 13, color: 'var(--text-primary)' }}>{info.status}</div>
                    {info.latency_ms != null && <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{info.latency_ms} ms</div>}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="surface" style={{ padding: 16 }}>
          <div style={{ fontSize: 12, textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 10 }}>DNA e descoberta</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div style={{ fontSize: 13 }}>
              DNA disponivel: <strong style={{ color: 'var(--text-primary)' }}>{dna?.dados_insuficientes ? 'nao' : 'sim'}</strong>
            </div>
            {dna?.especialidades?.length ? (
              <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Especialidades: {dna.especialidades.join(', ')}</div>
            ) : null}
            <button className="btn btn-secondary" onClick={() => atualizarDna()} disabled={atualizandoDna}>
              {atualizandoDna ? <Spinner size={12} /> : null} Atualizar DNA
            </button>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
              <input className="input" value={tipoAcao} onChange={(e) => setTipoAcao(e.target.value)} placeholder="Tipo de acao" />
              <input className="input" value={tribunal} onChange={(e) => setTribunal(e.target.value)} placeholder="Tribunal" />
              <input className="input" type="number" min={1} max={100} value={limite} onChange={(e) => setLimite(Number(e.target.value) || 1)} placeholder="Limite" />
              <input className="input" type="number" min={0} max={100} value={scoreMinimo} onChange={(e) => setScoreMinimo(Number(e.target.value) || 0)} placeholder="Score minimo" />
            </div>
            <select className="input" value={tipoLead} onChange={(e) => setTipoLead(e.target.value)}>
              <option value="auto">auto</option>
              <option value="empresa">empresa</option>
              <option value="pessoa">pessoa</option>
            </select>
            <button className="btn btn-primary" onClick={() => descobrir()} disabled={descobrindo || !tipoAcao.trim()}>
              {descobrindo ? <Spinner size={12} /> : null} Descobrir leads
            </button>
          </div>
        </div>
      </div>

      <div className="surface" style={{ padding: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
          <div style={{ fontSize: 12, textTransform: 'uppercase', color: 'var(--text-muted)' }}>Pipeline de prospeccao</div>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{pipeline?.total ?? 0} leads</div>
        </div>

        {pipelineError ? <ErrorBox message="Falha ao carregar pipeline de prospeccao." /> : null}

        {loadingPipeline ? (
          <Spinner />
        ) : !pipeline?.leads?.length ? (
          <EmptyState title="Sem leads no pipeline" desc="Execute a descoberta para preencher o funil com dados reais." />
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {pipeline.leads.map((lead) => (
              <div key={lead.id} style={{ border: '1px solid var(--surface-border)', borderRadius: 8, padding: 12 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center' }}>
                  <div>
                    <div style={{ fontSize: 14, color: 'var(--text-primary)', fontWeight: 600 }}>{lead.nome}</div>
                    <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{lead.tipo_lead} · score {lead.score_match ?? 0}</div>
                  </div>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <select
                      className="input"
                      value={lead.status}
                      onChange={(e) => atualizarStatus({ leadId: lead.id, status: e.target.value })}
                      disabled={atualizandoStatus}
                      style={{ width: 160 }}
                    >
                      {STATUSS.map((status) => (
                        <option key={status} value={status}>{status}</option>
                      ))}
                    </select>
                    <button className="btn btn-danger btn-sm" onClick={() => excluirLead(lead.id)} disabled={excluindo}>Excluir</button>
                  </div>
                </div>
                {lead.abordagem_sugerida ? (
                  <p style={{ marginTop: 8, fontSize: 12, color: 'var(--text-secondary)' }}>{lead.abordagem_sugerida}</p>
                ) : null}
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  )
}
