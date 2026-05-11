import { useState, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  FolderOpen, Upload, FileText, CheckCircle, Database,
  Trash2, Search, ChevronDown, ChevronUp,
  Sparkles, BookOpen, Scale, AlertTriangle,
} from 'lucide-react'

/* ── Tipos ── */
interface Doc {
  id: number
  titulo: string
  tipo: keyof typeof TIPO_CFG
  chunks: number
  tamanho?: string
  adicionado_em: string
}

const TIPO_CFG = {
  jurisprudencia: { label: 'Jurisprudência', color: '#D08010', dot: '🟡' },
  tese:           { label: 'Tese / Argumento', color: '#1248BE', dot: '🟠' },
  sentenca:       { label: 'Sentença',        color: '#1A9E78', dot: '🟢' },
  parecer:        { label: 'Parecer / FAQ',   color: '#7C4DFF', dot: '🟣' },
  peticao:        { label: 'Petição',         color: '#2D6FD4', dot: '🔵' },
} as const

const INITIAL_DOCS: Doc[] = [
  { id: 1, titulo: 'Tese — Danos Morais por Falha na Prestação de Serviços', tipo: 'tese',           chunks: 8,  tamanho: '142 KB', adicionado_em: '2026-05-01' },
  { id: 2, titulo: 'Jurisprudência STJ 2023 — Responsabilidade Civil',        tipo: 'jurisprudencia', chunks: 12, tamanho: '287 KB', adicionado_em: '2026-05-02' },
  { id: 3, titulo: 'Petição Modelo — Indenização ao Consumidor',              tipo: 'peticao',        chunks: 6,  tamanho: '98 KB',  adicionado_em: '2026-05-03' },
  { id: 4, titulo: 'Súmulas STJ — Direito do Consumidor Compiladas',         tipo: 'jurisprudencia', chunks: 15, tamanho: '320 KB', adicionado_em: '2026-05-05' },
]

/* ── Componentes auxiliares ── */
function Card({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`bg-white rounded-2xl card-shadow card-border-hover ${className}`}
      style={{ border: '1px solid var(--color-am-border)' }}>
      {children}
    </div>
  )
}

function CardHeader({ icon, title, badge }: { icon: React.ReactNode; title: string; badge?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between px-4 py-3"
      style={{ borderBottom: '1px solid var(--color-am-border)', background: 'rgba(12,30,48,0.02)' }}>
      <div className="flex items-center gap-2">
        <span className="text-am-blue">{icon}</span>
        <span className="text-[10px] font-bold uppercase tracking-wider text-am-secondary">{title}</span>
      </div>
      {badge}
    </div>
  )
}

function TipoBadge({ tipo }: { tipo: keyof typeof TIPO_CFG }) {
  const cfg = TIPO_CFG[tipo]
  return (
    <span className="text-[9px] font-bold px-1.5 py-px rounded-md"
      style={{ color: cfg.color, background: `${cfg.color}14`, border: `1px solid ${cfg.color}28` }}>
      {cfg.label}
    </span>
  )
}

function Collapsible({ title, icon, defaultOpen = false, children }: {
  title: string; icon: React.ReactNode; defaultOpen?: boolean; children: React.ReactNode
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <Card>
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-black/[0.01] transition-colors"
        style={{ borderBottom: open ? '1px solid var(--color-am-border)' : 'none' }}
      >
        <div className="flex items-center gap-2">
          <span className="text-am-blue">{icon}</span>
          <span className="text-[10px] font-bold uppercase tracking-wider text-am-secondary">{title}</span>
        </div>
        {open ? <ChevronUp size={14} className="text-am-muted" /> : <ChevronDown size={14} className="text-am-muted" />}
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.22, ease: 'easeInOut' }}
            style={{ overflow: 'hidden' }}
          >
            {children}
          </motion.div>
        )}
      </AnimatePresence>
    </Card>
  )
}

