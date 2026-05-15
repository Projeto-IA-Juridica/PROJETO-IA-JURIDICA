import { useState, useRef, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import {
  FolderOpen, Upload, FileText, CheckCircle, Database,
  Trash2, Search, ChevronDown, ChevronUp,
  Sparkles, BookOpen, Scale, AlertTriangle, Loader2, X,
} from 'lucide-react'
import {
  listarDocumentos, uploadDocumento, deletarDocumento, statusJob,
  type DocItem, type JobStatus,
} from '../api/rag'

/* ── Tipos e constantes ── */
const TIPO_CFG = {
  jurisprudencia: { label: 'Jurisprudência',   color: '#D08010' },
  tese:           { label: 'Tese / Argumento', color: '#1248BE' },
  sentenca:       { label: 'Sentença',         color: '#1A9E78' },
  parecer:        { label: 'Parecer / FAQ',    color: '#7C4DFF' },
  peticao:        { label: 'Petição',          color: '#2D6FD4' },
} as const

type TipoDoc = keyof typeof TIPO_CFG

interface PendingJob {
  job_id: string
  titulo: string
  tipo: TipoDoc
  status: JobStatus['status']
  erro: string | null
}

/* ── Sub-componentes de layout ── */
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

function TipoBadge({ tipo }: { tipo: TipoDoc }) {
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

/* ── Modal de seleção de tipo ── */
function TipoModal({
  file, onConfirm, onCancel,
}: {
  file: File
  onConfirm: (titulo: string, tipo: TipoDoc) => void
  onCancel: () => void
}) {
  const [titulo, setTitulo] = useState(file.name.replace(/\.[^.]+$/, ''))
  const [tipo,   setTipo]   = useState<TipoDoc>('peticao')

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-4"
      style={{ background: 'rgba(12,30,48,0.45)', backdropFilter: 'blur(4px)' }}>
      <motion.div
        initial={{ opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: 24 }}
        className="w-full max-w-md bg-white rounded-3xl p-6"
        style={{ boxShadow: '0 24px 64px rgba(12,30,48,0.18)' }}>
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-sm font-bold text-am-ink">Classificar documento</h2>
          <button onClick={onCancel} className="w-7 h-7 rounded-lg flex items-center justify-center text-am-muted hover:text-am-ink transition-colors"
            style={{ border: '1px solid var(--color-am-border)' }}>
            <X size={13} />
          </button>
        </div>

        <div className="mb-4">
          <label className="block text-[10px] font-bold uppercase tracking-wider text-am-secondary mb-1.5">Título</label>
          <input
            value={titulo}
            onChange={e => setTitulo(e.target.value)}
            className="w-full px-3 py-2.5 text-xs rounded-xl text-am-ink outline-none"
            style={{ border: '1px solid var(--color-am-border)', fontFamily: 'var(--font-sans)' }}
            onFocus={e => { e.target.style.borderColor = 'var(--color-am-blue)'; e.target.style.boxShadow = '0 0 0 3px rgba(18,72,190,0.10)' }}
            onBlur={e =>  { e.target.style.borderColor = 'var(--color-am-border)'; e.target.style.boxShadow = 'none' }}
          />
        </div>

        <div className="mb-5">
          <label className="block text-[10px] font-bold uppercase tracking-wider text-am-secondary mb-2">Tipo do documento</label>
          <div className="grid grid-cols-1 gap-1.5">
            {(Object.keys(TIPO_CFG) as TipoDoc[]).map(t => (
              <button key={t} type="button" onClick={() => setTipo(t)}
                className="flex items-center gap-2.5 px-3 py-2 rounded-xl text-left transition-all"
                style={tipo === t
                  ? { background: `${TIPO_CFG[t].color}0F`, border: `1.5px solid ${TIPO_CFG[t].color}`, color: TIPO_CFG[t].color }
                  : { background: 'transparent', border: '1px solid var(--color-am-border)', color: 'var(--color-am-secondary)' }}>
                <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: TIPO_CFG[t].color }} />
                <span className="text-xs font-semibold">{TIPO_CFG[t].label}</span>
              </button>
            ))}
          </div>
        </div>

        <button
          onClick={() => titulo.trim() && onConfirm(titulo.trim(), tipo)}
          disabled={!titulo.trim()}
          className="press w-full py-2.5 rounded-xl text-xs font-bold text-white"
          style={{
            background: 'linear-gradient(135deg,#1248BE,#3A7AB8)',
            border: 'none', cursor: titulo.trim() ? 'pointer' : 'not-allowed',
            fontFamily: 'var(--font-sans)', opacity: titulo.trim() ? 1 : 0.5,
          }}>
          Enviar para a IA
        </button>
      </motion.div>
    </div>
  )
}

