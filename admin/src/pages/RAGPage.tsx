import { useState, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ragApi, type RAGChunk } from '../api'
import { Spinner, EmptyState, ErrorBox } from '../components/ui'

const TIPOS = ['peticao', 'sentenca', 'jurisprudencia', 'tese', 'parecer']
const TIPO_ICON: Record<string, string> = {
  peticao: '🔵', sentenca: '🟢', jurisprudencia: '🟡', tese: '🟠', parecer: '🟣',
}

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
        <h1 className="page-title">Base de Conhecimento — RAG</h1>
        <p className="page-subtitle">Feature 3 — Documentos jurídicos injetados automaticamente nas respostas da IA</p>
      </div>

      {/* Métricas */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 24 }}>
        <div className="surface" style={{ padding: '12px 20px', display: 'flex', gap: 20 }}>
          <div><span style={{ fontSize: 20, fontWeight: 700 }}>{docs?.length ?? 0}</span><div style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Documentos</div></div>
          <div style={{ width: 1, background: 'var(--surface-border)' }} />
          <div><span style={{ fontSize: 20, fontWeight: 700 }}>{docs?.reduce((s, d) => s + d.chunks, 0) ?? 0}</span><div style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Chunks</div></div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: 20 }}>
        {/* Left: upload + lista */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Upload */}
          <div className="surface" style={{ padding: 20 }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14 }}>📤 Adicionar Documento</div>

            <div
              onClick={() => fileRef.current?.click()}
              style={{
                border: `2px dashed ${selectedFile ? 'var(--accent)' : 'var(--surface-border)'}`,
                borderRadius: 8, padding: '20px', textAlign: 'center',
                cursor: 'pointer', marginBottom: 14,
                background: selectedFile ? '#0f2040' : 'transparent',
                transition: 'all 0.15s',
              }}
            >
              {selectedFile
                ? <><div style={{ fontSize: 13, color: 'var(--accent)' }}>✅ {selectedFile.name}</div><div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{(selectedFile.size / 1024).toFixed(1)} KB</div></>
                : <><div style={{ fontSize: 22 }}>📄</div><div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Clique para selecionar PDF ou TXT</div></>
              }
              <input ref={fileRef} type="file" accept=".pdf,.txt" onChange={handleFileChange} style={{ display: 'none' }} />
            </div>

            {selectedFile && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                <div>
                  <label className="label">Título</label>
                  <input className="input" value={titulo} onChange={e => setTitulo(e.target.value)} />
                </div>
                <div>
                  <label className="label">Tipo</label>
                  <select className="input" value={tipo} onChange={e => setTipo(e.target.value)}>
                    {TIPOS.map(t => <option key={t} value={t}>{TIPO_ICON[t]} {t}</option>)}
                  </select>
                </div>
                {uploadError && <ErrorBox message="Falha no upload." />}
                {jobInfo && <div style={{ fontSize: 11, color: 'var(--success)' }}>{jobInfo}</div>}
                <button className="btn btn-primary" onClick={() => upload()} disabled={uploading}>
                  {uploading ? <><Spinner size={12} /> Ingerindo...</> : '📥 Ingerir documento'}
                </button>
              </div>
            )}
          </div>

          {/* Lista de documentos */}
          <div className="surface" style={{ padding: 20 }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14 }}>📂 Documentos Indexados</div>
            {isLoading ? <Spinner /> : !docs?.length ? (
              <EmptyState icon="📚" title="Base vazia" desc="Adicione documentos para enriquecer as respostas da IA." />
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {docs.map(d => (
                  <div key={d.doc_hash} style={{
                    display: 'flex', alignItems: 'center', gap: 12, padding: '8px 12px',
                    background: 'var(--surface-overlay)', borderRadius: 6,
                    border: '1px solid var(--surface-border)'
                  }}>
                    <span style={{ fontSize: 16 }}>{TIPO_ICON[d.tipo] ?? '⚪'}</span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{d.titulo}</div>
                      <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{d.tipo} · {d.chunks} chunks</div>
                    </div>
                    <button className="btn btn-danger btn-sm" onClick={() => deletar(d.doc_hash)}>🗑️</button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right: busca semântica */}
        <div className="surface" style={{ padding: 20, alignSelf: 'start' }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14 }}>🔍 Teste de Busca Semântica</div>
          <p style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 14, lineHeight: 1.5 }}>
            Simula como a IA recupera contexto ao responder uma pergunta.
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div>
              <label className="label">Consulta</label>
              <input className="input" value={query} onChange={e => setQuery(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && buscar()}
                placeholder="ex: prescrição trabalhista, rescisão indireta..." />
            </div>
            <button className="btn btn-primary" onClick={buscar} disabled={buscando || !query.trim()}>
              {buscando ? <Spinner size={12} /> : '🔎 Buscar'}
            </button>
          </div>

          {resultados.length > 0 && (
            <div style={{ marginTop: 16 }}>
              <div style={{ fontSize: 12, color: 'var(--success)', marginBottom: 10 }}>✅ {resultados.length} chunk(s) recuperado(s)</div>
              {resultados.map((r, i) => (
                <details key={i} style={{ marginBottom: 8 }}>
                  <summary style={{ fontSize: 12, cursor: 'pointer', color: 'var(--text-secondary)', fontWeight: 500 }}>
                    {TIPO_ICON[tipo] ?? '⚪'} Trecho {i + 1}
                  </summary>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 6, padding: '8px', background: 'var(--surface-base)', borderRadius: 4, lineHeight: 1.6 }}>
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
