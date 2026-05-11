import { useState, useRef } from 'react'
import { Upload, FileText, CheckCircle, Database, Trash2 } from 'lucide-react'

interface Doc { titulo: string; tipo: string; chunks: number }

const BASE_DOCS: Doc[] = [
  { titulo: 'Tese — Danos Morais por Falha na Prestação de Serviços', tipo: 'Tese',          chunks: 8  },
  { titulo: 'Jurisprudência STJ 2023 — Responsabilidade Civil',        tipo: 'Jurisprudência', chunks: 12 },
  { titulo: 'Petição Modelo — Indenização ao Consumidor',              tipo: 'Petição',        chunks: 6  },
]

/* Badge por tipo — único uso de cor semântica aqui: distinguir tipo de doc */
const TIPO_BADGE: Record<string, { color: string }> = {
  Tese:           { color: 'var(--color-am-blue)'    },
  Jurisprudência: { color: 'var(--color-am-green)'   },
  Petição:        { color: 'var(--color-am-amber)'   },
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
  const [docs, setDocs]         = useState<Doc[]>(BASE_DOCS)
  const [dragging, setDragging] = useState(false)
  const [uploaded, setUploaded] = useState<string[]>([])
  const inputRef = useRef<HTMLInputElement>(null)

  const totalChunks = docs.reduce((a, d) => a + d.chunks, 0)

  function handleFiles(files: FileList | null) {
    if (!files) return
    Array.from(files).forEach((f) => {
      if (f.type !== 'application/pdf' && !f.name.endsWith('.txt')) return
      const doc: Doc = {
        titulo: f.name.replace(/\.[^.]+$/, ''),
        tipo:   f.name.endsWith('.pdf') ? 'PDF' : 'TXT',
        chunks: Math.floor(Math.random() * 10) + 3,
      }
      setDocs((prev) => [...prev, doc])
      setUploaded((prev) => [...prev, doc.titulo])
      setTimeout(() => setUploaded((prev) => prev.filter((n) => n !== doc.titulo)), 3000)
    })
  }

  return (
    <div className="p-4 sm:p-6 space-y-4">

      {/* Stats — 3 colunas */}
      <div className="grid grid-cols-3 gap-3">
        {[
          { val: docs.length,  lbl: 'Documentos',       color: 'var(--color-am-blue)'  },
          { val: totalChunks,  lbl: 'Blocos indexados', color: 'var(--color-am-green)' },
          { val: uploaded.length || '—', lbl: 'Recém enviados', color: 'var(--color-am-amber)' },
        ].map(({ val, lbl, color }) => (
          <div key={lbl}
            className="flex flex-col items-center py-3 sm:py-4 rounded-xl bg-white card-shadow border border-am-border">
            <span className="text-xl sm:text-2xl font-extrabold leading-none" style={{ color }}>{val}</span>
            <span className="text-[9px] font-semibold mt-1 text-center px-1" style={{ color }}>
              {lbl}
            </span>
          </div>
        ))}
      </div>

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

        {docs.length === 0 ? (
          <div className="flex flex-col items-center py-10 gap-2 text-am-muted">
            <FileText size={22} strokeWidth={1.5} />
            <span className="text-xs">Nenhum documento na base</span>
          </div>
        ) : (
          <div className="divide-y divide-am-border">
            {docs.map((d, i) => (
              <div key={i} className="flex items-center gap-3 px-4 sm:px-5 py-3.5 group hover:bg-am-bg transition-fast">
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
                  {uploaded.includes(d.titulo) && (
                    <span className="flex items-center gap-1 text-[10px] font-semibold" style={{ color: '#1A9E78' }}>
                      <CheckCircle size={11} /> Enviado
                    </span>
                  )}
                  <button
                    onClick={() => setDocs((prev) => prev.filter((_, j) => j !== i))}
                    className="opacity-0 group-hover:opacity-100 w-7 h-7 rounded-lg flex items-center justify-center
                      text-am-muted transition-fast"
                    style={{ '--hover-bg': 'rgba(200,48,48,0.07)' } as React.CSSProperties}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.color = '#C83030'
                      e.currentTarget.style.background = 'rgba(200,48,48,0.07)'
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.color = ''
                      e.currentTarget.style.background = ''
                    }}
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Zona de upload */}
      <div
        className="relative rounded-xl border-2 border-dashed p-6 sm:p-8 text-center transition-fast cursor-pointer"
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
          <div
            className="w-11 h-11 rounded-xl flex items-center justify-center transition-fast"
            style={{
              background: dragging ? 'var(--color-am-blue)' : 'var(--color-am-surface)',
              border: dragging ? 'none' : '1px solid var(--color-am-border)',
            }}
          >
            <Upload size={18} style={{ color: dragging ? '#fff' : 'var(--color-am-blue)' }} />
          </div>
          <div>
            <div className="text-sm font-semibold text-am-secondary mb-1">
              {dragging ? 'Solte o arquivo aqui' : 'Adicionar documento à base'}
            </div>
            <div className="text-xs text-am-muted">
              Arraste ou clique — PDF ou TXT
            </div>
          </div>
          <button
            className="px-4 py-2 text-white text-xs font-bold rounded-lg transition-fast"
            style={{ background: 'var(--color-am-blue)' }}
            onClick={(e) => { e.stopPropagation(); inputRef.current?.click() }}
            onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--color-am-blue-hover)')}
            onMouseLeave={(e) => (e.currentTarget.style.background = 'var(--color-am-blue)')}
          >
            Selecionar arquivo
          </button>
        </div>
      </div>
    </div>
  )
}
