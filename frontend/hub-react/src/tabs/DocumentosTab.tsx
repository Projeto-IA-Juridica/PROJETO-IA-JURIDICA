import { useState, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Upload, FileText, Trash2, Loader2, AlertTriangle, Download, X } from 'lucide-react'
import {
  listarDocumentosCliente,
  uploadDocumentoCliente,
  deletarDocumentoCliente,
  downloadDocumentoCliente,
  TIPOS_DOC_CLIENTE,
  type DocClienteItem,
  type TipoDocCliente,
} from '../api/documentosCliente'

interface Cliente {
  id: number
  nome: string
}

function TipoBadge({ tipo }: { tipo: TipoDocCliente }) {
  const cfg = TIPOS_DOC_CLIENTE[tipo] ?? TIPOS_DOC_CLIENTE.outro
  return (
    <span
      className="text-[9px] font-bold uppercase tracking-wider px-1.5 py-px rounded"
      style={{
        color: cfg.color,
        background: `${cfg.color}14`,
        border: `1px solid ${cfg.color}28`,
      }}
    >
      {cfg.label}
    </span>
  )
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('pt-BR', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  })
}

/* ── Modal de classificação do documento ── */
function UploadModal({
  file,
  onConfirm,
  onCancel,
}: {
  file: File
  onConfirm: (nome: string, tipo: TipoDocCliente) => void
  onCancel: () => void
}) {
  const [nome, setNome] = useState(file.name.replace(/\.[^.]+$/, ''))
  const [tipo, setTipo] = useState<TipoDocCliente>('outro')

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-4"
      style={{ background: 'rgba(12,30,48,0.45)', backdropFilter: 'blur(4px)' }}
    >
      <div
        className="w-full max-w-sm bg-white rounded-3xl p-5"
        style={{ boxShadow: '0 24px 64px rgba(12,30,48,0.18)' }}
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-bold text-am-ink">Classificar documento</h2>
          <button
            onClick={onCancel}
            className="w-7 h-7 rounded-lg flex items-center justify-center text-am-muted hover:text-am-ink transition-colors"
            style={{ border: '1px solid var(--color-am-border)' }}
          >
            <X size={13} />
          </button>
        </div>

        <div className="mb-3">
          <label className="block text-[10px] font-bold uppercase tracking-wider text-am-secondary mb-1.5">
            Nome
          </label>
          <input
            value={nome}
            onChange={(e) => setNome(e.target.value)}
            className="am-input"
          />
        </div>

        <div className="mb-4">
          <label className="block text-[10px] font-bold uppercase tracking-wider text-am-secondary mb-2">
            Tipo
          </label>
          <div className="grid grid-cols-2 gap-1.5">
            {(Object.keys(TIPOS_DOC_CLIENTE) as TipoDocCliente[]).map((t) => {
              const cfg = TIPOS_DOC_CLIENTE[t]
              const active = tipo === t
              return (
                <button
                  key={t}
                  type="button"
                  onClick={() => setTipo(t)}
                  className="flex items-center gap-2 px-3 py-2 rounded-xl text-left transition-all"
                  style={
                    active
                      ? { background: `${cfg.color}0F`, border: `1.5px solid ${cfg.color}`, color: cfg.color }
                      : { background: 'transparent', border: '1px solid var(--color-am-border)', color: 'var(--color-am-secondary)' }
                  }
                >
                  <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: cfg.color }} />
                  <span className="text-xs font-semibold">{cfg.label}</span>
                </button>
              )
            })}
          </div>
        </div>

        <button
          onClick={() => nome.trim() && onConfirm(nome.trim(), tipo)}
          disabled={!nome.trim()}
          className="w-full py-2.5 rounded-xl text-xs font-bold text-white"
          style={{
            background: 'linear-gradient(135deg,#1248BE,#3A7AB8)',
            opacity: nome.trim() ? 1 : 0.5,
            cursor: nome.trim() ? 'pointer' : 'not-allowed',
          }}
        >
          Adicionar documento
        </button>
      </div>
    </div>
  )
}

