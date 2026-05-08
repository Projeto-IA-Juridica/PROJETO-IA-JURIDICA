import { useState, useRef } from 'react'
import { FolderOpen, Upload, FileText, CheckCircle, Database, Trash2, Search, Filter } from 'lucide-react'

interface Doc {
  id: number
  titulo: string
  tipo: string
  categoria: string
  chunks: number
  tamanho?: string
  adicionado_em: string
}

const CATEGORIAS = ['Todos', 'Teses', 'Jurisprudência', 'Petições', 'Contratos', 'Outros']

const TIPO_CFG: Record<string, { color: string }> = {
  Tese:           { color: 'var(--color-am-blue)'      },
  Jurisprudência: { color: 'var(--color-am-green)'     },
  Petição:        { color: 'var(--color-am-amber)'     },
  Contrato:       { color: '#7C4DFF'                   },
  PDF:            { color: 'var(--color-am-secondary)' },
  TXT:            { color: 'var(--color-am-secondary)' },
}

const INITIAL_DOCS: Doc[] = [
  { id: 1, titulo: 'Tese — Danos Morais por Falha na Prestação de Serviços', tipo: 'Tese',           categoria: 'Teses',         chunks: 8,  tamanho: '142 KB', adicionado_em: '2026-05-01' },
  { id: 2, titulo: 'Jurisprudência STJ 2023 — Responsabilidade Civil',        tipo: 'Jurisprudência', categoria: 'Jurisprudência', chunks: 12, tamanho: '287 KB', adicionado_em: '2026-05-02' },
  { id: 3, titulo: 'Petição Modelo — Indenização ao Consumidor',              tipo: 'Petição',        categoria: 'Petições',       chunks: 6,  tamanho: '98 KB',  adicionado_em: '2026-05-03' },
  { id: 4, titulo: 'Contrato de Prestação de Serviços Advocatícios',          tipo: 'Contrato',       categoria: 'Contratos',      chunks: 4,  tamanho: '76 KB',  adicionado_em: '2026-05-04' },
  { id: 5, titulo: 'Súmulas STJ — Direito do Consumidor Compiladas',         tipo: 'Jurisprudência', categoria: 'Jurisprudência', chunks: 15, tamanho: '320 KB', adicionado_em: '2026-05-05' },
]

function TipoBadge({ tipo }: { tipo: string }) {
  const color = TIPO_CFG[tipo]?.color ?? 'var(--color-am-secondary)'
  return (
    <span className="text-[9px] font-bold uppercase tracking-wider px-1.5 py-px rounded"
      style={{ color, background: `color-mix(in srgb, ${color} 10%, transparent)`, border: `1px solid color-mix(in srgb, ${color} 22%, transparent)` }}>
      {tipo}
    </span>
  )
}

