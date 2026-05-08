import { useState, useRef, useEffect } from 'react'
import { useMutation } from '@tanstack/react-query'
import {
  Sparkles, Send, BookOpen, Scale, FileSearch,
  AlertTriangle, ChevronRight, RotateCcw,
} from 'lucide-react'
import { consultar } from '../api/hub'
import type { ChatMessage } from '../types'

type Tool = 'chat' | 'peticao' | 'jurisprudencia'

const TOOLS: { id: Tool; icon: React.ReactNode; label: string; desc: string }[] = [
  { id: 'chat',          icon: <Sparkles size={16} />,   label: 'Assistente Jurídico', desc: 'Consulte a IA sobre qualquer tema do direito' },
  { id: 'peticao',       icon: <Scale size={16} />,      label: 'Análise de Petição',  desc: 'Gere e refine petições com suporte da IA'     },
  { id: 'jurisprudencia',icon: <FileSearch size={16} />, label: 'Jurisprudência',       desc: 'Pesquise precedentes e teses jurídicas'       },
]

const QUICK_PROMPTS: Record<Tool, string[]> = {
  chat: [
    'O que é responsabilidade civil objetiva?',
    'Quais os requisitos para dano moral?',
    'Explique prescrição e decadência',
    'Diferença entre nulidade e anulabilidade',
  ],
  peticao: [
    'Modele uma petição inicial para indenização por dano moral',
    'Redija uma contestação para ação de cobrança',
    'Crie um recurso de apelação para decisão de improcedência',
    'Elabore uma réplica rebatendo alegações genéricas',
  ],
  jurisprudencia: [
    'STJ sobre dano moral em atraso de voo',
    'Teses STF sobre responsabilidade do Estado',
    'Súmulas do TST sobre horas extras',
    'Precedentes sobre inversão do ônus da prova',
  ],
}

const INTENT_MAP: Record<Tool, string> = {
  chat:           'duvida_juridica',
  peticao:        'analise_peticao',
  jurisprudencia: 'duvida_juridica',
}

function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === 'user'
  return (
    <div className={`flex flex-col ${isUser ? 'items-end' : 'items-start'} gap-1.5`}>
      {!isUser && (
        <div className="flex items-center gap-1.5 px-1">
          <div className="w-5 h-5 rounded-full flex items-center justify-center text-white text-[9px] font-bold flex-shrink-0"
            style={{ background: '#1A9E78' }}>C</div>
          <span className="text-[10px] font-bold text-am-muted">Dra. Camila · Amicus IA</span>
        </div>
      )}
      <div className={`max-w-[85%] sm:max-w-[78%] px-4 py-3 text-xs leading-relaxed whitespace-pre-wrap
        ${isUser
          ? 'bubble-user text-white'
          : 'bubble-assistant bg-white border border-am-border text-am-ink card-shadow'}`}
        style={isUser ? { background: 'var(--color-am-blue)' } : {}}>
        {msg.content}
      </div>
    </div>
  )
}

function TypingIndicator() {
  return (
    <div className="flex flex-col items-start gap-1.5">
      <div className="flex items-center gap-1.5 px-1">
        <div className="w-5 h-5 rounded-full flex items-center justify-center text-white text-[9px] font-bold"
          style={{ background: '#1A9E78' }}>C</div>
        <span className="text-[10px] font-bold text-am-muted">Dra. Camila está digitando…</span>
      </div>
      <div className="bubble-assistant bg-white border border-am-border card-shadow px-4 py-3">
        <div className="dot-pulse flex gap-1.5"><span /><span /><span /></div>
      </div>
    </div>
  )
}

