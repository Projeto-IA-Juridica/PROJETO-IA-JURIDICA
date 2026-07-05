import { useQuery } from '@tanstack/react-query'
import { Calendar, Clock } from 'lucide-react'
import { listarAgendamentos, type Agendamento } from '../../api/agendamentos'

function labelDia(iso: string): string {
  const d = new Date(iso)
  const hoje = new Date(); hoje.setHours(0, 0, 0, 0)
  const amanha = new Date(hoje); amanha.setDate(amanha.getDate() + 1)
  const dia = new Date(d); dia.setHours(0, 0, 0, 0)

  const hora = d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
  if (dia.getTime() === hoje.getTime()) return `Hoje, ${hora}`
  if (dia.getTime() === amanha.getTime()) return `Amanhã, ${hora}`
  const semana = d.toLocaleDateString('pt-BR', { weekday: 'short' }).replace('.', '')
  return `${semana.charAt(0).toUpperCase()}${semana.slice(1)} ${d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' })}, ${hora}`
}

interface Props {
  onVerAgenda: (semanaISO: string) => void
  onVerPendentes: () => void
}

export default function ProximasReunioes({ onVerAgenda, onVerPendentes }: Props) {
  const { data: confirmadas } = useQuery({
    queryKey: ['agendamentos-proximas'],
    queryFn: () => listarAgendamentos({
      status: 'confirmado',
      data_inicio: new Date().toISOString(),
      page_size: 50,
    }),
    staleTime: 30_000,
    refetchInterval: 60_000,
  })

  const { data: pendentes } = useQuery({
    queryKey: ['agendamentos-pendentes'],
    queryFn: () => listarAgendamentos({ status: 'aguardando_advogado' }),
    staleTime: 10_000,
    refetchInterval: 30_000,
  })

  const proximas: Agendamento[] = (confirmadas ?? [])
    .filter(a => a.data_hora_inicio)
    .sort((a, b) => (a.data_hora_inicio ?? '').localeCompare(b.data_hora_inicio ?? ''))
    .slice(0, 3)

  const totalPendentes = pendentes?.length ?? 0

  // Sem reuniões próximas e sem pendentes → bloco oculto (não ocupa espaço)
  if (proximas.length === 0 && totalPendentes === 0) return null

  return (
    <div className="flex-shrink-0 bg-white rounded-2xl overflow-hidden card-shadow card-border-hover"
      style={{ border: '1px solid var(--color-am-border)' }}>
      <div className="flex items-center justify-between px-4 py-3"
        style={{ borderBottom: '1px solid var(--color-am-border)', background: 'rgba(12,30,48,0.02)' }}>
        <div className="flex items-center gap-2">
          <Calendar size={13} className="text-am-blue" />
          <span className="text-[10px] font-bold uppercase tracking-wider text-am-secondary">
            Próximas reuniões
          </span>
        </div>
        {totalPendentes > 0 && (
          <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full text-white" style={{ background: '#D08010' }}>
            {totalPendentes}
          </span>
        )}
      </div>

      <div className="p-2">
        {proximas.map(ag => (
          <button
            key={ag.id}
            onClick={() => ag.data_hora_inicio && onVerAgenda(ag.data_hora_inicio)}
            title="Abrir na agenda semanal"
            className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-left hover:bg-am-bg transition-colors press">
            <span className="text-[11px] font-bold whitespace-nowrap" style={{ color: 'var(--color-am-blue)', minWidth: 92 }}>
              {ag.data_hora_inicio ? labelDia(ag.data_hora_inicio) : '—'}
            </span>
            <span className="text-[11px] text-am-muted">·</span>
            <span className="text-xs font-semibold text-am-ink truncate">
              {ag.cliente_nome ?? `Cliente #${ag.cliente_id}`}
            </span>
          </button>
        ))}

        {proximas.length === 0 && (
          <p className="px-3 py-2.5 text-[11px] text-am-muted">Nenhuma reunião confirmada nos próximos dias.</p>
        )}

        {totalPendentes > 0 && (
          <div className="flex items-center justify-between gap-2 mx-1 mt-1 px-3 py-2 rounded-xl"
            style={{ background: 'rgba(208,128,16,0.07)', border: '1px solid rgba(208,128,16,0.25)' }}>
            <span className="flex items-center gap-1.5 text-[11px] font-semibold" style={{ color: '#B06D0A' }}>
              <Clock size={11} />
              {totalPendentes === 1 ? '1 aguardando aprovação' : `${totalPendentes} aguardando aprovação`}
            </span>
            <button
              onClick={onVerPendentes}
              className="press px-2.5 py-1 rounded-lg text-[10px] font-bold text-white"
              style={{ background: '#D08010' }}>
              Ver
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
