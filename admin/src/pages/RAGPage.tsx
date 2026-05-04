import { useState, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ragApi, type RAGChunk } from '../api'
import { Spinner, EmptyState, ErrorBox, MetricCard } from '../components/ui'
import { BookOpen, Upload, Search, Trash2 } from 'lucide-react'

const TIPOS = ['peticao', 'sentenca', 'jurisprudencia', 'tese', 'parecer']

export default function RAGPage() {
  const qc = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const [titulo, setTitulo] = useState('')
  const [tipo, setTipo] = useState('jurisprudencia')
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [query, setQuery] = useState('')
  const [resultados, setResultados] = useState<RAGChunk[]>([])
  const [buscando, setBuscando] = useState(false)
  const [jobInfo, setJobInfo] = useState('')

  const { data: docs, isLoading, error } = useQuery({
    queryKey: ['rag-docs'],
    queryFn: ragApi.listar,
  })

  const { mutate: upload, isPending: uploading, error: uploadError } = useMutation({
    mutationFn: () => ragApi.upload(selectedFile!, titulo || selectedFile!.name, tipo),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['rag-docs'] })
      setJobInfo(`Ingestão iniciada. Job: ${res.job_id}`)
      setSelectedFile(null)
      setTitulo('')
      if (fileRef.current) fileRef.current.value = ''
    },
  })

  const { mutate: deletar } = useMutation({
    mutationFn: ragApi.deletar,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['rag-docs'] }),
  })

  const buscar = async () => {
    if (!query.trim()) return
    setBuscando(true)
    try {
      const r = await ragApi.buscar(query, tipo)
      setResultados(r)
    } finally { setBuscando(false) }
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (f) { setSelectedFile(f); if (!titulo) setTitulo(f.name.replace(/\.[^.]+$/, '')) }
  }

  if (error) return <ErrorBox message="Falha ao carregar documentos RAG." />

  return (
    <>
      <div className="page-header">
        <div className="page-header-main">
          <h1 className="page-title">Base de Conhecimento</h1>
          <p className="page-subtitle">Documentos jurídicos injetados nas respostas da IA</p>
        </div>
      </div>

      {/* Métricas */}
      <div className="page-grid page-grid-2" style={{ marginBottom: 18, maxWidth: 340 }}>
        <MetricCard value={docs?.length ?? 0} label="Documentos" />
        <MetricCard value={docs?.reduce((s, d) => s + d.chunks, 0) ?? 0} label="Chunks" />
      </div>

      <div className="page-grid page-grid-rag">
        {/* Left */}
        <div className="page-stack">
          {/* Upload */}
          <div className="surface page-panel page-stack">
            <div className="page-panel-kicker">
              <Upload size={14} /> Adicionar Documento
            </div>

            <div
              onClick={() => fileRef.current?.click()}
              style={{
                border: `1px dashed ${selectedFile ? 'var(--accent)' : 'var(--surface-border)'}`,
                borderRadius: 7, padding: 16, textAlign: 'center',
                cursor: 'pointer', marginBottom: 12,
                background: selectedFile ? 'var(--accent-glow)' : 'transparent',
                transition: 'all 0.15s',
              }}
            >
              {selectedFile
                ? <><div style={{ fontSize: 12, color: 'var(--accent)' }}>{selectedFile.name}</div><div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{(selectedFile.size / 1024).toFixed(1)} KB</div></>
                : <><div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Clique para selecionar PDF ou TXT</div></>
              }
              <input ref={fileRef} type="file" accept=".pdf,.txt" onChange={handleFileChange} style={{ display: 'none' }} />
            </div>

            {selectedFile && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <div>
                  <label className="label">Título</label>
                  <input className="input" value={titulo} onChange={e => setTitulo(e.target.value)} />
                </div>
                <div>
                  <label className="label">Tipo</label>
                  <select className="input" value={tipo} onChange={e => setTipo(e.target.value)}>
                    {TIPOS.map(t => <option key={t} value={t}>{t}</option>)}
                  </select>
                </div>
                {uploadError && <ErrorBox message="Falha no upload." />}
                {jobInfo && <div style={{ fontSize: 11, color: 'var(--success)' }}>{jobInfo}</div>}
                <button className="btn btn-primary" onClick={() => upload()} disabled={uploading}>
                  {uploading ? <><Spinner size={12} /> Ingerindo...</> : 'Ingerir documento'}
                </button>
              </div>
            )}
          </div>

          {/* Lista */}
          <div className="surface page-panel page-stack">
            <div className="page-panel-kicker">
              <BookOpen size={14} /> Documentos Indexados
            </div>
            {isLoading ? <Spinner /> : !docs?.length ? (
              <EmptyState icon={<BookOpen size={24} style={{ color: 'var(--text-muted)' }} />} title="Base vazia" desc="Adicione documentos para enriquecer as respostas." />
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                {docs.map(d => (
                  <div key={d.doc_hash} style={{
                    display: 'flex', alignItems: 'center', gap: 10, padding: '6px 10px',
                    background: 'var(--surface-overlay)', borderRadius: 6,
                    border: '1px solid var(--surface-border)'
                  }}>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-primary)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{d.titulo}</div>
                      <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{d.tipo} · {d.chunks} chunks</div>
                    </div>
                    <button className="btn btn-danger btn-sm" onClick={() => deletar(d.doc_hash)}><Trash2 size={12} /></button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right: Busca */}
        <div className="surface page-panel page-stack" style={{ alignSelf: 'start' }}>
          <div className="page-panel-kicker">
            <Search size={14} /> Busca Semântica
          </div>
          <p style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 12, lineHeight: 1.5 }}>
            Simula como a IA recupera contexto.
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div>
              <label className="label">Consulta</label>
              <input className="input" value={query} onChange={e => setQuery(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && buscar()}
                placeholder="prescrição trabalhista..." />
            </div>
            <button className="btn btn-primary" onClick={buscar} disabled={buscando || !query.trim()}>
              {buscando ? <Spinner size={12} /> : <><Search size={12} /> Buscar</>}
            </button>
          </div>

          {resultados.length > 0 && (
            <div style={{ marginTop: 14 }}>
              <div style={{ fontSize: 11, color: 'var(--success)', marginBottom: 8 }}>{resultados.length} chunk(s)</div>
              {resultados.map((r, i) => (
                <details key={i} style={{ marginBottom: 6 }}>
                  <summary style={{ fontSize: 12, cursor: 'pointer', color: 'var(--text-secondary)', fontWeight: 500 }}>
                    Trecho {i + 1}
                  </summary>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4, padding: 6, background: 'var(--surface-base)', borderRadius: 4, lineHeight: 1.5 }}>
                    {r.texto.slice(0, 400)}{r.texto.length > 400 ? '...' : ''}
                  </div>
                </details>
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  )
}