/* ── Componente principal ── */
export default function DocumentosPage() {
  const qc = useQueryClient()
  const [dragging, setDragging] = useState(false)
  const [search,   setSearch]   = useState('')
  const [pendingFile, setPendingFile] = useState<File | null>(null)
  const [jobs, setJobs] = useState<PendingJob[]>([])
  const inputRef = useRef<HTMLInputElement>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['rag-docs'],
    queryFn: () => listarDocumentos(),
    staleTime: 30_000,
  })

  const docs: DocItem[] = data?.items ?? []
  const totalChunks = docs.reduce((a, d) => a + d.chunks, 0)
  const filtered = docs.filter(d => d.titulo.toLowerCase().includes(search.toLowerCase()))

  const deleteMut = useMutation({
    mutationFn: deletarDocumento,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['rag-docs'] }),
  })

  const handleFileSelect = useCallback((files: FileList | null) => {
    if (!files?.length) return
    const f = files[0]
    if (f.type !== 'application/pdf' && !f.name.endsWith('.txt')) return
    setPendingFile(f)
  }, [])

  async function handleUploadConfirm(titulo: string, tipo: TipoDoc) {
    if (!pendingFile) return
    setPendingFile(null)

    const job: PendingJob = { job_id: '', titulo, tipo, status: 'pendente', erro: null }
    setJobs(prev => [job, ...prev])

    try {
      const result = await uploadDocumento(pendingFile, titulo, tipo)
      const jobId = result.job_id

      setJobs(prev => prev.map(j => j.titulo === titulo && j.job_id === ''
        ? { ...j, job_id: jobId, status: 'em_andamento' }
        : j
      ))

      // Poll status until done
      const poll = async () => {
        try {
          const s = await statusJob(jobId)
          setJobs(prev => prev.map(j => j.job_id === jobId ? { ...j, status: s.status, erro: s.erro } : j))
          if (s.status === 'pendente' || s.status === 'em_andamento') {
            setTimeout(poll, 2500)
          } else if (s.status === 'concluido') {
            qc.invalidateQueries({ queryKey: ['rag-docs'] })
            setTimeout(() => setJobs(prev => prev.filter(j => j.job_id !== jobId)), 4000)
          }
        } catch {
          setJobs(prev => prev.map(j => j.job_id === jobId ? { ...j, status: 'erro', erro: 'Erro ao verificar status' } : j))
        }
      }
      setTimeout(poll, 2000)

    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Erro no upload'
      setJobs(prev => prev.map(j => j.titulo === titulo && j.job_id === ''
        ? { ...j, status: 'erro', erro: msg }
        : j
      ))
    }
  }

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="p-4 max-w-3xl mx-auto space-y-4 page-enter">

        {/* Header */}
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

        {/* Stats */}
        <div className="grid grid-cols-3 gap-3">
          {[
            { val: isLoading ? '—' : docs.length,   label: 'Documentos',        color: '#1248BE' },
            { val: isLoading ? '—' : totalChunks,   label: 'Trechos indexados', color: '#1A9E78' },
            { val: Object.keys(TIPO_CFG).length,     label: 'Categorias',        color: '#7C4DFF' },
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

        {/* Jobs em andamento */}
        <AnimatePresence>
          {jobs.map(job => (
            <motion.div key={job.job_id || job.titulo}
              initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, height: 0 }}
              className="flex items-center gap-3 px-4 py-3 rounded-2xl"
              style={job.status === 'erro'
                ? { background: 'rgba(200,48,48,0.06)', border: '1px solid rgba(200,48,48,0.20)' }
                : job.status === 'concluido'
                  ? { background: 'rgba(26,158,120,0.06)', border: '1px solid rgba(26,158,120,0.22)' }
                  : { background: 'rgba(18,72,190,0.05)', border: '1px solid rgba(18,72,190,0.18)' }
              }>
              {job.status === 'erro'
                ? <AlertTriangle size={14} style={{ color: '#C83030' }} className="flex-shrink-0" />
                : job.status === 'concluido'
                  ? <CheckCircle size={14} style={{ color: '#1A9E78' }} className="flex-shrink-0" />
                  : <Loader2 size={14} style={{ color: 'var(--color-am-blue)' }} className="animate-spin flex-shrink-0" />
              }
              <div className="flex-1 min-w-0">
                <p className="text-xs font-semibold text-am-ink truncate">{job.titulo}</p>
                <p className="text-[10px] text-am-muted">
                  {job.status === 'pendente'    && 'Aguardando processamento...'}
                  {job.status === 'em_andamento' && 'Indexando para a IA...'}
                  {job.status === 'concluido'   && 'Documento indexado com sucesso'}
                  {job.status === 'erro'        && (job.erro ?? 'Erro no processamento')}
                </p>
              </div>
              {(job.status === 'erro' || job.status === 'concluido') && (
                <button onClick={() => setJobs(prev => prev.filter(j => j !== job))}
                  className="text-am-muted hover:text-am-ink transition-colors flex-shrink-0">
                  <X size={12} />
                </button>
              )}
            </motion.div>
          ))}
        </AnimatePresence>

        {/* Como funciona */}
        <Collapsible title="Como a IA usa os documentos" icon={<Sparkles size={13} />} defaultOpen>
          <div className="px-4 py-4 space-y-3">
            <p className="text-xs text-am-secondary leading-relaxed">
              Quando o advogado ou cliente faz uma pergunta, a IA segue três passos com os documentos do escritório:
            </p>
            <div className="space-y-2">
              {[
                { step: '1', title: 'Identifica', desc: 'Quais documentos do seu escritório são relevantes para aquela pergunta' },
                { step: '2', title: 'Lê',          desc: 'Os trechos mais pertinentes automaticamente, sem precisar abrir o arquivo' },
                { step: '3', title: 'Responde',    desc: 'Usando o raciocínio e a linguagem desses documentos — soando como você' },
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
          </div>
        </Collapsible>

        {/* O que enviar */}
        <Collapsible title="O que enviar para a IA aprender" icon={<BookOpen size={13} />}>
          <div className="px-4 py-4 space-y-4">
            <p className="text-xs text-am-secondary leading-relaxed">
              A IA identifica automaticamente a área jurídica e busca os documentos mais relevantes.
              Quanto mais focados forem os documentos, melhor ela responde.
            </p>
            <div className="space-y-2">
              {(Object.keys(TIPO_CFG) as TipoDoc[]).map(tipo => {
                const cfg = TIPO_CFG[tipo]
                return (
                  <div key={tipo} className="rounded-xl p-3"
                    style={{ background: `${cfg.color}07`, border: `1px solid ${cfg.color}18` }}>
                    <TipoBadge tipo={tipo} />
                    <p className="text-[11px] text-am-secondary mt-1.5">
                      {tipo === 'jurisprudencia' && 'Acórdãos, súmulas e decisões similares aos seus casos'}
                      {tipo === 'tese'           && 'Argumentos e estratégias que funcionam no tribunal'}
                      {tipo === 'sentenca'       && 'Sentenças anonimizadas em casos similares'}
                      {tipo === 'parecer'        && 'Perguntas frequentes e explicações ao cliente'}
                      {tipo === 'peticao'        && 'Petições iniciais e contestações com seus argumentos'}
                    </p>
                  </div>
                )
              })}
            </div>
            <div className="flex items-start gap-2 px-3 py-2.5 rounded-xl"
              style={{ background: 'rgba(200,48,48,0.04)', border: '1px solid rgba(200,48,48,0.15)' }}>
              <AlertTriangle size={12} style={{ color: '#C83030' }} className="flex-shrink-0 mt-0.5" />
              <p className="text-[11px] text-am-secondary">
                <strong>Não envie</strong> documentos com CPF ou dados pessoais. Anonimize antes. Aceito: PDF e TXT, máx. 10 MB.
              </p>
            </div>
          </div>
        </Collapsible>

        {/* Upload zone */}
        <div
          className="relative rounded-2xl border-2 border-dashed p-6 text-center transition-fast cursor-pointer"
          style={{
            borderColor: dragging ? 'var(--color-am-blue)' : 'rgba(18,72,190,0.25)',
            background:  dragging ? 'rgba(18,72,190,0.05)' : 'white',
          }}
          onDragOver={e => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={e => { e.preventDefault(); setDragging(false); handleFileSelect(e.dataTransfer.files) }}
          onClick={() => inputRef.current?.click()}
        >
          <input ref={inputRef} type="file" accept=".pdf,.txt" className="hidden"
            onChange={e => handleFileSelect(e.target.files)} />
          <div className="flex flex-col items-center gap-3">
            <div className="w-10 h-10 rounded-2xl flex items-center justify-center transition-fast"
              style={{ background: dragging ? 'linear-gradient(135deg,#1248BE,#4A8ED4)' : 'rgba(18,72,190,0.08)' }}>
              <Upload size={17} style={{ color: dragging ? '#fff' : '#1248BE' }} />
            </div>
            <div>
              <p className="text-sm font-semibold text-am-ink mb-1">
                {dragging ? 'Solte o arquivo aqui' : 'Ensinar à IA'}
              </p>
              <p className="text-xs text-am-muted">Arraste ou clique — PDF ou TXT · máx. 10 MB</p>
            </div>
            <motion.button
              whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.96 }}
              transition={{ type: 'spring', stiffness: 400, damping: 28 }}
              className="px-4 py-2 text-white text-xs font-bold rounded-xl"
              style={{ background: 'linear-gradient(135deg,#1248BE,#4A8ED4)' }}
              onClick={e => { e.stopPropagation(); inputRef.current?.click() }}>
              Selecionar arquivo
            </motion.button>
          </div>
        </div>

        {/* Lista de documentos */}
        <Card>
          <CardHeader
            icon={<Database size={13} />}
            title="Documentos que a IA já aprendeu"
            badge={<span className="text-[10px] text-am-muted">{docs.length} doc{docs.length !== 1 ? 's' : ''}</span>}
          />

          <div className="px-4 pt-3 pb-2">
            <div className="relative">
              <Search size={12} className="absolute left-3 top-1/2 -translate-y-1/2 text-am-muted pointer-events-none" />
              <input
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Buscar documento…"
                className="w-full pl-8 pr-4 py-2 text-xs rounded-xl bg-am-bg text-am-ink outline-none placeholder:text-am-muted"
                style={{ border: '1px solid var(--color-am-border)' }}
              />
            </div>
          </div>

          {isLoading && (
            <div className="flex items-center justify-center py-10">
              <Loader2 size={20} className="animate-spin text-am-muted" />
            </div>
          )}

          {!isLoading && filtered.length === 0 && (
            <div className="flex flex-col items-center py-10 gap-2 text-am-muted">
              <Scale size={20} strokeWidth={1.5} />
              <span className="text-xs">
                {docs.length === 0 ? 'Nenhum documento enviado ainda' : 'Nenhum documento encontrado'}
              </span>
            </div>
          )}

          {!isLoading && filtered.length > 0 && (
            <div className="divide-y divide-am-border">
              {filtered.map(d => {
                const tipo = (TIPO_CFG[d.tipo as TipoDoc] ? d.tipo : 'peticao') as TipoDoc
                const cfg  = TIPO_CFG[tipo]
                return (
                  <motion.div key={d.doc_hash} layout
                    initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }}
                    className="flex items-center gap-3 px-4 py-3 group hover:bg-am-bg transition-colors">
                    <div className="w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0"
                      style={{ background: `${cfg.color}12`, border: `1px solid ${cfg.color}24` }}>
                      <FileText size={13} style={{ color: cfg.color }} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-semibold text-am-ink truncate">{d.titulo}</p>
                      <div className="flex items-center gap-2 mt-1 flex-wrap">
                        <TipoBadge tipo={tipo} />
                        <span className="text-[10px] text-am-muted">{d.chunks} trechos</span>
                        {(d.metadata_json as { tamanho_bytes?: number })?.tamanho_bytes && (
                          <span className="text-[10px] text-am-muted">
                            {Math.round(((d.metadata_json as { tamanho_bytes: number }).tamanho_bytes) / 1024)} KB
                          </span>
                        )}
                      </div>
                    </div>
                    <button
                      onClick={() => deleteMut.mutate(d.doc_hash)}
                      disabled={deleteMut.isPending}
                      className="opacity-0 group-hover:opacity-100 w-7 h-7 rounded-lg flex items-center justify-center text-am-muted transition-fast hover:text-red-500"
                      onMouseEnter={e => { e.currentTarget.style.background = 'rgba(200,48,48,0.07)' }}
                      onMouseLeave={e => { e.currentTarget.style.background = '' }}>
                      <Trash2 size={12} />
                    </button>
                  </motion.div>
                )
              })}
            </div>
          )}
        </Card>

      </div>

      {/* Modal de classificação */}
      <AnimatePresence>
        {pendingFile && (
          <TipoModal
            file={pendingFile}
            onConfirm={handleUploadConfirm}
            onCancel={() => setPendingFile(null)}
          />
        )}
      </AnimatePresence>
    </div>
  )
}
