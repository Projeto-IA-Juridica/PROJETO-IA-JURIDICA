import { useState, useRef, useEffect } from 'react'
import { useMutation } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Sparkles, Scale, FileSearch,
  AlertTriangle, RotateCcw,
} from 'lucide-react'
import { consultar } from '../api/hub'
import type { ChatMessage } from '../types'
import { PlaceholdersAndVanishInput } from '../components/ui/PlaceholdersAndVanishInput'

type Tool = 'chat' | 'peticao' | 'jurisprudencia'

const TOOLS: { id: Tool; icon: React.ReactNode; label: string }[] = [
  { id: 'chat',          icon: <Sparkles size={13} />,   label: 'Assistente' },
  { id: 'peticao',       icon: <Scale size={13} />,      label: 'Petição'    },
  { id: 'jurisprudencia',icon: <FileSearch size={13} />, label: 'Jurisprudência' },
]

const QUICK_PROMPTS: Record<Tool, string[]> = {
  chat: [
    'O que é responsabilidade civil objetiva?',
    'Quais os requisitos para dano moral?',
    'Explique prescrição e decadência',
    'Diferença entre nulidade e anulabilidade',
  ],
  peticao: [
    'Petição inicial para indenização por dano moral',
    'Contestação para ação de cobrança',
    'Recurso de apelação — decisão de improcedência',
    'Réplica rebatendo alegações genéricas',
  ],
  jurisprudencia: [
    'STJ — dano moral em atraso de voo',
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

/* ── Bolha de mensagem ─────────────────────────────────────────────────── */
function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === 'user'
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      {!isUser && (
        <div className="flex items-end gap-2 max-w-[82%]">
          <div className="w-7 h-7 rounded-full flex items-center justify-center text-white text-[10px] font-bold flex-shrink-0 mb-0.5"
            style={{ background: 'linear-gradient(135deg,#1248BE,#4A8ED4)' }}>
            C
          </div>
          <div className="px-4 py-3 rounded-2xl rounded-bl-sm text-sm leading-relaxed whitespace-pre-wrap bg-white border border-am-border text-am-ink"
            style={{ boxShadow: '0 1px 6px rgba(12,30,48,0.06)' }}>
            {msg.content}
          </div>
        </div>
      )}
      {isUser && (
        <div className="max-w-[82%] px-4 py-3 rounded-2xl rounded-br-sm text-sm leading-relaxed whitespace-pre-wrap text-white"
          style={{ background: 'linear-gradient(135deg,#1248BE,#2D6FD4)' }}>
          {msg.content}
        </div>
      )}
    </div>
  )
}

/* ── Indicador de digitação ─────────────────────────────────────────────── */
function TypingIndicator() {
  return (
    <div className="flex justify-start">
      <div className="flex items-end gap-2">
        <div className="w-7 h-7 rounded-full flex items-center justify-center text-white text-[10px] font-bold flex-shrink-0"
          style={{ background: 'linear-gradient(135deg,#1248BE,#4A8ED4)' }}>C</div>
        <div className="px-4 py-3 rounded-2xl rounded-bl-sm bg-white border border-am-border"
          style={{ boxShadow: '0 1px 6px rgba(12,30,48,0.06)' }}>
          <div className="dot-pulse flex gap-1.5"><span /><span /><span /></div>
        </div>
      </div>
    </div>
  )
}

