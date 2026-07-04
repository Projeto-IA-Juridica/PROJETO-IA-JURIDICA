import { useState, useRef, useEffect, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Sparkles, Scale, FileSearch, AlertTriangle, RotateCcw,
  Upload, X, MessageSquare, Plus, Clock, CheckCircle2, Circle,
} from 'lucide-react'
import {
  consultar, analisarPeticaoAsync, pollHubJob,
  fetchConversas, fetchConversa,
  type PeticaoAnalise, type ConversaListItem, type ConversaMensagem,
} from '../api/hub'
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

/* ── Utilitários de data ────────────────────────────────────────────────── */

function labelDataGrupo(iso: string): string {
  const d = new Date(iso)
  const hoje = new Date()
  const diff = Math.floor((hoje.getTime() - d.getTime()) / 86_400_000)
  if (diff === 0) return 'Hoje'
  if (diff === 1) return 'Ontem'
  if (diff <= 7) return 'Últimos 7 dias'
  if (diff <= 30) return 'Últimos 30 dias'
  return d.toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' })
}

function agruparPorData(conversas: ConversaListItem[]) {
  const grupos: Record<string, ConversaListItem[]> = {}
  for (const c of conversas) {
    const label = labelDataGrupo(c.ultima_mensagem_em)
    if (!grupos[label]) grupos[label] = []
    grupos[label].push(c)
  }
  return grupos
}