/* ── Componente principal ── */
export default function DocumentosTab({ cliente }: { cliente: Cliente }) {
  const qc = useQueryClient()
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const [pendingFile, setPendingFile] = useState<File | null>(null)
  const [uploadErro, setUploadErro] = useState<string | null>(null)

  const { data: docs = [], isLoading } = useQuery({
    queryKey: ['docs-cliente', cliente.id],
    queryFn: () => listarDocumentosCliente(cliente.id),
    staleTime: 30_000,
  })

  const uploadMut = useMutation({
    mutationFn: ({ file, nome, tipo }: { file: File; nome: string; tipo: TipoDocCliente }) =>
      uploadDocumentoCliente(cliente.id, file, nome, tipo),
    onSuccess: () => {
      setUploadErro(null)
      qc.invalidateQueries({ queryKey: ['docs-cliente', cliente.id] })
    },
    onError: (e: unknown) => {
      const msg =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        'Erro ao enviar documento'
      setUploadErro(msg)
    },
  })

  const deleteMut = useMutation({
    mutationFn: (docId: number) => deletarDocumentoCliente(cliente.id, docId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['docs-cliente', cliente.id] }),
  })

  const downloadMut = useMutation({
    mutationFn: (doc: DocClienteItem) =>
      downloadDocumentoCliente(cliente.id, doc.id, doc.arquivo_nome),
  })

  function handleFiles(files: FileList | null) {
    if (!files?.length) return
    const f = files[0]
    setPendingFile(f)
    setUploadErro(null)
  }

  function handleConfirm(nome: string, tipo: TipoDocCliente) {
    if (!pendingFile) return
    setPendingFile(null)
    uploadMut.mutate({ file: pendingFile, nome, tipo })
  }

  return (
    <div className="p-4 sm:p-6 space-y-4">

      {/* Erro de upload */}
      {uploadErro && (
        <div
          className="flex items-center gap-2 px-4 py-3 rounded-xl text-xs"
          style={{ background: 'rgba(200,48,48,0.06)', border: '1px solid rgba(200,48,48,0.18)', color: '#C83030' }}
        >
          <AlertTriangle size={13} className="flex-shrink-0" />
          {uploadErro}
          <button onClick={() => setUploadErro(null)} className="ml-auto">
            <X size={12} />
          </button>
        </div>
      )}

      {/* Processando */}
      {uploadMut.isPending && (
        <div
          className="flex items-center gap-2.5 px-4 py-3 rounded-xl text-xs"
          style={{ background: 'rgba(18,72,190,0.06)', border: '1px solid rgba(18,72,190,0.18)', color: 'var(--color-am-blue)' }}
        >
          <Loader2 size={13} className="animate-spin flex-shrink-0" />
          Enviando documento…
        </div>
      )}

      {/* Lista */}
      <div className="bg-white rounded-xl overflow-hidden card-shadow border border-am-border">
        <div className="flex items-center justify-between px-4 sm:px-5 py-3.5 bg-am-bg border-b border-am-border">
          <div className="flex items-center gap-2">
            <FileText size={13} className="text-am-blue" />
            <span className="text-[10px] font-bold text-am-secondary uppercase tracking-wider">
              Documentos do cliente
            </span>
          </div>
          <span className="text-[10px] text-am-muted font-medium">
            {docs.length} arquivo{docs.length !== 1 ? 's' : ''}
          </span>
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center h-20">
            <Loader2 size={18} className="animate-spin text-am-muted" />
          </div>
        ) : docs.length === 0 ? (
          <div className="flex flex-col items-center py-10 gap-2 text-am-muted">
            <FileText size={22} strokeWidth={1.5} />
            <span className="text-xs">Nenhum documento enviado ainda</span>
          </div>
        ) : (
          <div className="divide-y divide-am-border">
            {docs.map((doc) => {
              const cfg = TIPOS_DOC_CLIENTE[doc.tipo] ?? TIPOS_DOC_CLIENTE.outro
              return (
                <div
                  key={doc.id}
                  className="flex items-center gap-3 px-4 sm:px-5 py-3.5 group hover:bg-am-bg transition-fast"
                >
                  <div
                    className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
                    style={{ background: `${cfg.color}12`, border: `1px solid ${cfg.color}24` }}
                  >
                    <FileText size={13} style={{ color: cfg.color }} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-xs font-semibold text-am-ink truncate">{doc.nome}</div>
                    <div className="flex items-center gap-2 mt-1 flex-wrap">
                      <TipoBadge tipo={doc.tipo} />
                      <span className="text-[10px] text-am-muted">{formatBytes(doc.tamanho_bytes)}</span>
                      <span className="text-[10px] text-am-muted">{formatDate(doc.created_at)}</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-1 flex-shrink-0 opacity-0 group-hover:opacity-100 transition-fast">
                    <button
                      onClick={() => downloadMut.mutate(doc)}
                      disabled={downloadMut.isPending}
                      className="w-7 h-7 rounded-lg flex items-center justify-center text-am-muted hover:text-am-blue transition-fast"
                      title="Baixar"
                    >
                      {downloadMut.isPending && downloadMut.variables?.id === doc.id
                        ? <Loader2 size={12} className="animate-spin" />
                        : <Download size={12} />}
                    </button>
                    <button
                      onClick={() => deleteMut.mutate(doc.id)}
                      disabled={deleteMut.isPending && deleteMut.variables === doc.id}
                      className="w-7 h-7 rounded-lg flex items-center justify-center text-am-muted transition-fast"
                      onMouseEnter={(e) => { e.currentTarget.style.color = '#C83030'; e.currentTarget.style.background = 'rgba(200,48,48,0.07)' }}
                      onMouseLeave={(e) => { e.currentTarget.style.color = ''; e.currentTarget.style.background = '' }}
                      title="Remover"
                    >
                      {deleteMut.isPending && deleteMut.variables === doc.id
                        ? <Loader2 size={12} className="animate-spin" />
                        : <Trash2 size={12} />}
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Zona de upload */}
      <div
        className="relative rounded-xl border-2 border-dashed p-6 text-center transition-fast"
        style={{
          borderColor: dragging ? 'var(--color-am-blue)' : 'var(--color-am-blue-light)',
          background: dragging ? 'rgba(58,122,184,0.05)' : 'var(--color-am-bg)',
          cursor: uploadMut.isPending ? 'not-allowed' : 'pointer',
          opacity: uploadMut.isPending ? 0.6 : 1,
        }}
        onDragOver={(e) => { if (!uploadMut.isPending) { e.preventDefault(); setDragging(true) } }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); handleFiles(e.dataTransfer.files) }}
        onClick={() => { if (!uploadMut.isPending) inputRef.current?.click() }}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.png,.jpg,.jpeg,.webp,.docx,.txt"
          className="hidden"
          onChange={(e) => { handleFiles(e.target.files); e.target.value = '' }}
        />
        <div className="flex flex-col items-center gap-3">
          <div
            className="w-11 h-11 rounded-xl flex items-center justify-center transition-fast"
            style={{
              background: dragging ? 'var(--color-am-blue)' : 'var(--color-am-surface)',
              border: dragging ? 'none' : '1px solid var(--color-am-border)',
            }}
          >
            {uploadMut.isPending
              ? <Loader2 size={18} className="animate-spin" style={{ color: 'var(--color-am-blue)' }} />
              : <Upload size={18} style={{ color: dragging ? '#fff' : 'var(--color-am-blue)' }} />}
          </div>
          <div>
            <div className="text-sm font-semibold text-am-secondary mb-1">
              {uploadMut.isPending ? 'Enviando…' : dragging ? 'Solte o arquivo aqui' : 'Adicionar documento'}
            </div>
            <div className="text-xs text-am-muted">
              PDF, imagem ou DOCX · máx. 10 MB
            </div>
          </div>
          {!uploadMut.isPending && (
            <button
              className="px-4 py-2 text-white text-xs font-bold rounded-lg transition-fast"
              style={{ background: 'var(--color-am-blue)' }}
              onClick={(e) => { e.stopPropagation(); inputRef.current?.click() }}
              onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--color-am-blue-hover)')}
              onMouseLeave={(e) => (e.currentTarget.style.background = 'var(--color-am-blue)')}
            >
              Selecionar arquivo
            </button>
          )}
        </div>
      </div>

      <p className="text-[10px] text-am-muted text-center">
        Documentos enviados aqui ficam visíveis apenas para este cliente.
      </p>

      {/* Modal de classificação */}
      {pendingFile && (
        <UploadModal
          file={pendingFile}
          onConfirm={handleConfirm}
          onCancel={() => setPendingFile(null)}
        />
      )}
    </div>
  )
}