export default function DocumentosPage() {
  const [docs, setDocs]           = useState<Doc[]>(INITIAL_DOCS)
  const [dragging, setDragging]   = useState(false)
  const [uploaded, setUploaded]   = useState<number[]>([])
  const [search, setSearch]       = useState('')
  const [categoria, setCategoria] = useState('Todos')
  const inputRef                  = useRef<HTMLInputElement>(null)

  const totalChunks = docs.reduce((a, d) => a + d.chunks, 0)

  const filtered = docs.filter((d) => {
    const matchSearch = d.titulo.toLowerCase().includes(search.toLowerCase())
    const matchCat    = categoria === 'Todos' || d.categoria === categoria
    return matchSearch && matchCat
  })

  function handleFiles(files: FileList | null) {
    if (!files) return
    Array.from(files).forEach((f) => {
      if (f.type !== 'application/pdf' && !f.name.endsWith('.txt')) return
      const id  = Date.now() + Math.random()
      const doc: Doc = {
        id,
        titulo:       f.name.replace(/\.[^.]+$/, ''),
        tipo:         f.name.endsWith('.pdf') ? 'PDF' : 'TXT',
        categoria:    'Outros',
        chunks:       Math.floor(Math.random() * 10) + 3,
        tamanho:      `${Math.round(f.size / 1024)} KB`,
        adicionado_em: new Date().toISOString().split('T')[0],
      }
      setDocs((prev) => [doc, ...prev])
      setUploaded((prev) => [...prev, id])
      setTimeout(() => setUploaded((prev) => prev.filter((n) => n !== id)), 3000)
    })
  }

  function formatDate(iso: string) {
    return new Date(iso).toLocaleDateString('pt-BR', { day: '2-digit', month: 'short', year: '2-digit' })
  }

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="p-4 sm:p-6 max-w-4xl mx-auto space-y-5 page-enter">

        {/* Header */}
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0"
            style={{ background: 'rgba(58,122,184,0.1)', border: '1px solid rgba(58,122,184,0.2)' }}>
            <FolderOpen size={16} className="text-am-blue" />
          </div>
          <div>
            <h2 className="text-lg font-extrabold text-am-ink tracking-tight">Base de Documentos</h2>
            <p className="text-xs text-am-muted mt-0.5">Conhecimento jurídico indexado para a IA</p>
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-3 gap-3">
          {[
            { val: docs.length,  label: 'Documentos',       color: 'var(--color-am-blue)'  },
            { val: totalChunks,  label: 'Blocos indexados', color: 'var(--color-am-green)' },
            { val: CATEGORIAS.length - 1, label: 'Categorias', color: 'var(--color-am-amber)' },
          ].map(({ val, label, color }) => (
            <div key={label} className="bg-white rounded-xl card-shadow border border-am-border py-4 flex flex-col items-center gap-1.5 card-border-hover">
              <span className="text-2xl font-extrabold leading-none" style={{ color }}>{val}</span>
              <span className="text-[9px] font-semibold text-center px-2" style={{ color }}>{label}</span>
            </div>
          ))}
        </div>

        {/* Filtros */}
        <div className="flex gap-2 sm:gap-3 flex-wrap">
          {CATEGORIAS.map((cat) => (
            <button key={cat} onClick={() => setCategoria(cat)}
              className="px-3 py-1.5 rounded-lg text-xs font-semibold press"
              style={categoria === cat
                ? { background: 'var(--color-am-surface)', color: 'var(--color-am-blue)', border: '1px solid var(--color-am-border)' }
                : { background: 'transparent', color: 'var(--color-am-muted)', border: '1px solid transparent' }}>
              {cat}
            </button>
          ))}
        </div>

        {/* Busca */}
        <div className="relative">
          <Search size={13} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-am-muted" />
          <input type="text" value={search} onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar documento…"
            className="w-full pl-9 pr-4 py-2.5 text-xs rounded-xl bg-white border border-am-border text-am-ink outline-none transition-fast placeholder:text-am-muted card-shadow"
            onFocus={(e) => (e.target.style.borderColor = 'var(--color-am-blue)')}
            onBlur={(e) => (e.target.style.borderColor = 'var(--color-am-border)')}
          />
        </div>

        {/* Lista */}
        <div className="bg-white rounded-2xl card-shadow border border-am-border overflow-hidden card-border-hover">
          <div className="flex items-center justify-between px-5 py-3 bg-am-bg border-b border-am-border">
            <div className="flex items-center gap-2">
              <Database size={12} className="text-am-blue" />
              <span className="text-[10px] font-bold text-am-secondary uppercase tracking-wider">
                {categoria === 'Todos' ? 'Todos os documentos' : categoria}
              </span>
            </div>
            <div className="flex items-center gap-1.5 text-[10px] text-am-muted">
              <Filter size={10} />
              {filtered.length} doc{filtered.length !== 1 ? 's' : ''}
            </div>
          </div>

          {filtered.length === 0 ? (
            <div className="flex flex-col items-center py-12 gap-2 text-am-muted">
              <FileText size={22} strokeWidth={1.5} />
              <span className="text-xs">Nenhum documento encontrado</span>
            </div>
          ) : (
            <div className="divide-y divide-am-border">
              {filtered.map((d) => (
                <div key={d.id}
                  className="flex items-center gap-3 px-5 py-3.5 group hover:bg-am-bg row-press row-in">
                  <div className="w-8 h-8 rounded-xl bg-am-surface flex items-center justify-center flex-shrink-0 border border-am-border">
                    <FileText size={13} className="text-am-blue" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-xs font-semibold text-am-ink truncate">{d.titulo}</div>
                    <div className="flex items-center gap-2 mt-1 flex-wrap">
                      <TipoBadge tipo={d.tipo} />
                      <span className="text-[10px] text-am-muted">{d.chunks} blocos</span>
                      {d.tamanho && <span className="text-[10px] text-am-muted">{d.tamanho}</span>}
                      <span className="text-[10px] text-am-muted hidden sm:block">{formatDate(d.adicionado_em)}</span>
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
                      className="opacity-0 group-hover:opacity-100 w-7 h-7 rounded-lg flex items-center justify-center
                        text-am-muted transition-fast"
                      onMouseEnter={(e) => { e.currentTarget.style.color = '#C83030'; e.currentTarget.style.background = 'rgba(200,48,48,0.07)' }}
                      onMouseLeave={(e) => { e.currentTarget.style.color = ''; e.currentTarget.style.background = '' }}>
                      <Trash2 size={12} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Upload */}
        <div
          className="relative rounded-2xl border-2 border-dashed p-6 sm:p-8 text-center transition-fast cursor-pointer"
          style={{
            borderColor: dragging ? 'var(--color-am-blue)' : 'var(--color-am-blue-light)',
            background:  dragging ? 'rgba(58,122,184,0.05)' : 'var(--color-am-bg)',
          }}
          onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => { e.preventDefault(); setDragging(false); handleFiles(e.dataTransfer.files) }}
          onClick={() => inputRef.current?.click()}
        >
          <input ref={inputRef} type="file" accept=".pdf,.txt" multiple className="hidden"
            onChange={(e) => handleFiles(e.target.files)} />

          <div className="flex flex-col items-center gap-3">
            <div className="w-11 h-11 rounded-xl flex items-center justify-center transition-fast"
              style={{
                background: dragging ? 'var(--color-am-blue)' : 'var(--color-am-surface)',
                border: dragging ? 'none' : '1px solid var(--color-am-border)',
              }}>
              <Upload size={18} style={{ color: dragging ? '#fff' : 'var(--color-am-blue)' }} />
            </div>
            <div>
              <div className="text-sm font-semibold text-am-secondary mb-1">
                {dragging ? 'Solte o arquivo aqui' : 'Adicionar à base de conhecimento'}
              </div>
              <div className="text-xs text-am-muted">Arraste ou clique — PDF ou TXT</div>
            </div>
            <button
              className="px-4 py-2 text-white text-xs font-bold rounded-xl transition-fast"
              style={{ background: 'var(--color-am-blue)' }}
              onClick={(e) => { e.stopPropagation(); inputRef.current?.click() }}
              onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--color-am-blue-hover)')}
              onMouseLeave={(e) => (e.currentTarget.style.background = 'var(--color-am-blue)')}>
              Selecionar arquivo
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