export default function DocumentosPage() {
  const [docs, setDocs]         = useState<Doc[]>(INITIAL_DOCS)
  const [dragging, setDragging] = useState(false)
  const [uploaded, setUploaded] = useState<number[]>([])
  const [search, setSearch]     = useState('')
  const inputRef                = useRef<HTMLInputElement>(null)

  const totalChunks = docs.reduce((a, d) => a + d.chunks, 0)

  const filtered = docs.filter((d) =>
    d.titulo.toLowerCase().includes(search.toLowerCase())
  )

  function handleFiles(files: FileList | null) {
    if (!files) return
    Array.from(files).forEach((f) => {
      if (f.type !== 'application/pdf' && !f.name.endsWith('.txt')) return
      const id = Date.now() + Math.random()
      const doc: Doc = {
        id,
        titulo:        f.name.replace(/\.[^.]+$/, ''),
        tipo:          'peticao',
        chunks:        Math.floor(Math.random() * 10) + 3,
        tamanho:       `${Math.round(f.size / 1024)} KB`,
        adicionado_em: new Date().toISOString().split('T')[0],
      }
      setDocs((prev) => [doc, ...prev])
      setUploaded((prev) => [...prev, id])
      setTimeout(() => setUploaded((prev) => prev.filter((n) => n !== id)), 3000)
    })
  }

  function fmt(iso: string) {
    return new Date(iso).toLocaleDateString('pt-BR', { day: '2-digit', month: 'short', year: '2-digit' })
  }

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="p-4 max-w-3xl mx-auto space-y-4 page-enter">

        {/* ── Header ── */}
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-2xl flex items-center justify-center flex-shrink-0"
            style={{ background: 'linear-gradient(135deg,#1248BE,#4A8ED4)', boxShadow: '0 4px 12px rgba(18,72,190,0.22)' }}>
            <FolderOpen size={16} className="text-white" />
          </div>
          <div>
            <h2 className="text-sm font-extrabold text-am-ink tracking-tight">Base de Documentos</h2>
            <p className="text-[11px] text-am-muted mt-0.5">Personalize a IA com o conhecimento do seu escritório</p>
          </div>
        </div>

        {/* ── Stats ── */}
        <div className="grid grid-cols-3 gap-3">
          {[
            { val: docs.length,  label: 'Documentos',       color: '#1248BE' },
            { val: totalChunks,  label: 'Trechos indexados', color: '#1A9E78' },
            { val: Object.keys(TIPO_CFG).length, label: 'Categorias', color: '#7C4DFF' },
          ].map(({ val, label, color }, i) => (
            <motion.div key={label}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.25, delay: i * 0.05, ease: [0.34, 1.1, 0.64, 1] }}
              className="bg-white rounded-2xl card-shadow card-border-hover py-4 flex flex-col items-center gap-1.5"
              style={{ border: '1px solid var(--color-am-border)' }}>
              <span className="text-2xl font-extrabold leading-none" style={{ color }}>{val}</span>
              <span className="text-[9px] font-semibold text-am-muted text-center px-2">{label}</span>
            </motion.div>
          ))}
        </div>

        {/* ── Como funciona ── */}
        <Collapsible title="Como a IA usa os documentos" icon={<Sparkles size={13} />} defaultOpen>
          <div className="px-4 py-4 space-y-3">
            <p className="text-xs text-am-secondary leading-relaxed">
              Quando o advogado ou cliente faz uma pergunta, a IA segue três passos com os documentos do escritório:
            </p>
            <div className="space-y-2">
              {[
                { step: '1', title: 'Identifica',  desc: 'Quais documentos do seu escritório são relevantes para aquela pergunta' },
                { step: '2', title: 'Lê',           desc: 'Os trechos mais pertinentes automaticamente, sem precisar abrir o arquivo' },
                { step: '3', title: 'Responde',     desc: 'Usando o raciocínio e a linguagem desses documentos — soando como você' },
              ].map(({ step, title, desc }) => (
                <div key={step} className="flex items-start gap-3">
                  <div className="w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-extrabold text-white flex-shrink-0 mt-0.5"
                    style={{ background: 'linear-gradient(135deg,#1248BE,#4A8ED4)' }}>
                    {step}
                  </div>
                  <div>
                    <span className="text-xs font-bold text-am-ink">{title} </span>
                    <span className="text-xs text-am-secondary">{desc}</span>
                  </div>
                </div>
              ))}
            </div>
            <p className="text-[11px] text-am-muted pt-1" style={{ borderTop: '1px solid var(--color-am-border)' }}>
              Quanto mais documentos do seu escritório você enviar, mais a IA vai soar como <strong>você</strong>.
            </p>
          </div>
        </Collapsible>

        {/* ── O que enviar ── */}
        <Collapsible title="O que enviar para a IA aprender" icon={<BookOpen size={13} />}>
          <div className="px-4 py-4 space-y-5">

            <p className="text-xs text-am-secondary leading-relaxed">
              A IA identifica automaticamente a área jurídica do processo e busca os documentos mais relevantes.
              Quanto mais focados forem os documentos, melhor ela responde.
            </p>

            {/* Por tipo */}
            <div>
              <p className="text-[10px] font-bold uppercase tracking-wider text-am-muted mb-3">Por tipo de documento</p>
              <div className="space-y-2.5">
                {[
                  {
                    tipo: 'jurisprudencia' as const,
                    impacto: 'Maior impacto',
                    impactoCor: '#D08010',
                    items: ['Acórdãos do TJSP/TRT/STJ da sua área de atuação', 'Súmulas aplicáveis aos seus casos', 'Decisões similares aos processos dos seus clientes'],
                  },
                  {
                    tipo: 'tese' as const,
                    impacto: '2º maior impacto',
                    impactoCor: '#1248BE',
                    items: ['Os argumentos que você usa nas suas petições', 'Pontos fortes e fracos de cada tipo de ação', 'Estratégias que funcionam bem no tribunal'],
                  },
                  {
                    tipo: 'sentenca' as const,
                    impacto: 'Contexto processual',
                    impactoCor: '#1A9E78',
                    items: ['Sentenças em casos similares (anonimizadas)', 'Como os juízes da sua comarca costumam fundamentar', 'Decisões interlocutórias frequentes no tribunal'],
                  },
                  {
                    tipo: 'parecer' as const,
                    impacto: 'Respostas prontas',
                    impactoCor: '#7C4DFF',
                    items: ['Perguntas frequentes dos clientes respondidas', 'O que acontece em cada fase do processo', 'Explicações que você dá no dia a dia'],
                  },
                  {
                    tipo: 'peticao' as const,
                    impacto: 'Linguagem do escritório',
                    impactoCor: '#2D6FD4',
                    items: ['Petições iniciais com os seus argumentos', 'Contestações nas suas áreas principais'],
                  },
                ].map(({ tipo, impacto, impactoCor, items }) => {
                  const cfg = TIPO_CFG[tipo]
                  return (
                    <div key={tipo} className="rounded-xl p-3"
                      style={{ background: `${cfg.color}07`, border: `1px solid ${cfg.color}18` }}>
                      <div className="flex items-center gap-2 mb-2">
                        <TipoBadge tipo={tipo} />
                        <span className="text-[10px] font-semibold" style={{ color: impactoCor }}>
                          {impacto}
                        </span>
                      </div>
                      <ul className="space-y-0.5">
                        {items.map((item) => (
                          <li key={item} className="flex items-start gap-1.5 text-[11px] text-am-secondary">
                            <span className="mt-0.5 flex-shrink-0" style={{ color: cfg.color }}>›</span>
                            {item}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )
                })}
              </div>
            </div>

            {/* Por área */}
            <div>
              <p className="text-[10px] font-bold uppercase tracking-wider text-am-muted mb-3">Por área de atuação</p>
              <div className="grid grid-cols-1 gap-2">
                {[
                  { area: 'Trabalhista',       icon: '⚖️',  dica: 'Súmulas do TST · Teses de rescisão indireta e dano moral' },
                  { area: 'Cível / Indeniz.',  icon: '🏛️',  dica: 'Acórdãos do TJSP por comarca · Como a vara calcula danos morais' },
                  { area: 'Previdenciário',    icon: '📋',  dica: 'Jurisprudência do TRF · Teses por tipo de benefício' },
                  { area: 'Família',           icon: '👨‍👩‍👧',  dica: 'Jurisprudência sobre pensão e guarda · FAQ de procedimentos' },
                  { area: 'Consumidor',        icon: '🛒',  dica: 'Súmulas do STJ aplicadas · Decisões da sua região' },
                ].map(({ area, icon, dica }) => (
                  <div key={area} className="flex items-start gap-2.5 px-3 py-2.5 rounded-xl"
                    style={{ background: 'rgba(12,30,48,0.03)', border: '1px solid var(--color-am-border)' }}>
                    <span className="text-sm flex-shrink-0">{icon}</span>
                    <div>
                      <p className="text-[11px] font-bold text-am-ink">{area}</p>
                      <p className="text-[11px] text-am-muted">{dica}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Tamanho ideal */}
            <div className="px-3 py-3 rounded-xl"
              style={{ background: 'rgba(18,72,190,0.04)', border: '1px solid rgba(18,72,190,0.14)' }}>
              <p className="text-[11px] font-bold text-am-blue mb-1">Tamanho ideal</p>
              <p className="text-[11px] text-am-secondary leading-relaxed">
                Documentos entre <strong>1 e 10 páginas</strong> funcionam melhor.
                Para sentenças longas (+40 páginas): envie apenas os <strong>fundamentos da decisão</strong> (3–5 páginas).
              </p>
            </div>

            {/* O que NÃO enviar */}
            <div>
              <p className="text-[10px] font-bold uppercase tracking-wider text-am-muted mb-2">O que não enviar</p>
              <div className="rounded-xl overflow-hidden"
                style={{ border: '1px solid rgba(200,48,48,0.18)', background: 'rgba(200,48,48,0.04)' }}>
                <div className="flex items-center gap-2 px-3 py-2" style={{ borderBottom: '1px solid rgba(200,48,48,0.12)' }}>
                  <AlertTriangle size={12} style={{ color: '#C83030' }} />
                  <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: '#C83030' }}>Evite estes tipos</span>
                </div>
                <ul className="px-3 py-3 space-y-1.5">
                  {[
                    'Documentos com CPF, RG ou dados pessoais — anonimize antes de enviar',
                    'Artigos genéricos da internet sem aplicação prática',
                    'Texto puro de lei — a IA já conhece a legislação; envie a aplicação dela nos seus casos',
                    'Jurisprudências com mais de 5 anos sem revisão — o entendimento muda',
                  ].map((item) => (
                    <li key={item} className="flex items-start gap-1.5 text-[11px] text-am-secondary">
                      <span className="flex-shrink-0 font-bold" style={{ color: '#C83030' }}>✕</span>
                      {item}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </Collapsible>

        {/* ── Upload ── */}
        <div
          className="relative rounded-2xl border-2 border-dashed p-6 text-center transition-fast cursor-pointer"
          style={{
            borderColor: dragging ? 'var(--color-am-blue)' : 'rgba(18,72,190,0.25)',
            background:  dragging ? 'rgba(18,72,190,0.05)' : 'white',
          }}
          onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => { e.preventDefault(); setDragging(false); handleFiles(e.dataTransfer.files) }}
          onClick={() => inputRef.current?.click()}
        >
          <input ref={inputRef} type="file" accept=".pdf,.txt" multiple className="hidden"
            onChange={(e) => handleFiles(e.target.files)} />
          <div className="flex flex-col items-center gap-3">
            <div className="w-10 h-10 rounded-2xl flex items-center justify-center transition-fast"
              style={{
                background: dragging ? 'linear-gradient(135deg,#1248BE,#4A8ED4)' : 'rgba(18,72,190,0.08)',
              }}>
              <Upload size={17} style={{ color: dragging ? '#fff' : '#1248BE' }} />
            </div>
            <div>
              <p className="text-sm font-semibold text-am-ink mb-1">
                {dragging ? 'Solte o arquivo aqui' : 'Ensinar à IA'}
              </p>
              <p className="text-xs text-am-muted">Arraste ou clique — PDF ou TXT</p>
            </div>
            <motion.button
              whileHover={{ scale: 1.04 }}
              whileTap={{ scale: 0.96 }}
              transition={{ type: 'spring', stiffness: 400, damping: 28 }}
              className="px-4 py-2 text-white text-xs font-bold rounded-xl"
              style={{ background: 'linear-gradient(135deg,#1248BE,#4A8ED4)' }}
              onClick={(e) => { e.stopPropagation(); inputRef.current?.click() }}>
              Selecionar arquivo
            </motion.button>
          </div>
        </div>

        {/* ── Documentos indexados ── */}
        <Card>
          <CardHeader
            icon={<Database size={13} />}
            title="Documentos que a IA já aprendeu"
            badge={
              <span className="text-[10px] text-am-muted">{docs.length} doc{docs.length !== 1 ? 's' : ''}</span>
            }
          />

          {/* Busca */}
          <div className="px-4 pt-3 pb-2">
            <div className="relative">
              <Search size={12} className="absolute left-3 top-1/2 -translate-y-1/2 text-am-muted pointer-events-none" />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Buscar documento…"
                className="w-full pl-8 pr-4 py-2 text-xs rounded-xl bg-am-bg text-am-ink outline-none placeholder:text-am-muted"
                style={{ border: '1px solid var(--color-am-border)' }}
              />
            </div>
          </div>

          {filtered.length === 0 ? (
            <div className="flex flex-col items-center py-10 gap-2 text-am-muted">
              <Scale size={20} strokeWidth={1.5} />
              <span className="text-xs">
                {docs.length === 0 ? 'Nenhum documento enviado ainda' : 'Nenhum documento encontrado'}
              </span>
            </div>
          ) : (
            <div className="divide-y divide-am-border">
              {filtered.map((d) => (
                <motion.div
                  key={d.id}
                  layout
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: 8 }}
                  className="flex items-center gap-3 px-4 py-3 group row-in row-press hover:bg-am-bg transition-colors"
                >
                  <div className="w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0"
                    style={{ background: `${TIPO_CFG[d.tipo].color}12`, border: `1px solid ${TIPO_CFG[d.tipo].color}24` }}>
                    <FileText size={13} style={{ color: TIPO_CFG[d.tipo].color }} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-semibold text-am-ink truncate">{d.titulo}</p>
                    <div className="flex items-center gap-2 mt-1 flex-wrap">
                      <TipoBadge tipo={d.tipo} />
                      <span className="text-[10px] text-am-muted">{d.chunks} trechos</span>
                      {d.tamanho && <span className="text-[10px] text-am-muted">{d.tamanho}</span>}
                      <span className="text-[10px] text-am-muted">{fmt(d.adicionado_em)}</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    {uploaded.includes(d.id) && (
                      <span className="flex items-center gap-1 text-[10px] font-semibold" style={{ color: '#1A9E78' }}>
                        <CheckCircle size={11} /> Enviado
                      </span>
                    )}
                    <button
                      onClick={() => setDocs((prev) => prev.filter((x) => x.id !== d.id))}
                      className="opacity-0 group-hover:opacity-100 w-7 h-7 rounded-lg flex items-center justify-center text-am-muted transition-fast hover:text-red-500"
                      style={{ background: 'transparent' }}
                      onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(200,48,48,0.07)' }}
                      onMouseLeave={(e) => { e.currentTarget.style.background = '' }}>
                      <Trash2 size={12} />
                    </button>
                  </div>
                </motion.div>
              ))}
            </div>
          )}
        </Card>

      </div>
    </div>
  )
}
