import { useState, useRef, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { clientesApi, processosApi } from '../api'
import { chatApi, type Mensagem } from '../api/chat'
import { BadgeCRM, BadgeRisco, ProgressBar, Spinner, ErrorBox, EmptyState } from '../components/ui'

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '5px 0', borderBottom: '1px solid var(--surface-border-muted)', fontSize: 12 }}>
      <span style={{ color: 'var(--text-muted)', flexShrink: 0, marginRight: 8 }}>{label}</span>
      <span style={{ color: 'var(--text-secondary)', textAlign: 'right' }}>{value ?? <span style={{ color: 'var(--text-muted)' }}>—</span>}</span>
    </div>
  )
}

function ChatWindow({ clienteId }: { clienteId: number }) {
  const qc = useQueryClient()
  const bottomRef = useRef<HTMLDivElement>(null)
  const { data: msgs, isLoading, error } = useQuery({
    queryKey: ['chat', clienteId],
    queryFn: () => chatApi.historico(clienteId),
    staleTime: 0,
    retry: 0,
  })
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [localMsgs, setLocalMsgs] = useState<Array<{ role: 'user' | 'ai'; content: string }>>([])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [msgs, localMsgs])

  const send = async () => {
    if (!input.trim() || sending) return
    const msg = input.trim()
    setInput('')
    setSending(true)
    setLocalMsgs(p => [...p, { role: 'user', content: msg }])
    try {
      const res = await chatApi.enviar(clienteId, msg)
      setLocalMsgs(p => [...p, { role: 'ai', content: res.message }])
      qc.invalidateQueries({ queryKey: ['chat', clienteId] })
    } catch {
      setLocalMsgs(p => [...p, { role: 'ai', content: '⚠️ Erro ao processar. Tente novamente.' }])
    } finally { setSending(false) }
  }

  // Merge: histórico da API + mensagens locais da sessão (evitar duplicatas)
  const apiMsgs: Mensagem[] = (msgs ?? []).slice().reverse()

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      {/* Histórico */}
      <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 8, padding: '4px 0 12px' }}>
        {isLoading && <div style={{ textAlign: 'center', paddingTop: 20 }}><Spinner /></div>}
        {error && (
          <ErrorBox message="Não foi possível carregar o histórico deste cliente agora." />
        )}

        {/* Mensagens da API (históricas) */}
        {apiMsgs.map(m => (
          <div key={m.id} style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            {m.mensagem_cliente && (
              <div className="chat-bubble-user">{m.mensagem_cliente}</div>
            )}
            {m.mensagem_ia && (
              <div className="chat-bubble-ai" style={{ whiteSpace: 'pre-wrap' }}>{m.mensagem_ia}</div>
            )}
          </div>
        ))}

        {/* Mensagens locais desta sessão */}
        {localMsgs.map((m, i) => (
          <div key={`local-${i}`}>
            {m.role === 'user' ? (
              <div className="chat-bubble-user">{m.content}</div>
            ) : (
              <div className="chat-bubble-ai" style={{ whiteSpace: 'pre-wrap' }}>{m.content}</div>
            )}
          </div>
        ))}
        {sending && <div style={{ alignSelf: 'flex-start' }}><div className="chat-bubble-ai"><Spinner size={12} /> processando...</div></div>}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div style={{ display: 'flex', gap: 8, paddingTop: 10, borderTop: '1px solid var(--surface-border)' }}>
        <input
          className="input"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && !e.shiftKey && send()}
          placeholder="Pergunte sobre o processo, termos jurídicos..."
          disabled={sending}
        />
        <button className="btn btn-primary" onClick={send} disabled={sending || !input.trim()}>
          {sending ? <Spinner size={12} /> : '↑'}
        </button>
      </div>
    </div>
  )
}