/* ── MessageBubble ─────────────────────────────────────────────────────── */
function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === 'user'
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.22, ease: 'easeOut' }}
      className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
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
    </motion.div>
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
    <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
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

      {[
        { title: 'Pontos fortes',         items: analise.pontos_fortes,          cor: '#1A9E78' },
        { title: 'Vulnerabilidades',       items: analise.vulnerabilidades,        cor: '#C83030' },
        { title: 'Argumentos ausentes',    items: analise.argumentos_ausentes,     cor: '#D08010' },
        { title: 'Precedentes relevantes', items: analise.precedentes_relevantes,  cor: '#1248BE' },
        { title: 'Sugestões',              items: analise.sugestoes,               cor: '#7C4DFF' },
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

/* ── Loading da análise de petição ───────────────────────────────────────
 * A análise no Opus leva de 15 a 60s — sem feedback de progresso, o usuário
 * não tem como distinguir "processando" de "travado". As etapas abaixo não
 * refletem progresso real do backend (ele não expõe granularidade), são só
 * uma progressão por tempo decorrido para comunicar atividade contínua.
 */
const PETICAO_ETAPAS = [
  { label: 'Lendo o documento e extraindo o conteúdo', apos: 0 },
  { label: 'Identificando pontos fortes e vulnerabilidades', apos: 5 },
  { label: 'Cruzando com jurisprudência relevante', apos: 15 },
  { label: 'Calculando score e finalizando sugestões', apos: 30 },
]

function AnalisePeticaoLoading() {
  const [segundos, setSegundos] = useState(0)

  useEffect(() => {
    const id = setInterval(() => setSegundos(s => s + 1), 1000)
    return () => clearInterval(id)
  }, [])

  const etapaAtual = PETICAO_ETAPAS.reduce(
    (acc, etapa, i) => (segundos >= etapa.apos ? i : acc), 0,
  )
  // Progresso "fake" que desacelera exponencialmente e nunca fecha em 100% —
  // só o resultado real (ou erro) chegando encerra o loading de verdade.
  const progresso = Math.min(92, Math.round((1 - Math.exp(-segundos / 18)) * 92))

  return (
    <div className="w-full flex flex-col items-center gap-5 py-8">
      <motion.div
        animate={{ rotate: [0, 10, -10, 0] }}
        transition={{ duration: 2.4, repeat: Infinity, ease: 'easeInOut' }}
        className="w-14 h-14 rounded-2xl flex items-center justify-center flex-shrink-0"
        style={{ background: 'linear-gradient(135deg,#1248BE,#4A8ED4)', boxShadow: '0 6px 20px rgba(18,72,190,0.3)' }}>
        <Scale size={24} className="text-white" />
      </motion.div>

      <div className="w-full max-w-[15rem] h-1.5 rounded-full overflow-hidden" style={{ background: 'rgba(18,72,190,0.1)' }}>
        <motion.div
          className="h-full rounded-full"
          style={{ background: 'linear-gradient(90deg,#1248BE,#4A8ED4)' }}
          animate={{ width: `${progresso}%` }}
          transition={{ duration: 0.6, ease: 'easeOut' }}
        />
      </div>

      <div className="flex flex-col gap-2.5 w-full max-w-[15rem]">
        {PETICAO_ETAPAS.map((etapa, i) => {
          const concluida = i < etapaAtual
          const ativa = i === etapaAtual
          return (
            <div key={etapa.label} className="flex items-center gap-2.5">
              {concluida ? (
                <CheckCircle2 size={14} style={{ color: '#1A9E78' }} className="flex-shrink-0" />
              ) : ativa ? (
                <div className="w-3.5 h-3.5 rounded-full border-2 border-am-blue border-t-transparent animate-spin flex-shrink-0" />
              ) : (
                <Circle size={14} className="text-am-border flex-shrink-0" />
              )}
              <span className={`text-xs text-left ${ativa ? 'text-am-ink font-semibold' : 'text-am-muted'}`}>
                {etapa.label}
              </span>
            </div>
          )
        })}
      </div>

      <p className="text-[11px] text-am-muted">
        Analisando com Claude Opus · {segundos}s
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
        }}>
        {loading
          ? <AnalisePeticaoLoading />
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

/* ── Drawer de histórico de conversas ──────────────────────────────────── */

function ConversasDrawer({ onClose, onSelectConversa, onNovaConversa }: {
  onClose: () => void
  onSelectConversa: (conversaId: string) => void
  onNovaConversa: () => void
}) {
  const { data: conversas, isLoading } = useQuery({
    queryKey: ['hub-conversas'],
    queryFn: () => fetchConversas(1, 50),
    staleTime: 30_000,
  })

  const grupos = conversas ? agruparPorData(conversas) : {}
  const grupoKeys = Object.keys(grupos)

  return (
    <motion.div
      initial={{ opacity: 0, x: -24 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -24 }}
      transition={{ type: 'spring', stiffness: 420, damping: 32 }}
      className="absolute inset-0 flex flex-col z-10"
      style={{ background: 'var(--color-am-bg)' }}>

      {/* Header */}
      <div className="flex-shrink-0 flex items-center justify-between px-4 pt-5 pb-3">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-lg flex items-center justify-center"
            style={{ background: 'rgba(18,72,190,0.1)' }}>
            <MessageSquare size={12} style={{ color: 'var(--color-am-blue)' }} />
          </div>
          <span className="text-sm font-bold text-am-ink">Histórico</span>
        </div>
        <motion.button
          onClick={onClose}
          aria-label="Fechar histórico"
          whileHover={{ scale: 1.1, rotate: 90 }}
          whileTap={{ scale: 0.88 }}
          transition={{ type: 'spring', stiffness: 400, damping: 20 }}
          className="w-8 h-8 rounded-xl flex items-center justify-center text-am-muted hover:text-am-ink transition-colors"
          style={{ border: '1px solid var(--color-am-border)', background: 'white' }}>
          <X size={13} />
        </motion.button>
      </div>

      {/* Nova conversa */}
      <div className="flex-shrink-0 px-6 pb-3">
        <motion.button
          onClick={() => { onNovaConversa(); onClose() }}
          whileHover={{ scale: 1.02, boxShadow: '0 6px 20px rgba(18,72,190,0.35)' }}
          whileTap={{ scale: 0.97 }}
          transition={{ type: 'spring', stiffness: 400, damping: 22 }}
          className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl text-xs font-bold text-white"
          style={{ background: 'linear-gradient(135deg,#1248BE,#3A7AB8)', boxShadow: '0 3px 12px rgba(18,72,190,0.25)' }}>
          <Plus size={13} />
          Nova conversa
        </motion.button>
      </div>

      {/* Lista de conversas */}
      <div className="flex-1 overflow-y-auto px-4 pb-4 space-y-4">
        {isLoading && (
          <div className="flex items-center justify-center h-32">
            <div className="w-5 h-5 rounded-full border-2 border-am-blue border-t-transparent animate-spin" />
          </div>
        )}

        {!isLoading && grupoKeys.length === 0 && (
          <div className="flex flex-col items-center justify-center h-40 gap-3">
            <div className="w-10 h-10 rounded-2xl flex items-center justify-center"
              style={{ background: 'rgba(12,30,48,0.05)' }}>
              <MessageSquare size={18} strokeWidth={1.5} className="text-am-muted" />
            </div>
            <div className="text-center">
              <p className="text-xs font-semibold text-am-secondary">Nenhuma conversa ainda</p>
              <p className="text-[11px] text-am-muted mt-0.5">Suas conversas aparecerão aqui</p>
            </div>
          </div>
        )}

        {grupoKeys.map(grupo => (
          <div key={grupo}>
            <p className="text-[10px] font-bold uppercase tracking-wider text-am-muted mb-2 px-1">
              {grupo}
            </p>
            <div className="space-y-1.5">
              {grupos[grupo].map((c: ConversaListItem) => (
                <motion.button
                  key={c.conversa_id}
                  onClick={() => onSelectConversa(c.conversa_id)}
                  whileHover={{ x: 3, borderColor: 'rgba(18,72,190,0.25)', backgroundColor: 'rgba(18,72,190,0.03)' }}
                  whileTap={{ scale: 0.985 }}
                  transition={{ type: 'spring', stiffness: 420, damping: 28 }}
                  className="w-full text-left px-3.5 py-3 rounded-xl group"
                  style={{ border: '1px solid var(--color-am-border)', background: 'white', boxShadow: '0 1px 3px rgba(12,30,48,0.04)' }}>
                  <div className="flex items-start gap-2">
                    <MessageSquare size={12} className="flex-shrink-0 mt-0.5 text-am-muted group-hover:text-am-blue transition-colors duration-150" />
                    <div className="flex-1 min-w-0">
                      <p className="text-xs text-am-ink leading-snug line-clamp-2 font-medium group-hover:text-am-blue transition-colors duration-150">{c.titulo}</p>
                      <div className="flex items-center gap-2 mt-1">
                        <span className="text-[10px] text-am-muted">
                          {new Date(c.ultima_mensagem_em).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}
                        </span>
                        <span className="text-[10px] text-am-muted">·</span>
                        <span className="text-[10px] text-am-muted">
                          {c.total_mensagens} {c.total_mensagens === 1 ? 'troca' : 'trocas'}
                        </span>
                      </div>
                    </div>
                  </div>
                </motion.button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </motion.div>
  )
}

/* ── Banner de conversa restaurada ──────────────────────────────────────── */
function ConversaRestauradaBanner({ onContinuar, onNova }: {
  onContinuar: () => void
  onNova: () => void
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ type: 'spring', stiffness: 400, damping: 28 }}
      className="flex-shrink-0 flex items-center gap-2 px-4 py-2.5"
      style={{ background: 'rgba(18,72,190,0.05)', borderBottom: '1px solid rgba(18,72,190,0.12)' }}>
      <div className="w-4 h-4 rounded-md flex items-center justify-center flex-shrink-0"
        style={{ background: 'rgba(18,72,190,0.12)' }}>
        <Clock size={9} style={{ color: 'var(--color-am-blue)' }} />
      </div>
      <span className="text-[11px] text-am-secondary flex-1">Conversa anterior restaurada</span>
      <motion.button
        onClick={onContinuar}
        whileHover={{ scale: 1.06 }}
        whileTap={{ scale: 0.94 }}
        transition={{ type: 'spring', stiffness: 400, damping: 22 }}
        className="text-[11px] font-bold px-2.5 py-1 rounded-lg transition-colors"
        style={{ color: 'var(--color-am-blue)', background: 'rgba(18,72,190,0.1)' }}>
        Continuar
      </motion.button>
      <motion.button
        onClick={onNova}
        whileHover={{ scale: 1.06 }}
        whileTap={{ scale: 0.94 }}
        transition={{ type: 'spring', stiffness: 400, damping: 22 }}
        className="text-[11px] font-semibold px-2.5 py-1 rounded-lg text-am-muted hover:text-am-secondary transition-colors"
        style={{ background: 'rgba(12,30,48,0.05)' }}>
        Nova
      </motion.button>
    </motion.div>
  )
}

/* ── Página principal ────────────────────────────────────────────────────── */

const MSG_INICIAL: ChatMessage = {
  role: 'assistant',
  content: 'Olá! Sou a Dra. Camila, sua assistente jurídica. Como posso ajudar hoje?',
  intencao: 'saudacao',
}

export default function HubIAPage() {
  const queryClient = useQueryClient()

  const [tool, setTool]                 = useState<Tool>('chat')
  const [messages, setMessages]         = useState<ChatMessage[]>([MSG_INICIAL])
  const [analise, setAnalise]           = useState<PeticaoAnalise | null>(null)
  const [analiseErro, setAnaliseErro]   = useState<string | null>(null)
  const [peticaoJobId, setPeticaoJobId] = useState<string | null>(null)
  const [showHistorico, setShowHistorico] = useState(false)
  const [conversaId, setConversaId]     = useState<string>(() => crypto.randomUUID())
  const [conversaRestaurada, setConversaRestaurada] = useState(false)

  const messagesRef = useRef<HTMLDivElement>(null)

  /* ── Enviar mensagem ── */
  const chatMutation = useMutation({
    mutationFn: (pergunta: string) => consultar({ pergunta, conversa_id: conversaId }),
    onSuccess: data => {
      if (data.conversa_id) setConversaId(data.conversa_id)
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: data.resposta,
        intencao: INTENT_MAP[tool],
        tokens: data.tokens_output,
      }])
      // Invalida a lista de conversas para refletir a nova mensagem
      queryClient.invalidateQueries({ queryKey: ['hub-conversas'] })
    },
  })

  /* ── Carregar conversa histórica ── */
  const carregarConversaMut = useMutation({
    mutationFn: fetchConversa,
    onSuccess: (mensagens: ConversaMensagem[], loadedId: string) => {
      const msgs: ChatMessage[] = mensagens.flatMap(m => [
        { role: 'user' as const,      content: m.mensagem_advogado },
        { role: 'assistant' as const, content: m.resposta_hub, tokens: m.tokens_output },
      ])
      setMessages(msgs)
      setConversaId(loadedId)
      setConversaRestaurada(true)
      setTool('chat')
      setAnalise(null)
      setAnaliseErro(null)
    },
  })

  /* ── Petição ── */
  const submitPeticaoMut = useMutation({
    mutationFn: analisarPeticaoAsync,
    onSuccess: ({ job_id }) => { setPeticaoJobId(job_id); setAnaliseErro(null) },
    onError: (e: unknown) => {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setAnaliseErro(msg ?? 'Erro ao enviar. Verifique se o PDF não está protegido.')
    },
  })

  const { data: jobStatus } = useQuery({
    queryKey: ['hub-job', peticaoJobId],
    queryFn: () => pollHubJob(peticaoJobId!),
    enabled: peticaoJobId !== null,
    // Continua tentando enquanto não houver um status terminal — inclusive
    // quando a última tentativa falhou (ex: 404 transitório), em vez de exigir
    // status === 'processando', que fica indefinido se algum fetch falhar antes
    // de qualquer resposta bem-sucedida chegar a existir.
    refetchInterval: (query) => {
      const st = query.state.data?.status
      return st === 'concluido' || st === 'erro' ? false : 2000
    },
  })

  useEffect(() => {
    if (jobStatus?.status === 'concluido' && jobStatus.resultado) {
      setAnalise(jobStatus.resultado)
      setAnaliseErro(null)
      setPeticaoJobId(null)
    } else if (jobStatus?.status === 'erro') {
      setAnaliseErro(jobStatus.erro ?? 'Erro ao analisar. Tente novamente.')
      setPeticaoJobId(null)
    }
  }, [jobStatus])

  useEffect(() => {
    const el = messagesRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages, chatMutation.isPending])

  /* ── Ações ── */
  const handleSend = useCallback((text: string) => {
    const t = text.trim()
    if (!t || chatMutation.isPending) return
    setMessages(prev => [...prev, { role: 'user', content: t }])
    chatMutation.mutate(t)
  }, [chatMutation])

  function novaConversa() {
    setMessages([{
      role: 'assistant',
      content: 'Nova conversa iniciada. Como posso ajudar?',
      intencao: 'saudacao',
    }])
    setConversaId(crypto.randomUUID())
    setConversaRestaurada(false)
  }

  function resetChat() {
    novaConversa()
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
      <div className="flex flex-col h-full w-full max-w-3xl mx-auto relative">

        {/* Tool switcher */}
        <div className="flex-shrink-0 flex items-center justify-between px-6 pt-5 pb-4">
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
            <motion.button
              onClick={() => setShowHistorico(v => !v)}
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.93 }}
              transition={{ type: 'spring', stiffness: 420, damping: 22 }}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium transition-all duration-200"
              style={{
                border: `1px solid ${showHistorico ? 'rgba(18,72,190,0.35)' : 'var(--color-am-border)'}`,
                background: showHistorico ? 'rgba(18,72,190,0.08)' : 'white',
                color: showHistorico ? 'var(--color-am-blue)' : 'var(--color-am-muted)',
                boxShadow: showHistorico ? '0 0 0 3px rgba(18,72,190,0.1)' : 'none',
              }}>
              <MessageSquare size={11} />
              Histórico
            </motion.button>
            {tool !== 'peticao' && (
              <motion.button
                onClick={resetChat}
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.93 }}
                transition={{ type: 'spring', stiffness: 420, damping: 22 }}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium text-am-muted transition-all duration-200 hover:text-red-400"
                style={{ border: '1px solid var(--color-am-border)', background: 'white' }}>
                <RotateCcw size={11} />
                Limpar
              </motion.button>
            )}
          </div>
        </div>

        {/* Banner de conversa restaurada */}
        <AnimatePresence>
          {conversaRestaurada && tool !== 'peticao' && (
            <ConversaRestauradaBanner
              onContinuar={() => setConversaRestaurada(false)}
              onNova={() => { novaConversa() }}
            />
          )}
        </AnimatePresence>

        {/* Conteúdo central */}
        {tool === 'peticao' ? (
          analise
            ? <AnalisePeticaoResult analise={analise} onReset={() => { setAnalise(null); setAnaliseErro(null); setPeticaoJobId(null) }} />
            : <AnalisePeticaoUpload
                onAnalise={f => submitPeticaoMut.mutate(f)}
                loading={submitPeticaoMut.isPending || (peticaoJobId !== null && jobStatus?.status === 'processando')}
                erro={analiseErro}
              />
        ) : (
          <>
            <div ref={messagesRef} className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
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
                      <motion.button
                        key={p}
                        onClick={() => handleSend(p)}
                        whileHover={{ y: -2, boxShadow: '0 6px 16px rgba(12,30,48,0.1)', borderColor: 'rgba(18,72,190,0.35)' }}
                        whileTap={{ scale: 0.97, y: 0 }}
                        transition={{ type: 'spring', stiffness: 400, damping: 24 }}
                        className="px-3 py-2.5 rounded-xl text-left text-xs text-am-secondary font-medium bg-white border border-am-border hover:text-am-ink leading-relaxed"
                        style={{ boxShadow: '0 1px 4px rgba(12,30,48,0.05)' }}>
                        {p}
                      </motion.button>
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
              {carregarConversaMut.isPending && (
                <div className="flex items-center justify-center gap-2 py-4 text-xs text-am-muted">
                  <div className="w-4 h-4 rounded-full border-2 border-am-blue border-t-transparent animate-spin" />
                  Carregando conversa…
                </div>
              )}
            </div>

            <div className="flex-shrink-0 px-6 pb-5 pt-2">
              <PlaceholdersAndVanishInput
                placeholders={prompts}
                onSubmit={handleSend}
                disabled={chatMutation.isPending || carregarConversaMut.isPending}
              />
              <p className="text-center text-[10px] text-am-muted mt-2">
                Amicus IA pode cometer erros. Verifique informações importantes.
              </p>
            </div>
          </>
        )}

        {/* Drawer de histórico */}
        <AnimatePresence>
          {showHistorico && (
            <ConversasDrawer
              onClose={() => setShowHistorico(false)}
              onSelectConversa={(id) => {
                setShowHistorico(false)
                carregarConversaMut.mutate(id)
              }}
              onNovaConversa={novaConversa}
            />
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}
