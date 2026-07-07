import { useEffect, useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'framer-motion'
import {
  AlertTriangle, Calendar, Check, ChevronLeft, ChevronRight,
  Clock, Settings, Loader2,
} from 'lucide-react'
import {
  confirmarAgendamento,
  fetchEventosAgenda,
  type Agendamento,
  type PrazoAgenda,
} from '../../api/agendamentos'
import AprovacaoCard, { labelHorario } from './AprovacaoCard'
import { useStreamConectado } from '../../hooks/useAgendamentoStream'

const DIAS_LABEL = ['SEG', 'TER', 'QUA', 'QUI', 'SEX', 'SÁB']

function mondayOf(d: Date): Date {
  const copy = new Date(d)
  copy.setHours(0, 0, 0, 0)
  const day = copy.getDay() // 0=domingo
  const diff = day === 0 ? -6 : 1 - day
  copy.setDate(copy.getDate() + diff)
  return copy
}

function addDays(d: Date, n: number): Date {
  const copy = new Date(d)
  copy.setDate(copy.getDate() + n)
  return copy
}

function isoDate(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

function fmtRangeSemana(inicio: Date): string {
  const fim = addDays(inicio, 5)
  const optsIni: Intl.DateTimeFormatOptions = { day: '2-digit', month: 'short' }
  const optsFim: Intl.DateTimeFormatOptions = { day: '2-digit', month: 'short', year: 'numeric' }
  return `${inicio.toLocaleDateString('pt-BR', optsIni)} — ${fim.toLocaleDateString('pt-BR', optsFim)}`
}

function horaLocal(iso: string): string {
  return new Date(iso).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
}

interface Props {
  /** semana solicitada externamente (ex: clique no widget do Painel) */
  semanaISO?: string | null
  navTs?: number
  onSelectCliente: (clienteId: number, tab: 'chat' | 'processo') => void
  onVerPendentes: () => void
  onGoConfig: () => void
}

export default function AgendaSemanal({ semanaISO, navTs, onSelectCliente, onVerPendentes, onGoConfig }: Props) {
  const qc = useQueryClient()
  const [weekStart, setWeekStart] = useState<Date>(() =>
    mondayOf(semanaISO ? new Date(semanaISO) : new Date()),
  )
  const [expandido, setExpandido] = useState<number | null>(null)

  /* Navegação externa (Painel → semana da reunião) */
  useEffect(() => {
    if (semanaISO) setWeekStart(mondayOf(new Date(semanaISO)))
  }, [semanaISO, navTs])

  const inicioISO = useMemo(() => {
    const d = new Date(weekStart)
    d.setHours(0, 0, 0, 0)
    return d.toISOString()
  }, [weekStart])

  const fimISO = useMemo(() => {
    const d = addDays(weekStart, 5)
    d.setHours(23, 59, 59, 999)
    return d.toISOString()
  }, [weekStart])

  const streamConectado = useStreamConectado()
  const { data, isLoading } = useQuery({
    queryKey: ['agendamentos-eventos', inicioISO],
    queryFn: () => fetchEventosAgenda(inicioISO, fimISO),
    // tempo real via SSE; polling é fallback (60s com stream, 15s sem)
    refetchInterval: streamConectado ? 60_000 : 15_000,
    staleTime: 5_000,
  })

  const confirmarMut = useMutation({
    mutationFn: (id: number) => confirmarAgendamento(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['agendamentos-eventos'] })
      qc.invalidateQueries({ queryKey: ['agendamentos-pendentes'] })
      qc.invalidateQueries({ queryKey: ['agendamentos-proximas'] })
    },
  })

  /* Agrupa itens por dia local (0=SEG … 5=SÁB) */
  const porDia = useMemo(() => {
    const dias: { agendamentos: Agendamento[]; prazos: PrazoAgenda[] }[] =
      Array.from({ length: 6 }, () => ({ agendamentos: [], prazos: [] }))
    const chaves = Array.from({ length: 6 }, (_, i) => isoDate(addDays(weekStart, i)))

    for (const ag of data?.agendamentos ?? []) {
      if (!ag.data_hora_inicio) continue
      const idx = chaves.indexOf(isoDate(new Date(ag.data_hora_inicio)))
      if (idx >= 0) dias[idx].agendamentos.push(ag)
    }
    for (const dia of dias) {
      dia.agendamentos.sort((a, b) =>
        (a.data_hora_inicio ?? '').localeCompare(b.data_hora_inicio ?? ''))
    }
    for (const p of data?.prazos ?? []) {
      const idx = chaves.indexOf(p.data)
      if (idx >= 0) dias[idx].prazos.push(p)
    }
    return dias
  }, [data, weekStart])

  const pendentesSemana = (data?.agendamentos ?? []).filter(a => a.status === 'aguardando_advogado')
  const semanaVazia = (data?.agendamentos ?? []).length === 0 && (data?.prazos ?? []).length === 0
  const hoje = isoDate(new Date())

  return (
    <div className="space-y-4 mt-2">

      {/* Navegação da semana */}
      <div className="flex items-center justify-center gap-3">
        <button
          onClick={() => setWeekStart(addDays(weekStart, -7))}
          aria-label="Semana anterior"
          className="press w-8 h-8 rounded-xl flex items-center justify-center text-am-secondary"
          style={{ background: 'white', border: '1px solid var(--color-am-border)' }}>
          <ChevronLeft size={14} />
        </button>
        <button
          onClick={() => setWeekStart(mondayOf(new Date()))}
          className="press px-4 py-1.5 rounded-xl text-xs font-bold text-am-ink min-w-[190px]"
          title="Voltar para a semana atual"
          style={{ background: 'white', border: '1px solid var(--color-am-border)' }}>
          {fmtRangeSemana(weekStart)}
        </button>
        <button
          onClick={() => setWeekStart(addDays(weekStart, 7))}
          aria-label="Próxima semana"
          className="press w-8 h-8 rounded-xl flex items-center justify-center text-am-secondary"
          style={{ background: 'white', border: '1px solid var(--color-am-border)' }}>
          <ChevronRight size={14} />
        </button>
      </div>

      {/* Banner de pendentes na semana */}
      {pendentesSemana.length > 0 && (
        <div className="flex items-center justify-between gap-3 px-4 py-3 rounded-2xl"
          style={{ background: 'rgba(208,128,16,0.07)', border: '1px solid rgba(208,128,16,0.28)' }}>
          <span className="flex items-center gap-2 text-xs font-semibold" style={{ color: '#B06D0A' }}>
            <Clock size={13} />
            {pendentesSemana.length === 1
              ? '1 reunião aguardando sua aprovação esta semana'
              : `${pendentesSemana.length} reuniões aguardando sua aprovação esta semana`}
          </span>
          <button
            onClick={onVerPendentes}
            className="press px-3 py-1.5 rounded-lg text-[11px] font-bold text-white flex-shrink-0"
            style={{ background: '#D08010' }}>
            Ver pendentes
          </button>
        </div>
      )}

      {isLoading && (
        <div className="flex items-center justify-center h-40">
          <Loader2 size={22} className="animate-spin text-am-muted" />
        </div>
      )}

      {/* Empty states */}
      {!isLoading && data && !data.tem_disponibilidade && (
        <div className="flex flex-col items-center gap-3 py-10 rounded-2xl bg-white card-shadow"
          style={{ border: '1px solid var(--color-am-border)' }}>
          <div className="w-12 h-12 rounded-2xl flex items-center justify-center"
            style={{ background: 'rgba(18,72,190,0.07)', border: '1px solid rgba(18,72,190,0.15)' }}>
            <Calendar size={20} style={{ color: 'var(--color-am-blue)' }} />
          </div>
          <p className="text-xs text-am-secondary text-center leading-relaxed max-w-xs">
            Configure seus horários para que a IA possa<br />sugerir reuniões automaticamente.
          </p>
          <button
            onClick={onGoConfig}
            className="press flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-bold text-white"
            style={{ background: 'linear-gradient(135deg,#1248BE,#3A7AB8)' }}>
            <Settings size={12} /> Configurar horários
          </button>
        </div>
      )}

      {!isLoading && data && data.tem_disponibilidade && semanaVazia && (
        <div className="flex flex-col items-center gap-2 py-10 rounded-2xl bg-white card-shadow"
          style={{ border: '1px solid var(--color-am-border)' }}>
          <Calendar size={20} className="text-am-muted" />
          <p className="text-xs text-am-muted">Semana livre. Que tal revisar seus horários de atendimento?</p>
          <button onClick={onGoConfig} className="press text-[11px] font-semibold" style={{ color: 'var(--color-am-blue)' }}>
            Abrir configurações →
          </button>
        </div>
      )}

      {/* Grade semanal */}
      {!isLoading && data && !semanaVazia && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
          {porDia.map((dia, i) => {
            const dataDia = addDays(weekStart, i)
            const ehHoje = isoDate(dataDia) === hoje
            return (
              <div key={i} className="rounded-2xl overflow-hidden flex flex-col min-h-[120px]"
                style={{
                  background: 'white',
                  border: ehHoje ? '1px solid rgba(18,72,190,0.35)' : '1px solid var(--color-am-border)',
                  boxShadow: ehHoje ? '0 2px 10px rgba(18,72,190,0.10)' : undefined,
                }}>
                <div className="px-3 py-2 text-center"
                  style={{ borderBottom: '1px solid var(--color-am-border)', background: ehHoje ? 'rgba(18,72,190,0.05)' : 'rgba(12,30,48,0.02)' }}>
                  <span className="text-[9px] font-bold uppercase tracking-widest"
                    style={{ color: ehHoje ? 'var(--color-am-blue)' : 'var(--color-am-muted)' }}>
                    {DIAS_LABEL[i]} {dataDia.getDate()}
                  </span>
                </div>

                <div className="flex-1 p-1.5 space-y-1.5">
                  {dia.agendamentos.map(ag => {
                    const confirmado = ag.status === 'confirmado'
                    const estaExpandido = expandido === ag.id
                    return (
                      <div key={ag.id}>
                        <button
                          onClick={() => confirmado
                            ? onSelectCliente(ag.cliente_id, 'chat')
                            : setExpandido(estaExpandido ? null : ag.id)}
                          title={confirmado ? 'Ver conversa que originou a reunião' : 'Ver detalhes da solicitação'}
                          className="w-full text-left rounded-xl px-2 py-1.5 press"
                          style={confirmado
                            ? { background: 'rgba(18,72,190,0.07)', border: '1px solid rgba(18,72,190,0.22)' }
                            : { background: 'rgba(208,128,16,0.08)', border: '1px solid rgba(208,128,16,0.30)' }}>
                          <p className="text-[10px] font-bold" style={{ color: confirmado ? 'var(--color-am-blue)' : '#B06D0A' }}>
                            {ag.data_hora_inicio ? horaLocal(ag.data_hora_inicio) : '—'}
                          </p>
                          <p className="text-[10px] font-semibold text-am-ink truncate">{ag.cliente_nome ?? `#${ag.cliente_id}`}</p>
                          <p className="text-[9px] font-medium" style={{ color: confirmado ? '#1A9E78' : '#B06D0A' }}>
                            {confirmado ? '✅ Confirmado' : '⏳ Aguardando'}
                          </p>
                        </button>
                        {!confirmado && !estaExpandido && (
                          <button
                            disabled={confirmarMut.isPending && confirmarMut.variables === ag.id}
                            onClick={() => confirmarMut.mutate(ag.id)}
                            className="press w-full mt-1 flex items-center justify-center gap-1 py-1 rounded-lg text-[9px] font-bold text-white"
                            style={{ background: 'linear-gradient(135deg,#1A9E78,#25C896)', opacity: confirmarMut.isPending && confirmarMut.variables === ag.id ? 0.6 : 1 }}>
                            {confirmarMut.isPending && confirmarMut.variables === ag.id
                              ? <span className="w-2.5 h-2.5 rounded-full border border-white border-t-transparent animate-spin" />
                              : <Check size={9} />}
                            Confirmar
                          </button>
                        )}
                      </div>
                    )
                  })}

                  {dia.prazos.map((p, j) => (
                    <button
                      key={`p-${j}`}
                      onClick={() => p.cliente_id && onSelectCliente(p.cliente_id, 'processo')}
                      title={`${p.estimado ? '≈ data estimada (prazo em dias úteis) · ' : ''}${p.numero_cnj ? `Processo ${p.numero_cnj}` : p.descricao}`}
                      className="w-full text-left rounded-xl px-2 py-1.5 press"
                      style={{ background: 'rgba(200,48,48,0.06)', border: 'none' }}>
                      <p className="flex items-center gap-1 text-[9px] font-bold" style={{ color: '#C83030' }}>
                        <AlertTriangle size={9} /> Prazo{p.estimado ? ' ≈' : ''}
                      </p>
                      <p className="text-[10px] font-semibold text-am-ink truncate">
                        {p.cliente_nome ?? p.descricao}
                      </p>
                    </button>
                  ))}

                  {dia.agendamentos.length === 0 && dia.prazos.length === 0 && (
                    <div className="h-full min-h-[40px]" />
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Card expandido de aprovação pendente */}
      <AnimatePresence>
        {expandido !== null && (() => {
          const ag = (data?.agendamentos ?? []).find(a => a.id === expandido && a.status === 'aguardando_advogado')
          if (!ag) return null
          return (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 8 }}
              transition={{ duration: 0.18 }}>
              <AprovacaoCard agendamento={ag} />
              <p className="text-[10px] text-am-muted mt-1 text-right">
                Horário solicitado: {labelHorario(ag)} ·{' '}
                <button className="underline" onClick={() => setExpandido(null)}>fechar</button>
              </p>
            </motion.div>
          )
        })()}
      </AnimatePresence>

      {/* Legenda */}
      {!isLoading && data && !semanaVazia && (
        <div className="flex items-center gap-4 justify-center flex-wrap">
          {[
            { cor: 'rgba(18,72,190,0.8)', label: 'Reunião confirmada' },
            { cor: '#D08010', label: 'Aguardando aprovação' },
            { cor: '#C83030', label: 'Prazo processual' },
          ].map(l => (
            <span key={l.label} className="flex items-center gap-1.5 text-[10px] text-am-muted">
              <span className="w-2 h-2 rounded-full" style={{ background: l.cor }} /> {l.label}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
