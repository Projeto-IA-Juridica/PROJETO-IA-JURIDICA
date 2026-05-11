import { useState, useRef, useEffect } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Send, BookOpen, AlertTriangle, FileText } from 'lucide-react'
import { consultar } from '../api/hub'
import { fetchProcessos } from '../api/processos'
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

export default function ChatTab({ cliente }: { cliente: CRMClienteCard }) {
  const [messages, setMessages] = useState<ChatMessage[]>([{
    role: 'assistant',
    content: `Olá! Estou aqui para auxiliar no caso de ${cliente.nome}. Pode perguntar sobre o processo, prazos, termos jurídicos ou qualquer dúvida.`,
    intencao: 'saudacao',
  }])
  const [input, setInput] = useState('')
  const messagesRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const { data: processoData } = useQuery({
    queryKey: ['processos', cliente.id],
    queryFn: () => fetchProcessos(cliente.id),
    enabled: cliente.total_processos > 0,
  })
  const processo = processoData?.items[0] ?? null

  const mutation = useMutation({
    mutationFn: (pergunta: string) =>
      consultar({ pergunta, cliente_id: cliente.id, processo_id: processo?.id }),
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
  })

  useEffect(() => {
    const el = messagesRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages, mutation.isPending])

  function handleSend() {
    const text = input.trim()
    if (!text || mutation.isPending) return
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

      {/* ── Status IA ── */}
      <div className="flex items-center gap-2.5 px-4 sm:px-5 py-2.5 flex-shrink-0"
        style={{ background: 'rgba(26,158,120,0.06)', borderBottom: '1px solid rgba(26,158,120,0.18)' }}>
        <span className="w-1.5 h-1.5 rounded-full glow-green flex-shrink-0" style={{ background: '#1A9E78' }} />
        <span className="text-xs text-am-secondary">
          IA configurada como <strong className="text-am-ink">Dra. Camila</strong>
          <span className="mx-1.5 text-am-muted">·</span>
          Tom formal · Verifica fatos
        </span>
      </div>

      {/* ── Contexto RAG ── */}
      {processo && (
        <div className="px-4 sm:px-5 py-2.5 flex-shrink-0 bg-am-bg border-b border-am-border">
          <div className="flex items-center gap-1.5 text-[9px] font-bold text-am-muted uppercase tracking-widest mb-2">
            <BookOpen size={9} className="text-am-blue" />
            Contexto ativo — {cliente.nome.split(' ')[0]}
          </div>
          <div className="flex flex-wrap gap-1.5">
            {[processo.tipo_acao, processo.tribunal, processo.status].filter(Boolean).map((v) => (
              <span key={v}
                className="flex items-center gap-1 text-[10px] font-semibold rounded-md"
                style={{ color: 'var(--color-am-blue)', background: 'rgba(58,122,184,0.08)', border: '1px solid rgba(58,122,184,0.18)', padding: '2px 7px' }}>
                <FileText size={8} />
                {v}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* ── Mensagens ── */}
      <div ref={messagesRef} className="flex-1 overflow-y-auto px-4 sm:px-6 py-5 space-y-4 bg-am-bg">
        {messages.map((msg, i) => <MessageBubble key={i} msg={msg} />)}
        {mutation.isPending && <TypingIndicator />}
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
          placeholder="Pergunte sobre o processo, termos jurídicos ou prazos…"
          disabled={mutation.isPending}
          className="flex-1 px-3.5 py-2.5 text-xs border border-am-border rounded-xl resize-none outline-none
            font-sans text-am-ink bg-am-bg transition-fast placeholder:text-am-muted
            disabled:opacity-50 max-h-[120px]"
          onFocus={(e) => (e.target.style.borderColor = 'var(--color-am-blue)')}
          onBlur={(e)  => (e.target.style.borderColor = 'var(--color-am-border)')}
        />
        <button
          onClick={handleSend}
          disabled={!input.trim() || mutation.isPending}
          className="w-9 h-9 flex items-center justify-center rounded-xl text-white flex-shrink-0 transition-fast disabled:opacity-40 disabled:cursor-not-allowed"
          style={{ background: 'var(--color-am-blue)' }}
          onMouseEnter={(e) => { if (!mutation.isPending && input.trim()) e.currentTarget.style.background = 'var(--color-am-blue-hover)' }}
          onMouseLeave={(e) => { e.currentTarget.style.background = 'var(--color-am-blue)' }}
        >
          <Send size={13} />
        </button>
      </div>
    </div>
  )
}
