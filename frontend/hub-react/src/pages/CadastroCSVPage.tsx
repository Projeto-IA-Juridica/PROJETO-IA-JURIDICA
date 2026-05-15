import { useState, useRef, useCallback, type DragEvent, type ChangeEvent } from 'react'
import {
  ArrowLeft, Upload, FileText, CheckCircle2, AlertCircle,
  ChevronDown, ChevronUp, X, Info,
} from 'lucide-react'
import { api } from '../api/client'

/* ── Types ──────────────────────────────────────────────────────────────── */

interface PreviewItem {
  nome: string; telefone: string; cpf: string
  data_nascimento: string | null; profissao: string | null
  empresa: string | null; status: string
  numero_processo: string; polo_cliente: string | null
}

interface ImportError { linha: number; dados: string; motivo: string }

interface ApiResult {
  importados: number; atualizados: number
  processos_novos: number; processos_atualizados: number
  ignorados: number; erros: ImportError[]; preview: PreviewItem[]
}

type Step = 'upload' | 'preview' | 'done'

/* ── Column guide data ───────────────────────────────────────────────────── */

const COLS_OBRIGATORIAS = [
  { nome: 'nome',            desc: 'Nome completo do cliente'                                      },
  { nome: 'telefone',        desc: 'Celular com DDD, só números — ex: 11999998888'                 },
  { nome: 'numero_processo', desc: 'Formato CNJ — ex: 0000001-23.2024.8.26.0100'                   },
]

const COLS_OPCIONAIS = [
  { nome: 'polo_cliente',    desc: '"autor", "reu" ou "terceiro" (padrão: autor)'                  },
  { nome: 'cpf',             desc: 'Somente dígitos — ex: 12345678900'                             },
  { nome: 'data_nascimento', desc: 'DD/MM/AAAA ou AAAA-MM-DD'                                      },
  { nome: 'profissao',       desc: 'Profissão do cliente'                                           },
  { nome: 'empresa',         desc: 'Empresa onde trabalha'                                          },
  { nome: 'status',          desc: '"ativo" ou "inativo" (padrão: ativo)'                           },
]

/* ── Component ───────────────────────────────────────────────────────────── */

interface Props { onBack: () => void }