export default function HubIAPage() {
  const [tool, setTool]         = useState<Tool>('chat')
  const [messages, setMessages] = useState<ChatMessage[]>([{
    role: 'assistant',
    content: 'Olá! Sou a Dra. Camila, sua assistente jurídica. Como posso ajudar hoje? Pode me fazer qualquer pergunta sobre direito, pedir análise de documentos ou pesquisar jurisprudência.',
    intencao: 'saudacao',
  }])
  const [input, setInput]       = useState('')
  const messagesRef             = useRef<HTMLDivElement>(null)
  const textareaRef             = useRef<HTMLTextAreaElement>(null)

  const mutation = useMutation({
    mutationFn: (pergunta: string) => consultar({ pergunta }),
    onSuccess: (data) => {
      setMessages((prev) => [...prev, {
        role: 'assistant',
        content: data.resposta,
        intencao: INTENT_MAP[tool],
        tokens: data.tokens_output,
      }])
    },
  })

  useEffect(() => {
    const el = messagesRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages, mutation.isPending])

  function handleSend(text?: string) {
    const t = (text ?? input).trim()
    if (!t || mutation.isPending) return
    setInput('')
    if (textareaRef.current) textareaRef.current.style.height = 'auto'
    setMessages((prev) => [...prev, { role: 'user', content: t }])
    mutation.mutate(t)
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

  function resetChat() {
    setMessages([{
      role: 'assistant',
      content: 'Nova conversa iniciada. Como posso ajudar?',
      intencao: 'saudacao',
    }])
    setInput('')
  }

  function switchTool(t: Tool) {
    setTool(t)
    resetChat()
  }

  const currentTool = TOOLS.find((t) => t.id === tool)!
  const placeholder =
    tool === 'peticao'        ? 'Descreva o caso e o tipo de petição desejada…' :
    tool === 'jurisprudencia' ? 'Pesquise uma tese, súmula ou precedente…' :
    'Pergunte qualquer coisa sobre direito…'

  return (
    <div className="flex flex-col h-full overflow-hidden">

      {/* Tool switcher */}
      <div className="flex-shrink-0 px-4 sm:px-6 pt-4 pb-0">
        <div className="flex gap-2 sm:gap-3 pb-3 border-b border-am-border overflow-x-auto">
          {TOOLS.map((t) => {
            const active = tool === t.id
            return (
              <button key={t.id} onClick={() => switchTool(t.id)}
                className="flex items-center gap-2 px-3 py-2 rounded-xl text-xs font-semibold whitespace-nowrap press flex-shrink-0"
                style={active
                  ? { background: 'var(--color-am-surface)', color: 'var(--color-am-blue)', border: '1px solid var(--color-am-border)', borderBottom: '2px solid var(--color-am-blue)' }
                  : { background: 'transparent', color: 'var(--color-am-muted)', border: '1px solid transparent' }
                }>
                <span style={{ color: active ? 'var(--color-am-blue)' : 'var(--color-am-muted)' }}>{t.icon}</span>
                <span className="hidden sm:inline">{t.label}</span>
              </button>
            )
          })}

          <button onClick={resetChat}
            className="ml-auto flex items-center gap-1.5 px-3 py-2 rounded-xl text-[10px] font-semibold whitespace-nowrap text-am-muted hover:text-am-secondary press flex-shrink-0"
            style={{ border: '1px solid var(--color-am-border)' }}>
            <RotateCcw size={11} />
            <span className="hidden sm:inline">Nova conversa</span>
          </button>
        </div>
      </div>

      {/* Tool description + status */}
      <div className="flex-shrink-0 flex items-center gap-3 px-4 sm:px-6 py-2.5"
        style={{ background: 'rgba(26,158,120,0.05)', borderBottom: '1px solid rgba(26,158,120,0.15)' }}>
        <span className="w-1.5 h-1.5 rounded-full glow-green flex-shrink-0" style={{ background: '#1A9E78' }} />
        <div className="flex items-center gap-1.5 min-w-0">
          <span className="text-xs font-semibold text-am-ink flex-shrink-0">{currentTool.label}</span>
          <span className="text-am-muted text-xs flex-shrink-0">·</span>
          <span className="text-xs text-am-muted truncate">{currentTool.desc}</span>
        </div>
        <span className="ml-auto text-[9px] font-bold px-1.5 py-0.5 rounded flex-shrink-0"
          style={{ background: 'rgba(26,158,120,0.18)', color: '#1A9E78' }}>ONLINE</span>
      </div>

      {/* Messages */}
      <div ref={messagesRef} className="flex-1 overflow-y-auto px-4 sm:px-6 py-5 space-y-4 bg-am-bg">

        {/* Quick prompts — only when single welcome message */}
        {messages.length === 1 && (
          <div className="space-y-2">
            <div className="flex items-center gap-1.5 px-1">
              <BookOpen size={10} className="text-am-muted" />
              <span className="text-[10px] font-bold text-am-muted uppercase tracking-wider">Sugestões rápidas</span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {QUICK_PROMPTS[tool].map((p) => (
                <button key={p} onClick={() => handleSend(p)}
                  className="flex items-center gap-2 px-3 py-2.5 rounded-xl text-left text-xs text-am-secondary font-medium
                    bg-white border border-am-border card-shadow hover:border-am-blue hover:text-am-ink hover-lift group">
                  <ChevronRight size={11} className="text-am-muted group-hover:text-am-blue transition-fast flex-shrink-0" />
                  {p}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, i) => <MessageBubble key={i} msg={msg} />)}
        {mutation.isPending && <TypingIndicator />}

        {mutation.isError && (
          <div className="flex items-center gap-2 p-3 rounded-xl text-xs"
            style={{ background: 'rgba(200,48,48,0.07)', border: '1px solid rgba(200,48,48,0.2)', color: '#C83030' }}>
            <AlertTriangle size={12} />
            Erro ao enviar. Verifique a conexão e tente novamente.
          </div>
        )}
      </div>

      {/* Input */}
      <div className="flex items-end gap-2 sm:gap-3 px-3 sm:px-5 py-3 sm:py-4 flex-shrink-0 bg-white border-t border-am-border">
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          onInput={handleInput}
          rows={1}
          placeholder={placeholder}
          disabled={mutation.isPending}
          className="flex-1 px-3.5 py-2.5 text-xs border border-am-border rounded-xl resize-none outline-none
            font-sans text-am-ink bg-am-bg transition-fast placeholder:text-am-muted
            disabled:opacity-50 max-h-[120px]"
          onFocus={(e) => (e.target.style.borderColor = 'var(--color-am-blue)')}
          onBlur={(e) => (e.target.style.borderColor = 'var(--color-am-border)')}
        />
        <button
          onClick={() => handleSend()}
          disabled={!input.trim() || mutation.isPending}
          className="w-9 h-9 flex items-center justify-center rounded-xl text-white flex-shrink-0
            transition-fast disabled:opacity-40 disabled:cursor-not-allowed"
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
