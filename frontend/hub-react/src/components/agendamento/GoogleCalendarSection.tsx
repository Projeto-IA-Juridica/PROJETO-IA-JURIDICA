import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Calendar, CheckCircle, ExternalLink, Loader2, Unlink } from 'lucide-react'
import {
  desconectarGoogleCalendar,
  fetchGoogleCalendarAuthUrl,
  fetchGoogleCalendarStatus,
} from '../../api/googleCalendar'

function SectionTitle({ icon, label, desc }: { icon: React.ReactNode; label: string; desc: string }) {
  return (
    <div className="flex items-center gap-3 mb-4">
      <div className="w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0"
        style={{ background: 'rgba(58,122,184,0.1)', border: '1px solid rgba(58,122,184,0.2)' }}>
        <span className="text-am-blue">{icon}</span>
      </div>
      <div>
        <div className="text-sm font-bold text-am-ink">{label}</div>
        <div className="text-[10px] text-am-muted">{desc}</div>
      </div>
    </div>
  )
}

export default function GoogleCalendarSection() {
  const qc = useQueryClient()
  const [erro, setErro] = useState<string | null>(null)
  const [redirecionando, setRedirecionando] = useState(false)

  const { data: status, isLoading } = useQuery({
    queryKey: ['google-calendar-status'],
    queryFn: fetchGoogleCalendarStatus,
    staleTime: 30_000,
  })

  async function conectar() {
    setErro(null)
    setRedirecionando(true)
    try {
      const url = await fetchGoogleCalendarAuthUrl()
      window.location.href = url // consentimento Google → callback → volta ao app
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setErro(detail ?? 'Não foi possível iniciar a conexão. Tente novamente.')
      setRedirecionando(false)
    }
  }

  const desconectarMut = useMutation({
    mutationFn: desconectarGoogleCalendar,
    onSuccess: () => {
      setErro(null)
      qc.invalidateQueries({ queryKey: ['google-calendar-status'] })
    },
    onError: () => setErro('Erro ao desconectar. Tente novamente.'),
  })

  // Servidor sem credenciais Google → seção oculta (não confunde o usuário)
  if (!isLoading && status && !status.configurado) return null

  return (
    <div className="bg-white rounded-2xl card-shadow border border-am-border p-5 card-border-hover">
      <SectionTitle
        icon={<Calendar size={14} />}
        label="Google Calendar"
        desc="Reuniões confirmadas entram na agenda do Google; horários ocupados lá não são oferecidos pela IA"
      />

      {isLoading ? (
        <div className="flex items-center justify-center h-16">
          <Loader2 size={18} className="animate-spin text-am-muted" />
        </div>
      ) : status?.conectado ? (
        <div className="space-y-3">
          <div className="flex items-center justify-between flex-wrap gap-3">
            <div className="flex items-center gap-2">
              <CheckCircle size={14} style={{ color: '#1A9E78' }} />
              <div>
                <p className="text-xs font-bold text-am-ink">Agenda conectada</p>
                <p className="text-[10px] text-am-muted">
                  {status.calendar_id === 'primary' ? 'Agenda principal' : status.calendar_id}
                  {status.conectado_em &&
                    ` · desde ${new Date(status.conectado_em).toLocaleDateString('pt-BR')}`}
                </p>
              </div>
            </div>
            <button
              type="button"
              disabled={desconectarMut.isPending}
              onClick={() => desconectarMut.mutate()}
              className="press flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold"
              style={{
                background: 'rgba(200,48,48,0.05)', color: '#C83030',
                border: '1px solid rgba(200,48,48,0.22)',
                opacity: desconectarMut.isPending ? 0.6 : 1,
              }}>
              {desconectarMut.isPending
                ? <Loader2 size={12} className="animate-spin" />
                : <Unlink size={12} />}
              Desconectar
            </button>
          </div>
          <p className="text-[10px] text-am-muted leading-relaxed">
            Se o escritório tem secretária, ela vê as reuniões confirmadas direto no Google Calendar —
            e o que ela marcar por lá bloqueia os horários oferecidos aos clientes.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          <p className="text-[11px] text-am-secondary leading-relaxed">
            Conecte a agenda do escritório: reuniões confirmadas viram eventos automaticamente
            e a IA nunca oferece um horário em que já exista compromisso no Google Calendar.
          </p>
          <button
            type="button"
            disabled={redirecionando}
            onClick={conectar}
            className="press flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold text-white"
            style={{
              background: 'linear-gradient(135deg,#1248BE,#3A7AB8)',
              opacity: redirecionando ? 0.6 : 1,
            }}>
            {redirecionando
              ? <><Loader2 size={13} className="animate-spin" /> Redirecionando…</>
              : <><ExternalLink size={13} /> Conectar Google Calendar</>}
          </button>
        </div>
      )}

      {erro && (
        <p className="text-[11px] font-medium mt-3" style={{ color: '#C83030' }}>{erro}</p>
      )}
    </div>
  )
}