export default function CadastroCSVPage({ onBack }: Props) {
  const [step,       setStep]       = useState<Step>('upload')
  const [dragging,   setDragging]   = useState(false)
  const [file,       setFile]       = useState<File | null>(null)
  const [preview,    setPreview]    = useState<ApiResult | null>(null)
  const [result,     setResult]     = useState<ApiResult | null>(null)
  const [loading,    setLoading]    = useState(false)
  const [errorMsg,   setErrorMsg]   = useState('')
  const [showGuide,  setShowGuide]  = useState(false)
  const [showErrors, setShowErrors] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const sendFile = useCallback(async (f: File, isPreview: boolean): Promise<ApiResult> => {
    const form = new FormData()
    form.append('file', f)
    const { data } = await api.post<ApiResult>(
      `/admin/import/clientes?preview=${isPreview}`,
      form,
      { headers: { 'Content-Type': 'multipart/form-data' } },
    )
    return data
  }, [])

  const handleFile = useCallback(async (f: File) => {
    if (!f.name.toLowerCase().endsWith('.csv')) {
      setErrorMsg('Selecione um arquivo .csv')
      return
    }

    // Validação rápida das colunas obrigatórias antes de enviar
    const text = await f.text()
    const firstLine = text.split(/\r?\n/)[0] ?? ''
    const delim = firstLine.includes(';') ? ';' : ','
    const headers = firstLine.split(delim).map(h => h.trim().replace(/^"|"$/g, '').toLowerCase())
    const REQUIRED = ['nome', 'telefone', 'numero_processo']
    const missing = REQUIRED.filter(r => !headers.includes(r))
    if (missing.length) {
      setErrorMsg(`Coluna${missing.length > 1 ? 's' : ''} obrigatória${missing.length > 1 ? 's' : ''} não encontrada${missing.length > 1 ? 's' : ''}: ${missing.map(c => `"${c}"`).join(', ')}`)
      return
    }

    setFile(f)
    setErrorMsg('')
    setLoading(true)
    try {
      const data = await sendFile(f, true)
      setPreview(data)
      setStep('preview')
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setErrorMsg(msg ?? 'Erro ao enviar o arquivo. Tente novamente.')
    } finally {
      setLoading(false)
    }
  }, [sendFile])

  function onDrop(e: DragEvent) {
    e.preventDefault(); setDragging(false)
    const f = e.dataTransfer.files[0]
    if (f) handleFile(f)
  }
  function onFileInput(e: ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0]
    if (f) handleFile(f)
    e.target.value = ''
  }

  async function handleConfirm() {
    if (!file) return
    setLoading(true)
    try {
      const data = await sendFile(file, false)
      setResult(data)
      setStep('done')
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setErrorMsg(msg ?? 'Erro ao importar. Tente novamente.')
    } finally {
      setLoading(false)
    }
  }

  /* ── Layout ── */
  return (
    <div className="flex flex-col h-full overflow-hidden bg-am-bg">
      <div className="flex flex-col h-full w-full max-w-3xl mx-auto">

        {/* Header */}
        <div className="flex-shrink-0 px-4 pt-5 pb-4">
          <div className="flex items-center gap-3">
            <button onClick={onBack}
              className="w-8 h-8 rounded-xl flex items-center justify-center text-am-muted hover:text-am-ink transition-colors flex-shrink-0"
              style={{ border: '1px solid var(--color-am-border)', background: 'white' }}>
              <ArrowLeft size={14} />
            </button>
            <div className="w-9 h-9 rounded-2xl flex items-center justify-center flex-shrink-0"
              style={{ background: 'linear-gradient(135deg,#1248BE,#4A8ED4)', boxShadow: '0 4px 12px rgba(18,72,190,0.22)' }}>
              <FileText size={15} className="text-white" />
            </div>
            <div>
              <h1 className="text-sm font-bold text-am-ink">Importar clientes via CSV</h1>
              <p className="text-[11px] text-am-muted">
                {step === 'upload'  && 'Selecione o arquivo para começar'}
                {step === 'preview' && `${preview?.importados ?? 0} novos · ${preview?.atualizados ?? 0} atualizações`}
                {step === 'done'    && 'Importação concluída'}
              </p>
            </div>
          </div>

          {/* Step dots */}
          <div className="flex items-center gap-2 mt-4">
            {(['upload', 'preview', 'done'] as Step[]).map((s, i) => (
              <div key={s} className="flex items-center gap-2">
                <div className="w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold transition-all"
                  style={
                    step === s
                      ? { background: 'var(--color-am-blue)', color: '#fff' }
                      : (['upload', 'preview', 'done'].indexOf(step) > i)
                        ? { background: 'rgba(26,158,120,0.15)', color: '#1A9E78', border: '1px solid rgba(26,158,120,0.30)' }
                        : { background: 'rgba(12,30,48,0.06)', color: 'var(--color-am-muted)' }
                  }>
                  {(['upload', 'preview', 'done'].indexOf(step) > i) ? '✓' : i + 1}
                </div>
                {i < 2 && <div className="h-px w-6 flex-shrink-0" style={{ background: 'var(--color-am-border)' }} />}
              </div>
            ))}
          </div>
        </div>

        {/* Conteúdo */}
        <div className="flex-1 overflow-y-auto px-4 pb-6 flex flex-col gap-4">

          {/* ── UPLOAD ── */}
          {step === 'upload' && (
            <>
              {/* Drop zone */}
              <button
                type="button"
                onClick={() => fileRef.current?.click()}
                onDragOver={e => { e.preventDefault(); setDragging(true) }}
                onDragLeave={() => setDragging(false)}
                onDrop={onDrop}
                disabled={loading}
                className="w-full rounded-2xl flex flex-col items-center justify-center gap-3 py-12 transition-all"
                style={{
                  border:     `2px dashed ${dragging ? 'var(--color-am-blue)' : 'var(--color-am-border)'}`,
                  background: dragging ? 'rgba(18,72,190,0.04)' : 'white',
                  cursor:     loading ? 'not-allowed' : 'pointer',
                  opacity:    loading ? 0.6 : 1,
                }}>
                {loading
                  ? <span className="w-8 h-8 rounded-full border-2 border-am-blue border-t-transparent animate-spin" />
                  : (
                    <>
                      <div className="w-12 h-12 rounded-2xl flex items-center justify-center"
                        style={{ background: 'rgba(18,72,190,0.08)' }}>
                        <Upload size={20} style={{ color: 'var(--color-am-blue)' }} />
                      </div>
                      <div className="text-center">
                        <p className="text-sm font-semibold text-am-ink">Arraste o arquivo CSV aqui</p>
                        <p className="text-xs text-am-muted mt-1">ou clique para selecionar</p>
                      </div>
                      <span className="text-[11px] px-3 py-1 rounded-full font-semibold"
                        style={{ background: 'rgba(18,72,190,0.08)', color: 'var(--color-am-blue)' }}>
                        .csv · máx. 5 MB
                      </span>
                    </>
                  )
                }
              </button>
              <input ref={fileRef} type="file" accept=".csv,text/csv" className="hidden" onChange={onFileInput} />

              {errorMsg && (
                <div className="flex items-center gap-2 px-4 py-3 rounded-xl text-xs font-medium"
                  style={{ background: 'rgba(200,48,48,0.07)', border: '1px solid rgba(200,48,48,0.18)', color: '#C83030' }}>
                  <AlertCircle size={14} className="flex-shrink-0" /> {errorMsg}
                </div>
              )}

              {/* Guia de colunas */}
              <div className="rounded-2xl overflow-hidden" style={{ border: '1px solid var(--color-am-border)' }}>
                <button
                  type="button"
                  onClick={() => setShowGuide(v => !v)}
                  className="w-full flex items-center justify-between px-4 py-3 text-left"
                  style={{ background: 'white', cursor: 'pointer' }}>
                  <div className="flex items-center gap-2">
                    <Info size={13} style={{ color: 'var(--color-am-blue)' }} />
                    <span className="text-xs font-semibold text-am-ink">Como montar o CSV</span>
                  </div>
                  {showGuide ? <ChevronUp size={14} className="text-am-muted" /> : <ChevronDown size={14} className="text-am-muted" />}
                </button>

                {showGuide && (
                  <div className="px-4 pb-4 pt-0" style={{ background: 'white', borderTop: '1px solid var(--color-am-border)' }}>

                    <p className="text-[11px] text-am-muted mt-3 mb-3 leading-relaxed">
                      A primeira linha do arquivo deve ter os nomes das colunas exatamente como abaixo.
                      O sistema aceita vírgula <strong>(,)</strong> ou ponto-e-vírgula <strong>(;)</strong> como separador.
                    </p>

                    {/* Obrigatórias */}
                    <p className="text-[10px] font-bold text-am-secondary uppercase tracking-wider mb-2">Obrigatórias</p>
                    <div className="flex flex-col gap-1.5 mb-4">
                      {COLS_OBRIGATORIAS.map(c => (
                        <div key={c.nome} className="flex items-start gap-3">
                          <code className="text-[11px] font-bold px-2 py-0.5 rounded-md flex-shrink-0"
                            style={{ background: 'rgba(18,72,190,0.08)', color: 'var(--color-am-blue)' }}>
                            {c.nome}
                          </code>
                          <span className="text-[11px] text-am-muted leading-relaxed pt-0.5">{c.desc}</span>
                        </div>
                      ))}
                    </div>

                    {/* Opcionais */}
                    <p className="text-[10px] font-bold text-am-secondary uppercase tracking-wider mb-2">Opcionais</p>
                    <div className="flex flex-col gap-1.5 mb-4">
                      {COLS_OPCIONAIS.map(c => (
                        <div key={c.nome} className="flex items-start gap-3">
                          <code className="text-[11px] font-mono px-2 py-0.5 rounded-md flex-shrink-0"
                            style={{ background: 'rgba(12,30,48,0.05)', color: 'var(--color-am-secondary)' }}>
                            {c.nome}
                          </code>
                          <span className="text-[11px] text-am-muted leading-relaxed pt-0.5">{c.desc}</span>
                        </div>
                      ))}
                    </div>

                    {/* Dica processo */}
                    <div className="flex items-start gap-2 px-3 py-2.5 rounded-xl"
                      style={{ background: 'rgba(18,72,190,0.05)', border: '1px solid rgba(18,72,190,0.15)' }}>
                      <Info size={12} className="flex-shrink-0 mt-0.5" style={{ color: 'var(--color-am-blue)' }} />
                      <p className="text-[11px] leading-relaxed" style={{ color: 'var(--color-am-blue)' }}>
                        O <strong>numero_processo</strong> é obrigatório. O amicus cria e monitora o processo automaticamente — tribunal, vara e andamentos são buscados no DataJud na próxima execução.
                      </p>
                    </div>

                    {/* Exemplo */}
                    <p className="text-[10px] font-bold text-am-secondary uppercase tracking-wider mt-4 mb-2">Exemplo</p>
                    <div className="overflow-x-auto rounded-xl" style={{ border: '1px solid var(--color-am-border)' }}>
                      <table className="w-full text-[11px]">
                        <thead style={{ background: 'rgba(12,30,48,0.04)' }}>
                          <tr>
                            {['nome', 'telefone', 'numero_processo'].map(h => (
                              <th key={h} className="px-3 py-2 text-left font-bold text-am-secondary whitespace-nowrap">{h}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          <tr style={{ borderTop: '1px solid var(--color-am-border)' }}>
                            <td className="px-3 py-2 text-am-ink">João da Silva</td>
                            <td className="px-3 py-2 text-am-ink">11999998888</td>
                            <td className="px-3 py-2 text-am-muted font-mono text-[10px]">0000001-23.2024.8.26.0100</td>
                          </tr>
                          <tr style={{ borderTop: '1px solid var(--color-am-border)' }}>
                            <td className="px-3 py-2 text-am-ink">Maria Oliveira</td>
                            <td className="px-3 py-2 text-am-ink">21988887777</td>
                            <td className="px-3 py-2 text-am-muted italic">—</td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            </>
          )}

          {/* ── PREVIEW ── */}
          {step === 'preview' && preview && (
            <>
              {/* Stats */}
              <div className="grid grid-cols-2 gap-3">
                <StatCard value={preview.importados} label="Novos clientes" color="#1A9E78" />
                <StatCard value={preview.atualizados} label="Serão atualizados" color="var(--color-am-blue)" />
                {preview.processos_novos > 0 && (
                  <StatCard value={preview.processos_novos} label="Processos novos" color="var(--color-am-blue)" />
                )}
                {preview.erros.length > 0 && (
                  <StatCard value={preview.erros.length} label="Linhas com erro" color="#C83030" />
                )}
              </div>

              {/* Erros colapsável */}
              {preview.erros.length > 0 && (
                <div className="rounded-2xl overflow-hidden" style={{ border: '1px solid rgba(200,48,48,0.22)' }}>
                  <button
                    type="button"
                    onClick={() => setShowErrors(v => !v)}
                    className="w-full flex items-center justify-between px-4 py-3"
                    style={{ background: 'rgba(200,48,48,0.05)', cursor: 'pointer' }}>
                    <div className="flex items-center gap-2">
                      <AlertCircle size={13} style={{ color: '#C83030' }} />
                      <span className="text-xs font-semibold" style={{ color: '#C83030' }}>
                        {preview.erros.length} linha{preview.erros.length !== 1 ? 's' : ''} com erro (não serão importadas)
                      </span>
                    </div>
                    {showErrors ? <ChevronUp size={14} style={{ color: '#C83030' }} /> : <ChevronDown size={14} style={{ color: '#C83030' }} />}
                  </button>
                  {showErrors && (
                    <div className="flex flex-col divide-y bg-white" style={{ borderTop: '1px solid rgba(200,48,48,0.15)' }}>
                      {preview.erros.map((err, i) => (
                        <div key={i} className="px-4 py-2.5">
                          <span className="text-[10px] font-bold" style={{ color: '#C83030' }}>Linha {err.linha}</span>
                          <p className="text-[11px] text-am-muted mt-0.5">{err.motivo}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Tabela preview */}
              {preview.preview.length > 0 && (
                <div className="rounded-2xl overflow-hidden" style={{ border: '1px solid var(--color-am-border)' }}>
                  <div className="px-4 py-2.5" style={{ background: 'rgba(12,30,48,0.03)', borderBottom: '1px solid var(--color-am-border)' }}>
                    <p className="text-[11px] font-bold text-am-secondary uppercase tracking-wider">
                      Pré-visualização ({Math.min(preview.preview.length, 8)} de {preview.preview.length})
                    </p>
                  </div>
                  <div className="overflow-x-auto bg-white">
                    <table className="w-full text-xs">
                      <thead>
                        <tr style={{ borderBottom: '1px solid var(--color-am-border)' }}>
                          {['Nome', 'Telefone', 'Processo', 'Status'].map(h => (
                            <th key={h} className="px-4 py-2.5 text-left font-semibold text-am-secondary whitespace-nowrap">{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {preview.preview.slice(0, 8).map((row, i) => (
                          <tr key={i} style={{ borderBottom: i < 7 ? '1px solid var(--color-am-border)' : undefined }}>
                            <td className="px-4 py-2.5 font-medium text-am-ink">{row.nome}</td>
                            <td className="px-4 py-2.5 text-am-muted font-mono text-[11px]">{row.telefone}</td>
                            <td className="px-4 py-2.5 text-am-muted font-mono text-[10px]">
                              {row.numero_processo !== '(não informado)' ? row.numero_processo : <span className="italic">—</span>}
                            </td>
                            <td className="px-4 py-2.5">
                              <span className="text-[10px] font-semibold px-2 py-0.5 rounded-md"
                                style={row.status === 'ativo'
                                  ? { color: '#1A9E78', background: 'rgba(26,158,120,0.08)' }
                                  : { color: 'var(--color-am-muted)', background: 'rgba(12,30,48,0.05)' }}>
                                {row.status}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {errorMsg && (
                <div className="flex items-center gap-2 px-4 py-3 rounded-xl text-xs font-medium"
                  style={{ background: 'rgba(200,48,48,0.07)', border: '1px solid rgba(200,48,48,0.18)', color: '#C83030' }}>
                  <AlertCircle size={14} className="flex-shrink-0" /> {errorMsg}
                </div>
              )}

              {/* Ações */}
              <div className="flex gap-3">
                <button onClick={() => { setStep('upload'); setPreview(null); setErrorMsg('') }}
                  className="flex items-center gap-1.5 px-4 py-2.5 rounded-xl text-xs font-semibold text-am-secondary flex-shrink-0"
                  style={{ background: 'white', border: '1px solid var(--color-am-border)', fontFamily: 'var(--font-sans)', cursor: 'pointer' }}>
                  <X size={12} /> Trocar arquivo
                </button>
                <button
                  onClick={handleConfirm}
                  disabled={loading || (preview.importados + preview.atualizados) === 0}
                  className="press flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl font-bold text-sm text-white"
                  style={{
                    background:   'linear-gradient(135deg,#1248BE 0%,#3A7AB8 100%)',
                    boxShadow:    '0 4px 16px rgba(18,72,190,0.22)',
                    opacity:      loading || (preview.importados + preview.atualizados) === 0 ? 0.5 : 1,
                    cursor:       loading || (preview.importados + preview.atualizados) === 0 ? 'not-allowed' : 'pointer',
                    fontFamily:   'var(--font-sans)', border: 'none', fontSize: 13,
                  }}>
                  {loading
                    ? <><span className="w-4 h-4 rounded-full border-2 border-white border-t-transparent animate-spin" /> Importando...</>
                    : <>Confirmar importação ({preview.importados + preview.atualizados})</>
                  }
                </button>
              </div>
            </>
          )}

          {/* ── DONE ── */}
          {step === 'done' && result && (
            <div className="flex flex-col items-center gap-6 py-10">
              <div className="w-16 h-16 rounded-full flex items-center justify-center"
                style={{ background: 'rgba(26,158,120,0.10)', border: '1.5px solid rgba(26,158,120,0.25)' }}>
                <CheckCircle2 size={28} style={{ color: '#1A9E78' }} />
              </div>

              <div className="text-center">
                <h2 className="text-base font-bold text-am-ink mb-1">Importação concluída!</h2>
                <p className="text-xs text-am-muted">Os clientes já estão disponíveis na lista.</p>
              </div>

              <div className="flex gap-3 flex-wrap justify-center">
                {result.importados > 0 && (
                  <StatCard value={result.importados} label="Importados" color="#1A9E78" />
                )}
                {result.atualizados > 0 && (
                  <StatCard value={result.atualizados} label="Atualizados" color="var(--color-am-blue)" />
                )}
                {result.processos_novos > 0 && (
                  <StatCard value={result.processos_novos} label="Processos criados" color="var(--color-am-blue)" />
                )}
                {result.erros.length > 0 && (
                  <StatCard value={result.erros.length} label="Com erro" color="#C83030" />
                )}
              </div>

              <div className="flex gap-3">
                <button onClick={onBack}
                  className="press px-5 py-2.5 rounded-xl text-xs font-semibold text-white"
                  style={{ background: 'linear-gradient(135deg,#1248BE,#3A7AB8)', fontFamily: 'var(--font-sans)', border: 'none', cursor: 'pointer' }}>
                  Ver clientes
                </button>
                <button onClick={() => { setStep('upload'); setPreview(null); setResult(null); setFile(null) }}
                  className="px-5 py-2.5 rounded-xl text-xs font-semibold text-am-secondary"
                  style={{ background: 'white', border: '1px solid var(--color-am-border)', fontFamily: 'var(--font-sans)', cursor: 'pointer' }}>
                  Importar outro
                </button>
              </div>
            </div>
          )}

        </div>
      </div>
    </div>
  )
}

/* ── StatCard ────────────────────────────────────────────────────────────── */

function StatCard({ value, label, color }: { value: number; label: string; color: string }) {
  return (
    <div className="flex flex-col items-center px-5 py-4 rounded-2xl flex-1"
      style={{ background: 'white', border: '1px solid var(--color-am-border)', minWidth: 110 }}>
      <span className="text-2xl font-black" style={{ color }}>{value}</span>
      <span className="text-[11px] text-am-muted mt-1 text-center">{label}</span>
    </div>
  )
}
