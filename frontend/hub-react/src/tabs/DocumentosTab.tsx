import { useState, useRef, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Upload, FileText, Database, Trash2, Loader2, AlertTriangle } from 'lucide-react'
import { listarDocumentos, uploadDocumento, statusJob, deletarDocumento, type DocItem } from '../api/rag'

const TIPO_BADGE: Record<string, { color: string }> = {
  Tese:           { color: 'var(--color-am-blue)'      },
  Jurisprudência: { color: 'var(--color-am-green)'     },
  Petição:        { color: 'var(--color-am-amber)'     },
  PDF:            { color: 'var(--color-am-secondary)' },
  TXT:            { color: 'var(--color-am-secondary)' },
}

function TipoBadge({ tipo }: { tipo: string }) {
  const color = TIPO_BADGE[tipo]?.color ?? 'var(--color-am-secondary)'
  return (
    <span
      className="text-[9px] font-bold uppercase tracking-wider px-1.5 py-px rounded"
      style={{ color, background: `color-mix(in srgb, ${color} 10%, transparent)`, border: `1px solid color-mix(in srgb, ${color} 22%, transparent)` }}
    >
      {tipo}
    </span>
  )
}

export default function DocumentosTab() {
  const qc = useQueryClient()
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging]     = useState(false)
  const [pendingJob, setPendingJob] = useState<{ id: string; titulo: string } | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['rag-documentos'],
    queryFn: () => listarDocumentos(),
    staleTime: 30_000,
  })
  const docs: DocItem[] = data?.items ?? []
  const totalChunks = docs.reduce((a, d) => a + d.chunks, 0)

  const { data: jobStatus } = useQuery({
    queryKey: ['rag-job', pendingJob?.id],
    queryFn: () => statusJob(pendingJob!.id),
    enabled: pendingJob !== null,
    refetchInterval: (q) => {
      const done = ['concluido', 'erro', 'duplicata']
      return done.includes(q.state.data?.status ?? '') ? false : 2000
    },
  })

  useEffect(() => {
    if (['concluido', 'erro', 'duplicata'].includes(jobStatus?.status ?? '')) {
      qc.invalidateQueries({ queryKey: ['rag-documentos'] })
      setPendingJob(null)
    }
  }, [jobStatus, qc])

  const uploadMut = useMutation({
    mutationFn: (file: File) => {
      const titulo = file.name.replace(/\.[^.]+$/, '')
      const tipo   = file.name.toLowerCase().endsWith('.pdf') ? 'PDF' : 'TXT'
      return uploadDocumento(file, titulo, tipo)
    },
    onSuccess: (result, file) => {
      const titulo = file.name.replace(/\.[^.]+$/, '')
      setPendingJob({ id: result.job_id, titulo })
    },
  })

  const deleteMut = useMutation({
    mutationFn: (hash: string) => deletarDocumento(hash),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['rag-documentos'] }),
  })

  function handleFiles(files: FileList | null) {
    if (!files || uploadMut.isPending || pendingJob !== null) return
    const file = Array.from(files).find(
      (f) => f.type === 'application/pdf' || f.name.endsWith('.txt'),
    )
    if (file) uploadMut.mutate(file)
  }

  const isUploading = uploadMut.isPending || pendingJob !== null

  return (
    <div className="p-4 sm:p-6 space-y-4">

      {/* Stats */}
      <div className="grid grid-cols-3 gap-3">
        {[
          { val: isLoading ? '…' : docs.length,      lbl: 'Documentos',       color: 'var(--color-am-blue)'  },
          { val: isLoading ? '…' : totalChunks,       lbl: 'Blocos indexados', color: 'var(--color-am-green)' },
          { val: isUploading ? '↑' : '—',             lbl: 'Processando',      color: 'var(--color-am-amber)' },
        ].map(({ val, lbl, color }) => (
          <div key={lbl}
            className="flex flex-col items-center py-3 sm:py-4 rounded-xl bg-white card-shadow border border-am-border">
            <span className="text-xl sm:text-2xl font-extrabold leading-none" style={{ color }}>{val}</span>
            <span className="text-[9px] font-semibold mt-1 text-center px-1" style={{ color }}>{lbl}</span>
          </div>
        ))}
      </div>

      {/* Job em andamento */}
      {isUploading && (
        <div className="flex items-center gap-2.5 px-4 py-3 rounded-xl text-xs"
          style={{ background: 'rgba(18,72,190,0.06)', border: '1px solid rgba(18,72,190,0.18)', color: 'var(--color-am-blue)' }}>
          <Loader2 size={13} className="animate-spin flex-shrink-0" />
          {uploadMut.isPending
            ? 'Enviando arquivo…'
            : `Indexando "${pendingJob?.titulo}"…`}
        </div>
      )}

      {/* Erro de upload */}
      {uploadMut.isError && (
        <div className="flex items-center gap-2 px-4 py-3 rounded-xl text-xs"
          style={{ background: 'rgba(200,48,48,0.06)', border: '1px solid rgba(200,48,48,0.18)', color: '#C83030' }}>
          <AlertTriangle size={13} className="flex-shrink-0" />
          Erro ao enviar. Verifique o formato do arquivo (PDF ou TXT).
        </div>
      )}

      {/* Lista de documentos */}
      <div className="bg-white rounded-xl overflow-hidden card-shadow border border-am-border">
        <div className="flex items-center justify-between px-4 sm:px-5 py-3.5 bg-am-bg border-b border-am-border">
          <div className="flex items-center gap-2">
            <Database size={13} className="text-am-blue" />
            <span className="text-[10px] font-bold text-am-secondary uppercase tracking-wider">
              Base de Conhecimento
            </span>
          </div>
          <span className="text-[10px] text-am-muted font-medium">
            {docs.length} doc{docs.length !== 1 ? 's' : ''} · {totalChunks} blocos
          </span>
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center h-20">
            <Loader2 size={18} className="animate-spin text-am-muted" />
          </div>
        ) : docs.length === 0 ? (
          <div className="flex flex-col items-center py-10 gap-2 text-am-muted">
            <FileText size={22} strokeWidth={1.5} />
            <span className="text-xs">Nenhum documento na base</span>
          </div>
        ) : (
          <div className="divide-y divide-am-border">
            {docs.map((d: DocItem) => (
              <div key={d.doc_hash}
                className="flex items-center gap-3 px-4 sm:px-5 py-3.5 group hover:bg-am-bg transition-fast">
                <div className="w-7 h-7 rounded-lg bg-am-surface flex items-center justify-center flex-shrink-0 border border-am-border">
                  <FileText size={12} className="text-am-blue" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-semibold text-am-ink truncate">{d.titulo}</div>
                  <div className="flex items-center gap-2 mt-1">
                    <TipoBadge tipo={d.tipo} />
                    <span className="text-[10px] text-am-muted">{d.chunks} blocos</span>
                  </div>
                </div>
                <div className="flex items-center gap-1.5 flex-shrink-0">
                  {deleteMut.isPending && deleteMut.variables === d.doc_hash ? (
                    <Loader2 size={12} className="animate-spin text-am-muted" />
                  ) : (
                    <button
                      onClick={() => deleteMut.mutate(d.doc_hash)}
                      className="opacity-0 group-hover:opacity-100 w-7 h-7 rounded-lg flex items-center justify-center text-am-muted transition-fast"
                      onMouseEnter={(e) => { e.currentTarget.style.color = '#C83030'; e.currentTarget.style.background = 'rgba(200,48,48,0.07)' }}
                      onMouseLeave={(e) => { e.currentTarget.style.color = ''; e.currentTarget.style.background = '' }}
                    >
                      <Trash2 size={12} />
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Zona de upload */}
      <div
        className="relative rounded-xl border-2 border-dashed p-6 sm:p-8 text-center transition-fast"
        style={{
          borderColor: dragging ? 'var(--color-am-blue)' : 'var(--color-am-blue-light)',
          background:  dragging ? 'rgba(58,122,184,0.05)' : 'var(--color-am-bg)',
          cursor: isUploading ? 'not-allowed' : 'pointer',
          opacity: isUploading ? 0.6 : 1,
        }}
        onDragOver={(e) => { if (!isUploading) { e.preventDefault(); setDragging(true) } }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); handleFiles(e.dataTransfer.files) }}
        onClick={() => { if (!isUploading) inputRef.current?.click() }}
      >
        <input ref={inputRef} type="file" accept=".pdf,.txt" className="hidden"
          onChange={(e) => { handleFiles(e.target.files); e.target.value = '' }} />

        <div className="flex flex-col items-center gap-3">
          <div
            className="w-11 h-11 rounded-xl flex items-center justify-center transition-fast"
            style={{
              background: dragging ? 'var(--color-am-blue)' : 'var(--color-am-surface)',
              border: dragging ? 'none' : '1px solid var(--color-am-border)',
            }}
          >
            {isUploading
              ? <Loader2 size={18} className="animate-spin" style={{ color: 'var(--color-am-blue)' }} />
              : <Upload size={18} style={{ color: dragging ? '#fff' : 'var(--color-am-blue)' }} />
            }
          </div>
          <div>
            <div className="text-sm font-semibold text-am-secondary mb-1">
              {isUploading ? 'Processando…' : dragging ? 'Solte o arquivo aqui' : 'Adicionar documento à base'}
            </div>
            <div className="text-xs text-am-muted">
              {isUploading ? 'Aguarde a indexação terminar' : 'Arraste ou clique — PDF ou TXT'}
            </div>
          </div>
          {!isUploading && (
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
        Documentos indexados ficam disponíveis para consulta da IA em todos os atendimentos do escritório.
      </p>
    </div>
  )
}
