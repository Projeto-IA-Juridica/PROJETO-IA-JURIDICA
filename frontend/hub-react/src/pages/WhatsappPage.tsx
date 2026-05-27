import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, MessageSquare, Loader2, RefreshCcw, AlertTriangle, QrCode } from 'lucide-react'
import { conectarWhatsapp, statusWhatsapp, extractDetail } from '../api/onboarding'
import { fetchCsrfToken } from '../api/auth'

function SectionTitle({ title, desc }: { title: string; desc: string }) {
  return (
    <div className="flex items-center gap-3">
      <div className="w-10 h-10 rounded-2xl flex items-center justify-center flex-shrink-0" style={{ background: 'rgba(58,122,184,0.1)', border: '1px solid rgba(58,122,184,0.18)' }}>
        <MessageSquare size={18} className="text-am-blue" />
      </div>
      <div>
        <h2 className="text-xl font-extrabold tracking-tight text-am-ink">{title}</h2>
        <p className="text-xs text-am-muted mt-0.5">{desc}</p>
      </div>
    </div>
  )
}

function normalizeQrCode(value: unknown): string | null {
  if (!value) return null
  if (typeof value === 'string') {
    return value.startsWith('data:') ? value : `data:image/png;base64,${value}`
  }
  if (typeof value === 'object') {
    const candidate = value as { base64?: unknown; code?: unknown; qr?: unknown; qrcode?: unknown }
    const nested = candidate.base64 ?? candidate.code ?? candidate.qr ?? candidate.qrcode
    if (typeof nested === 'string' && nested) {
      return nested.startsWith('data:') ? nested : `data:image/png;base64,${nested}`
    }
  }
  return null
}