export default function ClientDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const clienteId = Number(id)
  const [selectedProcessoId, setSelectedProcessoId] = useState<number | null>(null)

  const exportarDados = useMutation({
    mutationFn: () => clientesApi.exportar(clienteId),
    onSuccess: (data) => {
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json;charset=utf-8' })
      const url = window.URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `lgpd_cliente_${clienteId}.json`
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      window.URL.revokeObjectURL(url)
    },
  })

  const { data: cliente, isLoading: lcli, error: ecli } = useQuery({
    queryKey: ['cliente', clienteId],
    queryFn: () => clientesApi.detalhe(clienteId),
  })
  const { data: processos, isLoading: lproc } = useQuery({
    queryKey: ['processos', clienteId],
    queryFn: () => processosApi.porCliente(clienteId),
  })

  // Auto-select first process when data loads
  useEffect(() => {
    if (processos && processos.length > 0 && !selectedProcessoId) {
      setSelectedProcessoId(processos[0].id)
    }
  }, [processos, selectedProcessoId])

  if (lcli) return <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 80 }}><Spinner size={28} /></div>
  if (ecli || !cliente) return <ErrorBox message="Cliente não encontrado." />

  const processo = processos?.find(p => p.id === selectedProcessoId)

  return (
    <>
      {/* Header */}
      <div className="page-header" style={{ marginBottom: 20 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <button className="btn btn-ghost btn-sm" onClick={() => navigate('/hub')}>← Voltar</button>
          <div>
            <h1 className="page-title">{cliente.nome}</h1>
            <p className="page-subtitle">{cliente.telefone_whatsapp}</p>
          </div>
          <BadgeCRM nivel={cliente.crm_nivel} />
        </div>
      </div>

      {/* 3-column layout */}
      <div style={{ display: 'grid', gridTemplateColumns: '220px 1fr 360px', gap: 16, height: 'calc(100vh - 160px)', minHeight: 0 }}>

        {/* Col 1: Cliente Info */}
        <div className="surface" style={{ padding: 16, overflowY: 'auto' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, marginBottom: 10 }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Dados do Cliente</div>
            <button
              className="btn btn-secondary btn-sm"
              onClick={() => exportarDados.mutate()}
              disabled={exportarDados.isPending}
              title="Baixar exportação LGPD"
            >
              {exportarDados.isPending ? <Spinner size={12} /> : null} Exportar LGPD
            </button>
          </div>
          {exportarDados.error ? <ErrorBox message="Falha ao gerar a exportação LGPD do cliente." /> : null}
          <InfoRow label="CPF" value={cliente.cpf ?? 'Protegido (LGPD)'} />
          <InfoRow label="Status" value={<span style={{ color: cliente.ativo ? 'var(--success)' : 'var(--danger)' }}>{cliente.ativo ? 'Ativo' : 'Inativo'}</span>} />
          <div style={{ marginTop: 10, fontSize: 11, color: 'var(--text-muted)', lineHeight: 1.5 }}>
            A exportação completa de dados pessoais, processos e interações fica disponível quando você solicitar.
          </div>
        </div>

        {/* Col 2: Processo + Score */}
        <div style={{ overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 14 }}>
          {/* Processo */}
          <div className="surface" style={{ padding: 16 }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 10 }}>Processo Judicial</div>

            {/* Tabs para múltiplos processos */}
            {processos && processos.length > 1 && (
              <div style={{ display: 'flex', gap: 4, marginBottom: 12, flexWrap: 'wrap' }}>
                {processos.map(p => (
                  <button
                    key={p.id}
                    className={`btn btn-sm ${processo?.id === p.id ? 'btn-primary' : 'btn-secondary'}`}
                    onClick={() => setSelectedProcessoId(p.id)}
                    title={p.numero_cnj}
                  >
                    {p.numero_cnj.slice(-8)}
                  </button>
                ))}
              </div>
            )}

            {lproc ? <Spinner /> : !processos || processos.length === 0 ? (
              <EmptyState
                icon="📋"
                title="Nenhum processo vinculado"
                desc="Este cliente ainda não possui processos cadastrados."
              />
            ) : processo ? (
              <>
                <InfoRow label="CNJ" value={<code style={{ fontSize: 10 }}>{processo.numero_cnj}</code>} />
                <InfoRow label="Tribunal" value={processo.tribunal} />
                <InfoRow label="Tipo de Ação" value={processo.tipo_acao} />
                <InfoRow label="Polo" value={processo.polo_cliente?.toUpperCase()} />
                <InfoRow label="Último Andamento" value={processo.ultimo_andamento} />
                <InfoRow label="Data" value={processo.data_ultimo_andamento ? new Date(processo.data_ultimo_andamento).toLocaleDateString('pt-BR') : '—'} />
                <InfoRow label="Monitoramento" value={<span style={{ color: processo.monitoramento_ativo ? 'var(--success)' : 'var(--text-muted)' }}>{processo.monitoramento_ativo ? '✅ Ativo' : 'Inativo'}</span>} />
              </>
            ) : null}
          </div>

          {/* Score de Risco */}
          {processo?.score_risco != null && (
            <div className="surface" style={{ padding: 16 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Score de Risco (Feature 2)</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontSize: 22, fontWeight: 700, color: 'var(--text-primary)' }}>{processo.score_risco}</span>
                  <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>/100</span>
                  <BadgeRisco nivel={processo.score_nivel} />
                </div>
              </div>
              <ProgressBar value={processo.score_risco} max={100} height={7} />
              {processo.score_interpretacao && (
                <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 8, lineHeight: 1.5 }}>{processo.score_interpretacao}</p>
              )}
              <p style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 8, fontStyle: 'italic' }}>
                Uso exclusivo interno — não representa previsão de resultado (OAB Provimento 205/2021)
              </p>
            </div>
          )}
        </div>

        {/* Col 3: Chat */}
        <div className="surface" style={{ padding: 16, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 12 }}>
            Chat com IA
          </div>
          <div style={{ flex: 1, minHeight: 0 }}>
            <ChatWindow clienteId={clienteId} />
          </div>
        </div>
      </div>
    </>
  )
}
