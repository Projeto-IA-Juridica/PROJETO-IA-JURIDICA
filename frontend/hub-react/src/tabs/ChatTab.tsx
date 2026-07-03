import { useState, useRef, useEffect } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Send, BookOpen, AlertTriangle, History, ChevronDown, ChevronUp } from 'lucide-react'
import { consultar, fetchConversa } from '../api/hub'
import { fetchChatHistory, type InteracaoItem } from '../api/chat'
import type { CRMClienteCard, ChatMessage } from '../types'

const ESCALATION_TERMS = /parecer|estratégia|estrategia|negociação|negociacao|decisão|decisao|impacto|urgente/i
const RAG_TERMS = /processo|andamento|prazo|risco|dano|indeniz|contrat|cobran|réu|reu|autor|tribunal|sentença|sentenca/i

const INTENT_LABELS: Record<string, string> = {
  saudacao:                      'Boas-vindas',
  status_processo:               'Consulta de andamento',
  duvida_juridica:               'Dúvida jurídica',
  prazo:                         'Consulta de prazo',
  parecer_juridico:              'Parecer jurídico',
  estrategia_processual:         'Estratégia processual',
  negociacao:                    'Negociação',
  decisao_judicial_impacto_alto: 'Decisão de alto impacto',
  analise_peticao:               'Análise de petição',
  duvida_termo:                  'Dúvida jurídica',
  outro:                         'Atendimento geral',
}

function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser     = msg.role === 'user'
  const intentLabel = msg.intencao ? (INTENT_LABELS[msg.intencao] ?? msg.intencao) : null

  return (
    <div className={`flex flex-col ${isUser ? 'items-end' : 'items-start'} gap-1.5`}>
      {!isUser && (
        <div className="flex items-center gap-1.5 px-1">
          <div className="w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 text-white text-[9px] font-bold"
            style={{ background: '#1A9E78' }}>
            C
          </div>
          <span className="text-[10px] font-bold text-am-muted">Dra. Camila · Amicus IA</span>
        </div>
      )}

      <div
        className={`max-w-[80%] sm:max-w-[75%] px-4 py-3 text-xs leading-relaxed
          ${isUser ? 'bubble-user text-white' : 'bubble-assistant bg-white border border-am-border text-am-ink card-shadow'}`}
        style={isUser ? { background: 'var(--color-am-blue)' } : {}}
      >
        {msg.content}
      </div>

      {!isUser && (intentLabel || msg.ragAtivo || msg.escalacao) && (
        <div className="flex flex-wrap gap-1.5 px-1">
          {intentLabel && (
            <span className="text-[10px] font-semibold px-2 py-0.5 rounded-md"
              style={{ color: 'var(--color-am-blue)', background: 'rgba(58,122,184,0.08)', border: '1px solid rgba(58,122,184,0.2)' }}>
              {intentLabel}
            </span>
          )}
          {msg.ragAtivo && (
            <span className="flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-md"
              style={{ color: '#1A9E78', background: 'rgba(26,158,120,0.08)', border: '1px solid rgba(26,158,120,0.2)' }}>
              <BookOpen size={9} />
              Base de conhecimento ativa
            </span>
          )}
          {msg.escalacao && (
            <span className="flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-md"
              style={{ color: '#C83030', background: 'rgba(200,48,48,0.08)', border: '1px solid rgba(200,48,48,0.2)' }}>
              <AlertTriangle size={9} />
              Advogado notificado
            </span>
          )}
        </div>
      )}
    </div>
  )
}

function TypingIndicator() {
  return (
    <div className="flex flex-col items-start gap-1.5">
      <div className="flex items-center gap-1.5 px-1">
        <div className="w-5 h-5 rounded-full flex items-center justify-center text-white text-[9px] font-bold flex-shrink-0"
          style={{ background: '#1A9E78' }}>C</div>
        <span className="text-[10px] font-bold text-am-muted">Dra. Camila está digitando…</span>
      </div>
      <div className="bubble-assistant bg-white border border-am-border card-shadow px-4 py-3">
        <div className="dot-pulse flex gap-1.5"><span /><span /><span /></div>
      </div>
    </div>
  )
}

