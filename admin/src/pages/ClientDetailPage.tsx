import { useState, useRef, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { clientesApi, processosApi } from '../api'
import { chatApi, type Mensagem } from '../api/chat'
import { BadgeCRM, BadgeRisco, ProgressBar, Spinner, ErrorBox } from '../components/ui'

const ESCALACAO = new Set(['parecer_juridico', 'estrategia_processual', 'negociacao', 'decisao_judicial_impacto_alto'])

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '5px 0', borderBottom: '1px solid var(--surface-border-muted)', fontSize: 12 }}>
      <span style={{ color: 'var(--text-muted)', flexShrink: 0, marginRight: 8 }}>{label}</span>
      <span style={{ color: 'var(--text-secondary)', textAlign: 'right' }}>{value ?? '—'}</span>
    </div>
  )
}

function ChatWindow({ clienteId }: { clienteId: number }) {
  const qc = useQueryClient()
  const bottomRef = useRef<HTMLDivElement>(null)
  const { data: msgs, isLoading } = useQuery({
    queryKey: ['chat', clienteId],
    queryFn: () => chatApi.historico(clienteId),
    staleTime: 0,
  })
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [localMsgs, setLocalMsgs] = useState<Array<{ role: 'user' | 'ai'; content: string; meta?: Record<string, unknown> }>>([])

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
      setLocalMsgs(p => [...p, { role: 'ai', content: res.resposta, meta: { intencao: res.intencao, tokens: res.tokens_usados, fallback: res.usando_fallback } }])
      qc.invalidateQueries({ queryKey: ['chat', clienteId] })
    } catch {
      setLocalMsgs(p => [...p, { role: 'ai', content: '⚠️ Erro ao processar. Tente novamente.' }])
    } finally { setSending(false) }
  }

  // Merge: histórico da API + mensagens locais da sessão (evitar duplicatas)
  const apiMsgs: Mensagem[] = msgs ?? []

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      {/* Histórico */}
      <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 8, padding: '4px 0 12px' }}>
        {isLoading && <div style={{ textAlign: 'center', paddingTop: 20 }}><Spinner /></div>}

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
              <div>
                <div className="chat-bubble-ai" style={{ whiteSpace: 'pre-wrap' }}>{m.content}</div>
                {m.meta && (
                  <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 3, marginLeft: 4, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                    {m.meta.intencao && <span>intent: <code>{String(m.meta.intencao)}</code></span>}
                    {m.meta.tokens && <span>tokens: {(m.meta.tokens as { input: number; output: number }).input}↑ {(m.meta.tokens as { input: number; output: number }).output}↓</span>}
                    {ESCALACAO.has(String(m.meta.intencao)) && <span style={{ color: '#fca5a5' }}>🚨 escalado</span>}
                    {m.meta.fallback && <span style={{ color: 'var(--warning)' }}>⚠️ fallback</span>}
                  </div>
                )}
              </div>
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

  const { data: cliente, isLoading: lcli, error: ecli } = useQuery({
    queryKey: ['cliente', clienteId],
    queryFn: () => clientesApi.detalhe(clienteId),
  })
  const { data: processos, isLoading: lproc } = useQuery({
    queryKey: ['processos', clienteId],
    queryFn: () => processosApi.porCliente(clienteId),
  })

  if (lcli) return <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 80 }}><Spinner size={28} /></div>
  if (ecli || !cliente) return <ErrorBox message="Cliente não encontrado." />

  const processo = processos?.[0]

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
          <BadgeCRM nivel={cliente.crm_nivel as never} />
        </div>
      </div>

      {/* 3-column layout */}
      <div style={{ display: 'grid', gridTemplateColumns: '220px 1fr 360px', gap: 16, height: 'calc(100vh - 160px)', minHeight: 0 }}>

        {/* Col 1: Cliente Info */}
        <div className="surface" style={{ padding: 16, overflowY: 'auto' }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 10 }}>Dados do Cliente</div>
          <InfoRow label="CPF" value={cliente.cpf} />
          <InfoRow label="Nascimento" value={cliente.data_nascimento} />
          <InfoRow label="Profissão" value={cliente.profissao} />
          <InfoRow label="Empresa" value={cliente.empresa} />
          <InfoRow label="Status" value={<span style={{ color: cliente.ativo ? 'var(--success)' : 'var(--danger)' }}>{cliente.ativo ? 'Ativo' : 'Inativo'}</span>} />
        </div>

        {/* Col 2: Processo + Score */}
        <div style={{ overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 14 }}>
          {/* Processo */}
          <div className="surface" style={{ padding: 16 }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 10 }}>Processo Judicial</div>
            {lproc ? <Spinner /> : !processo ? (
              <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>Nenhum processo vinculado.</div>
            ) : (
              <>
                <InfoRow label="CNJ" value={<code style={{ fontSize: 10 }}>{processo.numero_cnj}</code>} />
                <InfoRow label="Tribunal" value={processo.tribunal} />
                <InfoRow label="Tipo de Ação" value={processo.tipo_acao} />
                <InfoRow label="Polo" value={processo.polo_cliente?.toUpperCase()} />
                <InfoRow label="Último Andamento" value={processo.ultimo_andamento} />
                <InfoRow label="Data" value={processo.data_ultimo_andamento} />
                <InfoRow label="Monitoramento" value={<span style={{ color: processo.monitoramento_ativo ? 'var(--success)' : 'var(--text-muted)' }}>{processo.monitoramento_ativo ? '✅ Ativo' : 'Inativo'}</span>} />
              </>
            )}
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
