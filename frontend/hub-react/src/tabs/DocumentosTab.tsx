import { useState, useRef } from 'react'
import { Upload, FileText, CheckCircle } from 'lucide-react'

interface Doc {
  titulo: string
  tipo: string
  chunks: number
}

const BASE_DOCS: Doc[] = [
  { titulo: 'Tese — Danos Morais por Falha na Prestação de Serviços', tipo: 'Tese', chunks: 8 },
  { titulo: 'Jurisprudência STJ 2023 — Responsabilidade Civil', tipo: 'Jurisprudência', chunks: 12 },
  { titulo: 'Petição Modelo — Indenização ao Consumidor', tipo: 'Petição', chunks: 6 },
]

export default function DocumentosTab() {
  const [docs, setDocs] = useState<Doc[]>(BASE_DOCS)
  const [dragging, setDragging] = useState(false)
  const [uploaded, setUploaded] = useState<string[]>([])
  const inputRef = useRef<HTMLInputElement>(null)

  const totalChunks = docs.reduce((a, d) => a + d.chunks, 0)

  function handleFiles(files: FileList | null) {
    if (!files) return
    Array.from(files).forEach((f) => {
      if (f.type !== 'application/pdf' && !f.name.endsWith('.txt')) return
      const newDoc: Doc = {
        titulo: f.name.replace(/\.[^.]+$/, ''),
        tipo: f.name.endsWith('.pdf') ? 'PDF' : 'TXT',
        chunks: Math.floor(Math.random() * 10) + 3,
      }
      setDocs((prev) => [...prev, newDoc])
      setUploaded((prev) => [...prev, f.name])
      setTimeout(() => setUploaded((prev) => prev.filter((n) => n !== f.name)), 3000)
    })
  }

  return (
    <div className="p-6 space-y-4">
      {/* Header card */}
      <div className="bg-white rounded-xl border border-am-border overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-am-border">
          <span className="text-[10px] font-semibold text-am-muted uppercase tracking-wider">
            Base de Conhecimento
          </span>
          <span className="text-[10px] text-am-muted">
            {docs.length} doc{docs.length !== 1 ? 's' : ''} · {totalChunks} chunks
          </span>
        </div>
        <div className="divide-y divide-am-border">
          {docs.map((d, i) => (
            <div key={i} className="flex items-center gap-4 px-5 py-3.5 group">
              <div className="w-7 h-7 rounded-lg bg-blue-50 flex items-center justify-center flex-shrink-0">
                <FileText size={13} className="text-am-blue" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-xs font-medium text-am-ink truncate">{d.titulo}</div>
                <div className="flex items-center gap-2 mt-0.5">
                  <span className="text-[9px] font-bold text-am-blue uppercase tracking-wider bg-blue-50
                    px-1.5 py-px rounded">
                    {d.tipo}
                  </span>
                  <span className="text-[10px] text-am-muted">{d.chunks} chunks</span>
                </div>
              </div>
              {uploaded.includes(d.titulo) && (
                <CheckCircle size={14} className="text-am-green flex-shrink-0" />
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Upload zone */}
      <div
        className={`relative rounded-xl border-2 border-dashed p-8 text-center transition-colors
          ${dragging ? 'border-am-blue bg-blue-50' : 'border-am-blue-light hover:border-am-blue hover:bg-am-surface'}`}
        onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); handleFiles(e.dataTransfer.files) }}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.txt"
          multiple
          className="hidden"
          onChange={(e) => handleFiles(e.target.files)}
        />
        <div className="flex flex-col items-center gap-3">
          <div className={`w-10 h-10 rounded-xl flex items-center justify-center
            ${dragging ? 'bg-am-blue text-white' : 'bg-am-surface text-am-muted'}`}
          >
            <Upload size={18} />
          </div>
          <div>
            <div className="text-sm font-semibold text-am-secondary">
              {dragging ? 'Solte o arquivo aqui' : 'Adicionar documento ao escritório'}
            </div>
            <div className="text-xs text-am-muted mt-1">PDF ou TXT — petições, teses, jurisprudências</div>
          </div>
          <button
            onClick={() => inputRef.current?.click()}
            className="px-5 py-2 bg-am-blue text-white text-xs font-semibold rounded-lg
              hover:bg-am-blue-hover transition-colors"
          >
            Selecionar arquivo
          </button>
        </div>
      </div>
    </div>
  )
}