function HistoricoPanel({ clienteId }: { clienteId: number }) {
  const [open, setOpen] = useState(false)

  const { data: historico, isLoading } = useQuery({
    queryKey: ['chat-history', clienteId],
    queryFn: () => fetchChatHistory(clienteId, 30),
    enabled: open,
    staleTime: 60_000,
  })

  const fmt = (iso: string) =>
    new Date(iso).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })

  return (
    <div className="flex-shrink-0 border-b border-am-border">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 px-4 sm:px-5 py-2.5 bg-am-bg hover:bg-am-surface transition-fast"
      >
        <History size={11} className="text-am-muted" />
        <span className="text-[10px] font-bold uppercase tracking-wider text-am-muted flex-1 text-left">
          Histórico WhatsApp
        </span>
        {open ? <ChevronUp size={11} className="text-am-muted" /> : <ChevronDown size={11} className="text-am-muted" />}
      </button>

      {open && (
        <div className="max-h-52 overflow-y-auto bg-white divide-y divide-am-border">
          {isLoading ? (
            <div className="flex items-center justify-center py-4">
              <span className="text-[10px] text-am-muted">Carregando…</span>
            </div>
          ) : !historico?.length ? (
            <div className="py-4 text-center text-[10px] text-am-muted">Nenhuma interação anterior</div>
          ) : (
            (historico as InteracaoItem[]).map((item) => (
              <div key={item.id} className="px-4 py-2.5 space-y-1">
                <div className="flex items-center justify-between">
                  <span className="text-[9px] font-bold uppercase tracking-wider"
                    style={{ color: item.direcao === 'entrada' ? 'var(--color-am-blue)' : '#1A9E78' }}>
                    {item.direcao === 'entrada' ? 'Cliente' : 'IA'}
                  </span>
                  <span className="text-[9px] text-am-muted">{fmt(item.data)}</span>
                </div>
                {item.mensagem_cliente && (
                  <p className="text-[11px] text-am-secondary leading-snug line-clamp-2">{item.mensagem_cliente}</p>
                )}
                {item.mensagem_ia && (
                  <p className="text-[11px] text-am-muted leading-snug line-clamp-2 italic">{item.mensagem_ia}</p>
                )}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  )
}

function saudacaoInicial(nomeCliente: string): ChatMessage {
  return {
    role: 'assistant',
    content: `Olá! Estou aqui para auxiliar no caso de ${nomeCliente}. Pode perguntar sobre o processo, prazos, termos jurídicos ou qualquer dúvida.`,
    intencao: 'saudacao',
  }
}

function conversaStorageKey(clienteId: number) {
  return `hub_chat_conversa_id_${clienteId}`
}

export default function ChatTab({ cliente }: { cliente: CRMClienteCard }) {
  const [messages, setMessages] = useState<ChatMessage[]>([saudacaoInicial(cliente.nome)])
  const [input, setInput] = useState('')
  // Enquanto uma conversa anterior está sendo retomada do backend, o envio
  // fica bloqueado — sem isso, uma pergunta enviada antes do fetchConversa
  // resolver seria apagada quando o histórico chegasse e sobrescrevesse
  // `messages` por inteiro.
  const [carregandoHistorico, setCarregandoHistorico] = useState(false)
  const messagesRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  // conversa_id é persistido por cliente (localStorage), não gerado do zero
  // a cada montagem — sem isso, trocar de aba (Processo/Score/Documentos) e
  // voltar para "Assistente" recriava o componente e perdia a memória da
  // conversa com o Opus, mesmo dentro da mesma visita ao Hub.
  const conversaIdRef = useRef<string>('')

  useEffect(() => {
    const key = conversaStorageKey(cliente.id)
    const existente = localStorage.getItem(key)
    const conversaId = existente || crypto.randomUUID()
    conversaIdRef.current = conversaId
    localStorage.setItem(key, conversaId)

    if (!existente) {
      setMessages([saudacaoInicial(cliente.nome)])
      setCarregandoHistorico(false)
      return
    }

    // Retoma a conversa anterior buscando as trocas já salvas no backend.
    let cancelado = false
    setCarregandoHistorico(true)
    fetchConversa(existente)
      .then((turnos) => {
        if (cancelado) return
        if (!turnos.length) {
          setMessages([saudacaoInicial(cliente.nome)])
          return
        }
        const historico: ChatMessage[] = turnos.flatMap((t) => [
          { role: 'user', content: t.mensagem_advogado } as ChatMessage,
          { role: 'assistant', content: t.resposta_hub, intencao: 'duvida_juridica' } as ChatMessage,
        ])
        setMessages([saudacaoInicial(cliente.nome), ...historico])
      })
      .catch(() => {
        if (!cancelado) setMessages([saudacaoInicial(cliente.nome)])
      })
      .finally(() => {
        if (!cancelado) setCarregandoHistorico(false)
      })

    return () => {
      cancelado = true
    }
  }, [cliente.id, cliente.nome])

  const mutation = useMutation({
    mutationFn: (pergunta: string) =>
      consultar({
        pergunta,
        cliente_id: cliente.id,
        conversa_id: conversaIdRef.current,
      }),
    onSuccess: (data, pergunta) => {
      setMessages((prev) => [...prev, {
        role: 'assistant',
        content: data.resposta,
        intencao: 'duvida_juridica',
        ragAtivo: RAG_TERMS.test(pergunta),
        escalacao: ESCALATION_TERMS.test(pergunta),
        tokens: data.tokens_output,
      }])
    },
    onError: (err: any) => {
      const msg = err.response?.data?.detail || err.message || "Erro desconhecido"
      console.error("ERRO DETALHADO DO BACKEND:", msg)
      alert("ERRO: \n" + msg)
    }
  })

  useEffect(() => {
    const el = messagesRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages, mutation.isPending])

  function handleSend() {
    const text = input.trim()
    if (!text || mutation.isPending || carregandoHistorico) return
    setInput('')
    if (textareaRef.current) textareaRef.current.style.height = 'auto'
    setMessages((prev) => [...prev, { role: 'user', content: text }])
    mutation.mutate(text)
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() }
  }

  function handleInput() {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 120) + 'px'
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">

      {/* ── Histórico WhatsApp ── */}
      <HistoricoPanel clienteId={cliente.id} />

      {/* ── Mensagens ── */}
      <div ref={messagesRef} className="flex-1 overflow-y-auto px-4 sm:px-6 py-5 space-y-4 bg-am-bg">
        {messages.map((msg, i) => <MessageBubble key={i} msg={msg} />)}
        {(mutation.isPending || carregandoHistorico) && <TypingIndicator />}
        {mutation.isError && (
          <div className="flex items-center gap-2 p-3 rounded-xl text-xs"
            style={{ background: 'rgba(200,48,48,0.07)', border: '1px solid rgba(200,48,48,0.2)', color: '#C83030' }}>
            <AlertTriangle size={12} />
            Erro ao enviar. Verifique o token e tente novamente.
          </div>
        )}
      </div>

      {/* ── Input ── */}
      <div className="flex items-end gap-2 sm:gap-3 px-3 sm:px-5 py-3 sm:py-4 flex-shrink-0 bg-white border-t border-am-border">
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          onInput={handleInput}
          rows={1}
          placeholder={carregandoHistorico ? 'Carregando conversa anterior…' : 'Pergunte sobre o processo, termos jurídicos ou prazos…'}
          disabled={mutation.isPending || carregandoHistorico}
          className="am-textarea flex-1 max-h-[120px] disabled:opacity-50"
        />
        <button
          onClick={handleSend}
          disabled={!input.trim() || mutation.isPending || carregandoHistorico}
          className="w-9 h-9 flex items-center justify-center rounded-xl text-white flex-shrink-0 transition-fast disabled:opacity-40 disabled:cursor-not-allowed"
          style={{ background: 'var(--color-am-blue)' }}
          onMouseEnter={(e) => { if (!mutation.isPending && !carregandoHistorico && input.trim()) e.currentTarget.style.background = 'var(--color-am-blue-hover)' }}
          onMouseLeave={(e) => { e.currentTarget.style.background = 'var(--color-am-blue)' }}
        >
          <Send size={13} />
        </button>
      </div>
    </div>
  )
}