/* ── Página principal ────────────────────────────────────────────────────── */
export default function HubIAPage() {
  const [tool, setTool]         = useState<Tool>('chat')
  const [messages, setMessages] = useState<ChatMessage[]>([{
    role: 'assistant',
    content: 'Olá! Sou a Dra. Camila, sua assistente jurídica. Como posso ajudar hoje?',
    intencao: 'saudacao',
  }])
  const messagesRef             = useRef<HTMLDivElement>(null)

  const mutation = useMutation({
    mutationFn: (pergunta: string) => consultar({ pergunta }),
    onSuccess: (data) => {
      setMessages(prev => [...prev, {
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

  function handleSend(text: string) {
    const t = text.trim()
    if (!t || mutation.isPending) return
    setMessages(prev => [...prev, { role: 'user', content: t }])
    mutation.mutate(t)
  }

  function resetChat() {
    setMessages([{
      role: 'assistant',
      content: 'Nova conversa iniciada. Como posso ajudar?',
      intencao: 'saudacao',
    }])
  }

  function switchTool(t: Tool) {
    setTool(t)
    resetChat()
  }

  const isEmpty = messages.length === 1

  return (
    <div className="flex flex-col h-full overflow-hidden bg-am-bg">

      {/* ── Container centralizado ── */}
      <div className="flex flex-col h-full w-full max-w-2xl mx-auto">

        {/* ── Tool switcher ── */}
        <div className="flex-shrink-0 flex items-center justify-between px-4 pt-5 pb-3">
          <div className="flex gap-1 p-1 rounded-2xl relative" style={{ background: 'rgba(12,30,48,0.05)' }}>
            {TOOLS.map((t) => {
              const active = tool === t.id
              return (
                <motion.button
                  key={t.id}
                  onClick={() => switchTool(t.id)}
                  whileHover={{ scale: active ? 1 : 1.04 }}
                  whileTap={{ scale: 0.95 }}
                  transition={{ type: 'spring', stiffness: 380, damping: 22 }}
                  className="relative flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold whitespace-nowrap z-10"
                  style={{ color: active ? 'var(--color-am-blue)' : 'var(--color-am-muted)' }}
                >
                  {/* sliding pill de fundo */}
                  <AnimatePresence>
                    {active && (
                      <motion.span
                        layoutId="tool-pill"
                        className="absolute inset-0 rounded-xl"
                        style={{
                          background: 'white',
                          boxShadow: '0 1px 6px rgba(18,72,190,0.15), 0 0 0 1px rgba(18,72,190,0.08)',
                        }}
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        transition={{ type: 'spring', stiffness: 400, damping: 28 }}
                      />
                    )}
                  </AnimatePresence>
                  <span className="relative">{t.icon}</span>
                  <span className="relative">{t.label}</span>
                </motion.button>
              )
            })}
          </div>

          <button onClick={resetChat}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium text-am-muted hover:text-am-secondary transition-colors"
            style={{ border: '1px solid var(--color-am-border)', background: 'white' }}>
            <RotateCcw size={11} />
            Limpar
          </button>
        </div>

        {/* ── Área de mensagens ── */}
        <div ref={messagesRef} className="flex-1 overflow-y-auto px-4 py-4 space-y-4">

          {/* Estado vazio — sugestões rápidas */}
          {isEmpty && (
            <div className="flex flex-col items-center justify-center h-full gap-6 pb-4">
              <div className="text-center">
                <div className="w-12 h-12 rounded-2xl flex items-center justify-center mx-auto mb-3"
                  style={{ background: 'linear-gradient(135deg,#1248BE,#4A8ED4)', boxShadow: '0 4px 16px rgba(18,72,190,0.25)' }}>
                  <Sparkles size={22} className="text-white" />
                </div>
                <p className="text-sm font-semibold text-am-ink">Dra. Camila</p>
                <p className="text-xs text-am-muted mt-0.5">Assistente Jurídica · Amicus IA</p>
              </div>

              <div className="w-full grid grid-cols-2 gap-2">
                {QUICK_PROMPTS[tool].map((p) => (
                  <button key={p} onClick={() => handleSend(p)}
                    className="px-3 py-2.5 rounded-xl text-left text-xs text-am-secondary font-medium bg-white border border-am-border hover:border-am-blue hover:text-am-ink transition-all duration-200 leading-relaxed"
                    style={{ boxShadow: '0 1px 4px rgba(12,30,48,0.05)' }}>
                    {p}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Mensagens */}
          {!isEmpty && messages.map((msg, i) => <MessageBubble key={i} msg={msg} />)}
          {mutation.isPending && <TypingIndicator />}

          {mutation.isError && (
            <div className="flex items-center gap-2 px-3 py-2.5 rounded-xl text-xs"
              style={{ background: 'rgba(200,48,48,0.06)', border: '1px solid rgba(200,48,48,0.18)', color: '#C83030' }}>
              <AlertTriangle size={12} />
              Erro ao enviar. Verifique a conexão e tente novamente.
            </div>
          )}
        </div>

        {/* ── Input ── */}
        <div className="flex-shrink-0 px-4 pb-5 pt-2">
          <PlaceholdersAndVanishInput
            placeholders={QUICK_PROMPTS[tool]}
            onSubmit={handleSend}
            disabled={mutation.isPending}
          />
          <p className="text-center text-[10px] text-am-muted mt-2">
            Amicus IA pode cometer erros. Verifique informações importantes.
          </p>
        </div>

      </div>
    </div>
  )
}
