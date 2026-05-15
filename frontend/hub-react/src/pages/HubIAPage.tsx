import { useState, useRef, useEffect, useCallback } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Sparkles, Scale, FileSearch, AlertTriangle, RotateCcw,
  Upload, ChevronDown, ChevronUp, Clock, X,
} from 'lucide-react'
import { consultar, analisarPeticao, listarHistorico, type PeticaoAnalise, type SessaoListItem } from '../api/hub'
import type { ChatMessage } from '../types'
import { PlaceholdersAndVanishInput } from '../components/ui/PlaceholdersAndVanishInput'

type Tool = 'chat' | 'peticao' | 'jurisprudencia'

const TOOLS: { id: Tool; icon: React.ReactNode; label: string }[] = [
  { id: 'chat',           icon: <Sparkles size={13} />,   label: 'Assistente'      },
  { id: 'peticao',        icon: <Scale size={13} />,      label: 'Petição'         },
  { id: 'jurisprudencia', icon: <FileSearch size={13} />, label: 'Jurisprudência'  },
]

const QUICK_PROMPTS: Record<Exclude<Tool, 'peticao'>, string[]> = {
  chat: [
    'O que é responsabilidade civil objetiva?',
    'Quais os requisitos para dano moral?',
    'Explique prescrição e decadência',
    'Diferença entre nulidade e anulabilidade',
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

/* ── MessageBubble ─────────────────────────────────────────────────────── */
function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === 'user'
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      {!isUser && (
        <div className="flex items-end gap-2 max-w-[82%]">
          <div className="w-7 h-7 rounded-full flex items-center justify-center text-white text-[10px] font-bold flex-shrink-0 mb-0.5"
            style={{ background: 'linear-gradient(135deg,#1248BE,#4A8ED4)' }}>C</div>
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

/* ── Análise de petição ─────────────────────────────────────────────────── */
function ScoreBar({ valor }: { valor: number }) {
  const cor = valor >= 70 ? '#1A9E78' : valor >= 40 ? '#D08010' : '#C83030'
  return (
    <div className="flex items-center gap-3">
      <div className="flex-1 h-2 rounded-full overflow-hidden" style={{ background: 'rgba(12,30,48,0.08)' }}>
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${valor}%` }}
          transition={{ duration: 0.8, ease: 'easeOut' }}
          className="h-full rounded-full"
          style={{ background: cor }}
        />
      </div>
      <span className="text-sm font-black w-8 text-right" style={{ color: cor }}>{valor}</span>
    </div>
  )
}

function AnalisePeticaoResult({ analise, onReset }: { analise: PeticaoAnalise; onReset: () => void }) {
  return (
    <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
      {/* Score */}
      <div className="bg-white rounded-2xl p-4" style={{ border: '1px solid var(--color-am-border)', boxShadow: '0 1px 4px rgba(12,30,48,0.05)' }}>
        <div className="flex items-center justify-between mb-3">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-wider text-am-secondary">Score geral</p>
            <p className="text-xs text-am-muted mt-0.5">{analise.tipo_peca}</p>
          </div>
          <button onClick={onReset}
            className="flex items-center gap-1.5 text-[11px] text-am-muted hover:text-am-ink transition-colors px-2.5 py-1.5 rounded-lg"
            style={{ border: '1px solid var(--color-am-border)' }}>
            <X size={11} /> Nova análise
          </button>
        </div>
        <ScoreBar valor={analise.score_geral} />
        {analise.texto_truncado && (
          <p className="text-[10px] text-am-muted mt-2">
            Apenas {analise.percentual_analisado}% do documento analisado (limite de tamanho).
          </p>
        )}
      </div>

      {/* Seções */}
      {[
        { title: 'Pontos fortes',        items: analise.pontos_fortes,         cor: '#1A9E78' },
        { title: 'Vulnerabilidades',      items: analise.vulnerabilidades,       cor: '#C83030' },
        { title: 'Argumentos ausentes',   items: analise.argumentos_ausentes,    cor: '#D08010' },
        { title: 'Precedentes relevantes',items: analise.precedentes_relevantes, cor: '#1248BE' },
        { title: 'Sugestões',             items: analise.sugestoes,              cor: '#7C4DFF' },
      ].filter(s => s.items.length > 0).map(({ title, items, cor }) => (
        <div key={title} className="bg-white rounded-2xl overflow-hidden" style={{ border: '1px solid var(--color-am-border)' }}>
          <div className="px-4 py-2.5 flex items-center gap-2" style={{ borderBottom: '1px solid var(--color-am-border)', background: 'rgba(12,30,48,0.02)' }}>
            <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: cor }} />
            <span className="text-[10px] font-bold uppercase tracking-wider text-am-secondary">{title}</span>
          </div>
          <ul className="px-4 py-3 space-y-2">
            {items.map((item, i) => (
              <li key={i} className="flex items-start gap-2 text-xs text-am-secondary leading-relaxed">
                <span className="font-bold flex-shrink-0 mt-0.5" style={{ color: cor }}>›</span>
                {item}
              </li>
            ))}
          </ul>
        </div>
      ))}

      <p className="text-[10px] text-am-muted text-center pb-2">
        {analise.tokens_input.toLocaleString()} tokens · custo estimado: {analise.custo_estimado}
      </p>
    </div>
  )
}

function AnalisePeticaoUpload({ onAnalise, loading, erro }: {
  onAnalise: (f: File) => void
  loading: boolean
  erro: string | null
}) {
  const [dragging, setDragging] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  return (
    <div className="flex-1 overflow-y-auto px-4 py-6 flex flex-col gap-4">
      <div className="text-center mb-2">
        <div className="w-12 h-12 rounded-2xl flex items-center justify-center mx-auto mb-3"
          style={{ background: 'linear-gradient(135deg,#1248BE,#4A8ED4)', boxShadow: '0 4px 16px rgba(18,72,190,0.25)' }}>
          <Scale size={22} className="text-white" />
        </div>
        <p className="text-sm font-semibold text-am-ink">Análise de Petição</p>
        <p className="text-xs text-am-muted mt-1">Envie um PDF — a IA identifica pontos fortes, vulnerabilidades e sugestões</p>
      </div>

      <button
        type="button"
        disabled={loading}
        onClick={() => fileRef.current?.click()}
        onDragOver={e => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={e => { e.preventDefault(); setDragging(false); const f = e.dataTransfer.files[0]; if (f) onAnalise(f) }}
        className="w-full rounded-2xl flex flex-col items-center gap-3 py-12 transition-all"
        style={{
          border: `2px dashed ${dragging ? 'var(--color-am-blue)' : 'rgba(18,72,190,0.25)'}`,
          background: dragging ? 'rgba(18,72,190,0.04)' : 'white',
          cursor: loading ? 'not-allowed' : 'pointer',
          opacity: loading ? 0.6 : 1,
        }}>
        {loading
          ? <><div className="w-8 h-8 rounded-full border-2 border-am-blue border-t-transparent animate-spin" /><p className="text-xs text-am-muted">Analisando com Claude Opus…</p></>
          : <><Upload size={20} style={{ color: 'var(--color-am-blue)' }} /><div className="text-center"><p className="text-sm font-semibold text-am-ink">Arraste o PDF aqui</p><p className="text-xs text-am-muted mt-1">ou clique para selecionar · máx. 10 MB</p></div></>
        }
      </button>
      <input ref={fileRef} type="file" accept=".pdf,application/pdf" className="hidden"
        onChange={e => { const f = e.target.files?.[0]; if (f) onAnalise(f); e.target.value = '' }} />

      {erro && (
        <div className="flex items-center gap-2 px-4 py-3 rounded-xl text-xs"
          style={{ background: 'rgba(200,48,48,0.06)', border: '1px solid rgba(200,48,48,0.18)', color: '#C83030' }}>
          <AlertTriangle size={13} className="flex-shrink-0" /> {erro}
        </div>
      )}

      <div className="rounded-2xl p-4 space-y-2" style={{ background: 'rgba(18,72,190,0.04)', border: '1px solid rgba(18,72,190,0.14)' }}>
        <p className="text-[10px] font-bold uppercase tracking-wider" style={{ color: 'var(--color-am-blue)' }}>O que a análise retorna</p>
        {['Pontos fortes da peça', 'Vulnerabilidades e brechas', 'Argumentos ausentes', 'Precedentes relevantes', 'Sugestões de melhoria', 'Score geral (0–100)'].map(item => (
          <p key={item} className="text-[11px] flex items-center gap-2" style={{ color: 'var(--color-am-blue)' }}>
            <span>›</span> {item}
          </p>
        ))}
      </div>
    </div>
  )
}

/* ── Painel de histórico ────────────────────────────────────────────────── */
function HistoricoPanel({ onClose, onRestaurar }: {
  onClose: () => void
  onRestaurar: (preview: string) => void
}) {
  const { data: sessoes, isLoading } = useQuery({
    queryKey: ['hub-historico'],
    queryFn: () => listarHistorico(1, 50),
    staleTime: 30_000,
  })

  function labelIntencao(intencao: string) {
    if (intencao === 'analise_peticao') return 'Petição'
    if (intencao === 'duvida_juridica') return 'Consulta'
    return intencao
  }

  return (
    <motion.div
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 20 }}
      className="absolute inset-0 flex flex-col bg-am-bg z-10">
      <div className="flex-shrink-0 flex items-center justify-between px-4 pt-5 pb-3">
        <div className="flex items-center gap-2">
          <Clock size={14} style={{ color: 'var(--color-am-blue)' }} />
          <span className="text-sm font-bold text-am-ink">Histórico</span>
        </div>
        <button onClick={onClose}
          className="w-8 h-8 rounded-xl flex items-center justify-center text-am-muted hover:text-am-ink transition-colors"
          style={{ border: '1px solid var(--color-am-border)', background: 'white' }}>
          <X size={13} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-4 pb-4 space-y-2">
        {isLoading && (
          <div className="flex items-center justify-center h-32">
            <div className="w-5 h-5 rounded-full border-2 border-am-blue border-t-transparent animate-spin" />
          </div>
        )}
        {!isLoading && (!sessoes || sessoes.length === 0) && (
          <div className="flex flex-col items-center justify-center h-32 gap-2 text-am-muted">
            <Clock size={20} strokeWidth={1.5} />
            <span className="text-xs">Nenhuma consulta ainda</span>
          </div>
        )}
        {sessoes?.map((s: SessaoListItem) => (
          <button key={s.id} onClick={() => onRestaurar(s.mensagem_preview)}
            className="w-full text-left px-4 py-3 rounded-2xl hover:bg-white transition-colors"
            style={{ border: '1px solid var(--color-am-border)', background: 'white', boxShadow: '0 1px 3px rgba(12,30,48,0.04)' }}>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-md"
                style={{ background: 'rgba(18,72,190,0.08)', color: 'var(--color-am-blue)' }}>
                {labelIntencao(s.intencao)}
              </span>
              <span className="text-[10px] text-am-muted">
                {new Date(s.created_at).toLocaleDateString('pt-BR', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}
              </span>
            </div>
            <p className="text-xs text-am-secondary truncate">{s.mensagem_preview}</p>
          </button>
        ))}
      </div>
    </motion.div>
  )
}

/* ── Página principal ────────────────────────────────────────────────────── */
export default function HubIAPage() {
  const [tool, setTool]               = useState<Tool>('chat')
  const [messages, setMessages]       = useState<ChatMessage[]>([{
    role: 'assistant',
    content: 'Olá! Sou a Dra. Camila, sua assistente jurídica. Como posso ajudar hoje?',
    intencao: 'saudacao',
  }])
  const [analise, setAnalise]         = useState<PeticaoAnalise | null>(null)
  const [analiseErro, setAnaliseErro] = useState<string | null>(null)
  const [showHistorico, setShowHistorico] = useState(false)
  const messagesRef = useRef<HTMLDivElement>(null)

  const chatMutation = useMutation({
    mutationFn: (pergunta: string) => consultar({ pergunta }),
    onSuccess: data => {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: data.resposta,
        intencao: INTENT_MAP[tool],
        tokens: data.tokens_output,
      }])
    },
  })

  const analiseMutation = useMutation({
    mutationFn: analisarPeticao,
    onSuccess: data => { setAnalise(data); setAnaliseErro(null) },
    onError: (e: unknown) => {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setAnaliseErro(msg ?? 'Erro ao analisar. Verifique se o PDF não está protegido.')
    },
  })

  useEffect(() => {
    const el = messagesRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages, chatMutation.isPending])

  const handleSend = useCallback((text: string) => {
    const t = text.trim()
    if (!t || chatMutation.isPending) return
    setMessages(prev => [...prev, { role: 'user', content: t }])
    chatMutation.mutate(t)
  }, [chatMutation])

  function resetChat() {
    setMessages([{ role: 'assistant', content: 'Nova conversa iniciada. Como posso ajudar?', intencao: 'saudacao' }])
  }

  function switchTool(t: Tool) {
    setTool(t)
    if (t !== 'peticao') resetChat()
    setAnalise(null)
    setAnaliseErro(null)
  }

  const isEmpty = messages.length === 1
  const prompts = tool !== 'peticao' ? QUICK_PROMPTS[tool] : []

  return (
    <div className="flex flex-col h-full overflow-hidden bg-am-bg">
      <div className="flex flex-col h-full w-full max-w-2xl mx-auto relative">

        {/* Tool switcher */}
        <div className="flex-shrink-0 flex items-center justify-between px-4 pt-5 pb-3">
          <div className="flex gap-1 p-1 rounded-2xl relative" style={{ background: 'rgba(12,30,48,0.05)' }}>
            {TOOLS.map(t => {
              const active = tool === t.id
              return (
                <motion.button key={t.id} onClick={() => switchTool(t.id)}
                  whileHover={{ scale: active ? 1 : 1.04 }} whileTap={{ scale: 0.95 }}
                  transition={{ type: 'spring', stiffness: 380, damping: 22 }}
                  className="relative flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold whitespace-nowrap z-10"
                  style={{ color: active ? 'var(--color-am-blue)' : 'var(--color-am-muted)' }}>
                  <AnimatePresence>
                    {active && (
                      <motion.span layoutId="tool-pill" className="absolute inset-0 rounded-xl"
                        style={{ background: 'white', boxShadow: '0 1px 6px rgba(18,72,190,0.15), 0 0 0 1px rgba(18,72,190,0.08)' }}
                        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                        transition={{ type: 'spring', stiffness: 400, damping: 28 }} />
                    )}
                  </AnimatePresence>
                  <span className="relative">{t.icon}</span>
                  <span className="relative">{t.label}</span>
                </motion.button>
              )
            })}
          </div>

          <div className="flex items-center gap-2">
            <button onClick={() => setShowHistorico(v => !v)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium transition-colors"
              style={{
                border: '1px solid var(--color-am-border)', background: 'white',
                color: showHistorico ? 'var(--color-am-blue)' : 'var(--color-am-muted)',
              }}>
              <Clock size={11} />
              Histórico
              {showHistorico ? <ChevronUp size={10} /> : <ChevronDown size={10} />}
            </button>
            {tool !== 'peticao' && (
              <button onClick={resetChat}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium text-am-muted hover:text-am-secondary transition-colors"
                style={{ border: '1px solid var(--color-am-border)', background: 'white' }}>
                <RotateCcw size={11} />
                Limpar
              </button>
            )}
          </div>
        </div>

        {/* Conteúdo central */}
        {tool === 'peticao' ? (
          analise
            ? <AnalisePeticaoResult analise={analise} onReset={() => { setAnalise(null); setAnaliseErro(null) }} />
            : <AnalisePeticaoUpload
                onAnalise={f => analiseMutation.mutate(f)}
                loading={analiseMutation.isPending}
                erro={analiseErro}
              />
        ) : (
          <>
            <div ref={messagesRef} className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
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
                    {prompts.map(p => (
                      <button key={p} onClick={() => handleSend(p)}
                        className="px-3 py-2.5 rounded-xl text-left text-xs text-am-secondary font-medium bg-white border border-am-border hover:border-am-blue hover:text-am-ink transition-all duration-200 leading-relaxed"
                        style={{ boxShadow: '0 1px 4px rgba(12,30,48,0.05)' }}>
                        {p}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {!isEmpty && messages.map((msg, i) => <MessageBubble key={i} msg={msg} />)}
              {chatMutation.isPending && <TypingIndicator />}
              {chatMutation.isError && (
                <div className="flex items-center gap-2 px-3 py-2.5 rounded-xl text-xs"
                  style={{ background: 'rgba(200,48,48,0.06)', border: '1px solid rgba(200,48,48,0.18)', color: '#C83030' }}>
                  <AlertTriangle size={12} />
                  Erro ao enviar. Verifique a conexão e tente novamente.
                </div>
              )}
            </div>

            <div className="flex-shrink-0 px-4 pb-5 pt-2">
              <PlaceholdersAndVanishInput
                placeholders={prompts}
                onSubmit={handleSend}
                disabled={chatMutation.isPending}
              />
              <p className="text-center text-[10px] text-am-muted mt-2">
                Amicus IA pode cometer erros. Verifique informações importantes.
              </p>
            </div>
          </>
        )}

        {/* Histórico overlay */}
        <AnimatePresence>
          {showHistorico && (
            <HistoricoPanel
              onClose={() => setShowHistorico(false)}
              onRestaurar={preview => {
                setShowHistorico(false)
                if (tool === 'peticao') switchTool('chat')
                handleSend(preview)
              }}
            />
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}
