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
  const isUser = msg.role === 'user'
  const intentLabel = msg.intencao ? (INTENT_LABELS[msg.intencao] ?? msg.intencao) : null

  return (
    <div className={`flex flex-col ${isUser ? 'items-end' : 'items-start'} gap-1`}>
      {!isUser && (
        <div className="text-[10px] font-semibold text-am-muted tracking-wide px-1">
          Dra. Camila · Amicus IA
        </div>
      )}

      <div
        className={`max-w-[78%] px-3.5 py-2.5 text-xs leading-relaxed
          ${isUser
            ? 'bubble-user bg-am-blue text-white'
            : 'bubble-assistant bg-white border border-am-border text-am-ink'}`}
      >
        {msg.content}
      </div>

      {!isUser && (intentLabel || msg.ragAtivo || msg.escalacao) && (
        <div className="flex flex-wrap gap-1.5 px-1">
          {intentLabel && (
            <span className="text-[10px] font-medium px-1.5 py-0.5 rounded
              bg-blue-50 text-am-secondary border border-am-border">
              {intentLabel}
            </span>
          )}
          {msg.ragAtivo && (
            <span className="flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded
              bg-green-50 text-am-green border border-green-100">
              <BookOpen size={9} />
              Documentos do escritório
            </span>
          )}
          {msg.escalacao && (
            <span className="flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded
              bg-red-50 text-am-red border border-red-100">
              <AlertTriangle size={9} />
              Questão importante — advogado notificado
            </span>
          )}
        </div>
      )}
    </div>
  )
}

function TypingIndicator() {
  return (
    <div className="flex flex-col items-start gap-1">
      <div className="text-[10px] font-semibold text-am-muted tracking-wide px-1">
        Dra. Camila está digitando…
      </div>
      <div className="bubble-assistant bg-white border border-am-border px-4 py-3">
        <div className="dot-pulse flex gap-1.5">
          <span /><span /><span />
        </div>
      </div>
    </div>
  )
}

export default function ChatTab({ cliente }: { cliente: CRMClienteCard }) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: 'assistant',
      content: `Olá! Estou aqui para auxiliar no caso de ${cliente.nome}. Pode perguntar sobre o processo, prazos, termos jurídicos ou qualquer dúvida.`,
      intencao: 'saudacao',
    },
  ])
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
      consultar({
        pergunta,
        cliente_id: cliente.id,
        processo_id: processo?.id,
      }),
    onSuccess: (data, pergunta) => {
      const ragAtivo = RAG_TERMS.test(pergunta)
      const escalacao = ESCALATION_TERMS.test(pergunta)
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: data.resposta,
          intencao: 'duvida_juridica',
          ragAtivo,
          escalacao,
          tokens: data.tokens_output,
        },
      ])
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
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
    setMessages((prev) => [...prev, { role: 'user', content: text }])
    mutation.mutate(text)
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  function handleInput() {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 120) + 'px'
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* AI strip */}
      <div className="flex items-center gap-2 px-5 py-2.5 border-b border-am-border bg-am-bg text-xs text-am-secondary flex-shrink-0">
        <span className="w-1.5 h-1.5 rounded-full bg-am-green" />
        IA configurada como
        <strong className="text-am-ink">Dra. Camila</strong>
        · Tom formal · Verifica fatos antes de responder
      </div>

      {/* RAG panel */}
      {processo && (
        <div className="px-5 py-2.5 border-b border-am-border bg-[#F4F8FC]/80 flex-shrink-0">
          <div className="flex items-center gap-1.5 text-[10px] text-am-secondary font-medium mb-1.5">
            <BookOpen size={10} className="text-am-blue" />
            Documentos ativos para {cliente.nome.split(' ')[0]}
          </div>
          <div className="flex flex-wrap gap-1.5">
            {[
              processo.tipo_acao && { label: 'Tipo de ação', value: processo.tipo_acao },
              processo.tribunal && { label: 'Tribunal', value: processo.tribunal },
              processo.status && { label: 'Status', value: processo.status },
            ].filter(Boolean).map((item) => item && (
              <span key={item.label}
                className="flex items-center gap-1 text-[10px] text-am-secondary bg-white
                  border border-am-border px-2 py-0.5 rounded-md"
              >
                <FileText size={8} className="text-am-blue" />
                {item.value}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Messages */}
      <div
        ref={messagesRef}
        className="flex-1 overflow-y-auto px-6 py-5 space-y-4"
      >
        {messages.map((msg, i) => (
          <MessageBubble key={i} msg={msg} />
        ))}
        {mutation.isPending && <TypingIndicator />}
        {mutation.isError && (
          <div className="flex items-center gap-2 p-3 rounded-lg bg-red-50 border border-red-100 text-xs text-am-red">
            <AlertTriangle size={12} />
            Erro ao enviar. Verifique o token e tente novamente.
          </div>
        )}
      </div>

      {/* Input */}
      <div className="flex items-end gap-3 px-5 py-3.5 border-t border-am-border bg-white flex-shrink-0">
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          onInput={handleInput}
          rows={1}
          placeholder="Pergunte sobre o processo, termos jurídicos ou prazos…"
          disabled={mutation.isPending}
          className="flex-1 px-3.5 py-2.5 text-xs border border-am-border rounded-xl resize-none
            outline-none font-sans text-am-ink bg-white
            focus:border-am-blue transition-colors placeholder:text-am-muted
            disabled:opacity-50 max-h-[120px]"
        />
        <button
          onClick={handleSend}
          disabled={!input.trim() || mutation.isPending}
          className="w-9 h-9 flex items-center justify-center rounded-xl bg-am-blue text-white flex-shrink-0
            hover:bg-am-blue-hover transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <Send size={13} />
        </button>
      </div>
    </div>
  )
}