export default function WhatsappPage() {
  const qc = useQueryClient()
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const [qrCode, setQrCode] = useState<string | null>(null)
  const [started, setStarted] = useState(false)
  const [apiError, setApiError] = useState<string | null>(null)

  const { data: initialStatus, isLoading: statusLoading } = useQuery({
    queryKey: ['whatsapp-status'],
    queryFn: statusWhatsapp,
    staleTime: 20_000,
  })

  const connected = initialStatus?.connected ?? false
  const state = initialStatus?.state ?? 'unknown'

  const mutation = useMutation({
    mutationFn: async () => {
      await fetchCsrfToken().catch(() => null)
      return conectarWhatsapp()
    },
    onSuccess: (result) => {
      const normalized = normalizeQrCode(result.qr_code)
      setQrCode(normalized)
      setStarted(true)
      setApiError(null)
      qc.invalidateQueries({ queryKey: ['whatsapp-status'] })
    },
    onError: (err) => {
      const detail = extractDetail(err)
      setApiError(detail || 'Não foi possível gerar o QR Code agora.')
    },
  })

  const syncStatus = async () => {
    try {
      const next = await statusWhatsapp()
      qc.setQueryData(['whatsapp-status'], next)
      if (next.connected) {
        setQrCode(null)
        setStarted(false)
      }
    } catch {
      /* silencioso: a tela continua funcionando mesmo sem polling */
    }
  }

  useEffect(() => {
    if (!started || connected) return
    pollingRef.current = setInterval(syncStatus, 3000)
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current)
      pollingRef.current = null
    }
  }, [connected, started])

  useEffect(() => {
    if (connected) {
      setQrCode(null)
      setStarted(false)
    }
  }, [connected])

  useEffect(() => {
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current)
    }
  }, [])

  const statusTone = useMemo(() => {
    if (connected) return { label: 'Conectado', color: '#1A9E78', bg: 'rgba(26,158,120,0.08)' }
    if (started) return { label: 'Aguardando leitura', color: '#D08010', bg: 'rgba(208,128,16,0.08)' }
    return { label: 'Desconectado', color: '#C83030', bg: 'rgba(200,48,48,0.08)' }
  }, [connected, started])

  const canGenerate = !mutation.isPending && !connected

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="p-4 sm:p-6 max-w-5xl mx-auto space-y-6 page-enter">
        <div className="flex items-center justify-between flex-wrap gap-4">
          <SectionTitle
            title="WhatsApp"
            desc="Conecte a Evolution API, gere o QR Code e monitore o estado da instância em tempo real."
          />

          <div className="flex items-center gap-2 px-3 py-2 rounded-xl border text-xs font-bold" style={{ background: statusTone.bg, color: statusTone.color, borderColor: 'rgba(58,122,184,0.18)' }}>
            <span className="w-2 h-2 rounded-full" style={{ background: statusTone.color }} />
            {statusTone.label}
          </div>
        </div>

        {apiError && (
          <div className="flex items-start gap-2 px-4 py-3 rounded-xl text-xs" style={{ background: 'rgba(200,48,48,0.06)', border: '1px solid rgba(200,48,48,0.2)', color: '#C83030' }}>
            <AlertTriangle size={14} className="flex-shrink-0 mt-0.5" />
            {apiError}
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-[1.25fr_0.75fr] gap-5">
          <div className="bg-white rounded-2xl card-shadow border border-am-border p-5 card-border-hover space-y-4">
            <div className="flex items-center gap-2 text-sm font-bold text-am-ink">
              <QrCode size={16} className="text-am-blue" /> QR Code da instância
            </div>

            <div className="min-h-[360px] rounded-2xl border border-dashed flex items-center justify-center p-6" style={{ background: 'linear-gradient(180deg, rgba(18,72,190,0.03), rgba(18,72,190,0.01))', borderColor: 'rgba(58,122,184,0.22)' }}>
              {mutation.isPending || statusLoading ? (
                <div className="flex flex-col items-center gap-3 text-am-muted">
                  <Loader2 size={24} className="animate-spin text-am-blue" />
                  <p className="text-xs">Preparando a conexão…</p>
                </div>
              ) : qrCode ? (
                <div className="flex flex-col items-center gap-4 text-center">
                  <img src={qrCode} alt="QR Code WhatsApp" className="w-64 h-64 object-contain rounded-2xl bg-white p-4 border border-am-border" />
                  <div>
                    <p className="text-sm font-bold text-am-ink">Escaneie com o WhatsApp do escritório</p>
                    <p className="text-xs text-am-muted mt-1">WhatsApp → Aparelhos conectados → Conectar aparelho</p>
                  </div>
                </div>
              ) : connected ? (
                <div className="flex flex-col items-center gap-3 text-center">
                  <div className="w-16 h-16 rounded-full flex items-center justify-center" style={{ background: 'rgba(26,158,120,0.1)', border: '1px solid rgba(26,158,120,0.2)' }}>
                    <CheckCircle2 size={30} className="text-green-600" />
                  </div>
                  <p className="text-sm font-bold text-am-ink">WhatsApp já está conectado</p>
                  <p className="text-xs text-am-muted max-w-sm">Se quiser recriar a instância, use o botão abaixo para gerar um novo QR Code.</p>
                </div>
              ) : (
                <div className="flex flex-col items-center gap-3 text-center text-am-muted">
                  <MessageSquare size={24} className="text-am-blue" />
                  <p className="text-sm font-bold text-am-ink">Nenhum QR Code gerado ainda</p>
                  <p className="text-xs max-w-md">Clique em "Gerar QR Code" para pedir a conexão à Evolution API e acompanhar o status da instância.</p>
                </div>
              )}
            </div>

            <div className="flex flex-wrap gap-3">
              <button
                type="button"
                onClick={() => mutation.mutate()}
                disabled={!canGenerate}
                className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl text-white text-xs font-bold transition-fast"
                style={{ background: 'var(--color-am-blue)', opacity: canGenerate ? 1 : 0.65, cursor: canGenerate ? 'pointer' : 'not-allowed' }}
              >
                {mutation.isPending ? <Loader2 size={13} className="animate-spin" /> : <QrCode size={13} />}
                {connected ? 'Gerar novo QR Code' : 'Gerar QR Code'}
              </button>

              <button
                type="button"
                onClick={syncStatus}
                className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold border transition-fast"
                style={{ color: 'var(--color-am-secondary)', borderColor: 'var(--color-am-border)', background: 'var(--color-am-bg)' }}
              >
                <RefreshCcw size={13} /> Atualizar status
              </button>
            </div>
          </div>

          <div className="space-y-5">
            <div className="bg-white rounded-2xl card-shadow border border-am-border p-5 card-border-hover">
              <div className="text-sm font-bold text-am-ink mb-3">Status da instância</div>
              <div className="space-y-3 text-xs text-am-secondary">
                <div className="flex items-center justify-between gap-3">
                  <span>Conectado</span>
                  <strong className="text-am-ink">{connected ? 'Sim' : 'Não'}</strong>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span>Estado técnico</span>
                  <strong className="text-am-ink">{state}</strong>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span>Polling</span>
                  <strong className="text-am-ink">{started && !connected ? 'Ativo' : 'Inativo'}</strong>
                </div>
              </div>
            </div>

            <div className="bg-white rounded-2xl card-shadow border border-am-border p-5 card-border-hover space-y-3">
              <div className="text-sm font-bold text-am-ink">Como funciona</div>
              <ol className="space-y-2 text-xs text-am-secondary list-decimal list-inside">
                <li>O backend chama a Evolution API usando as credenciais do `.env`.</li>
                <li>A Evolution retorna o QR Code da instância.</li>
                <li>Você escaneia o QR no celular do escritório.</li>
                <li>O painel faz polling até o estado virar conectado.</li>
              </ol>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}