import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CalendarClock, CheckCircle, Loader2, AlertTriangle, Save, Sparkles } from 'lucide-react'
import {
  fetchDisponibilidade,
  fetchSlotsPrevia,
  salvarDisponibilidade,
  type DisponibilidadeDia,
} from '../../api/agendamentos'
import { getConfig, saveConfig } from '../../api/config'

const DIAS = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado']

interface LinhaDia {
  dia_semana: number
  ativo: boolean
  hora_inicio: string
  hora_fim: string
}

function linhasIniciais(): LinhaDia[] {
  return DIAS.map((_, i) => ({
    dia_semana: i,
    ativo: false,
    hora_inicio: '09:00',
    hora_fim: '18:00',
  }))
}

/** "09:00:00" (backend `time`) → "09:00" (input HTML) */
function hhmm(v: string): string {
  return v.slice(0, 5)
}

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

export default function HorariosAtendimento() {
  const qc = useQueryClient()
  const [linhas, setLinhas] = useState<LinhaDia[]>(linhasIniciais)
  const [telefoneAdvogado, setTelefoneAdvogado] = useState('')
  const [salvo, setSalvo] = useState(false)
  const [erro, setErro] = useState<string | null>(null)

  const { data: disponibilidade, isLoading } = useQuery({
    queryKey: ['agenda-disponibilidade'],
    queryFn: fetchDisponibilidade,
    staleTime: 60_000,
  })

  const { data: config } = useQuery({
    queryKey: ['escritorio-config'],
    queryFn: getConfig,
    staleTime: 60_000,
  })

  const { data: slots, isLoading: slotsLoading } = useQuery({
    queryKey: ['agenda-slots-previa'],
    queryFn: () => fetchSlotsPrevia(3, 60),
    staleTime: 30_000,
  })

  useEffect(() => {
    if (!disponibilidade) return
    setLinhas(prev =>
      prev.map(linha => {
        const salva = disponibilidade.find(d => d.dia_semana === linha.dia_semana)
        return salva
          ? { ...linha, ativo: salva.ativo, hora_inicio: hhmm(salva.hora_inicio), hora_fim: hhmm(salva.hora_fim) }
          : linha
      }),
    )
  }, [disponibilidade])

  useEffect(() => {
    if (config?.telefone_advogado != null) setTelefoneAdvogado(config.telefone_advogado)
  }, [config?.telefone_advogado])

  const salvarMut = useMutation({
    mutationFn: async () => {
      // Grade: envia apenas dias com linha (ativos e inativos preservam config)
      const payload: DisponibilidadeDia[] = linhas
        .filter(l => l.ativo)
        .map(l => ({
          dia_semana: l.dia_semana,
          hora_inicio: l.hora_inicio,
          hora_fim: l.hora_fim,
          ativo: true,
        }))
      await salvarDisponibilidade(payload)
      // Telefone do advogado — persiste junto (config parcial)
      const updated = await saveConfig({ telefone_advogado: telefoneAdvogado.trim() })
      return updated
    },
    onSuccess: (updated) => {
      qc.setQueryData(['escritorio-config'], updated)
      qc.invalidateQueries({ queryKey: ['agenda-disponibilidade'] })
      qc.invalidateQueries({ queryKey: ['agenda-slots-previa'] })
      setErro(null)
      setSalvo(true)
      setTimeout(() => setSalvo(false), 3000)
    },
    onError: (e: unknown) => {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setErro(typeof detail === 'string' ? detail : 'Erro ao salvar horários. Verifique os campos.')
    },
  })

  function atualizar(i: number, patch: Partial<LinhaDia>) {
    setLinhas(prev => prev.map((l, idx) => (idx === i ? { ...l, ...patch } : l)))
    setSalvo(false)
    setErro(null)
  }

  const horarioInvalido = linhas.some(l => l.ativo && l.hora_fim <= l.hora_inicio)

  return (
    <div className="bg-white rounded-2xl card-shadow border border-am-border p-5 card-border-hover">
      <SectionTitle
        icon={<CalendarClock size={14} />}
        label="Horários de Atendimento"
        desc="A IA propõe reuniões aos clientes apenas dentro dessas janelas"
      />

      {isLoading ? (
        <div className="flex items-center justify-center h-24">
          <Loader2 size={20} className="animate-spin text-am-muted" />
        </div>
      ) : (
        <div className="space-y-4">

          {/* Grade semanal */}
          <div className="space-y-1.5">
            {linhas.map((linha, i) => (
              <div key={linha.dia_semana}
                className="flex items-center gap-3 px-3 py-2 rounded-xl"
                style={{
                  background: linha.ativo ? 'rgba(18,72,190,0.04)' : 'var(--color-am-bg)',
                  border: linha.ativo ? '1px solid rgba(18,72,190,0.18)' : '1px solid var(--color-am-border)',
                }}>
                {/* Toggle */}
                <button
                  type="button"
                  role="switch"
                  aria-checked={linha.ativo}
                  aria-label={`Atendimento na ${DIAS[i]}`}
                  onClick={() => atualizar(i, { ativo: !linha.ativo })}
                  className="relative flex-shrink-0 rounded-full transition-colors"
                  style={{
                    width: 32, height: 18,
                    background: linha.ativo ? 'var(--color-am-blue)' : 'rgba(12,30,48,0.15)',
                  }}>
                  <span
                    className="absolute top-0.5 rounded-full bg-white transition-all"
                    style={{ width: 14, height: 14, left: linha.ativo ? 16 : 2 }}
                  />
                </button>

                <span className="text-xs font-semibold w-16 flex-shrink-0"
                  style={{ color: linha.ativo ? 'var(--color-am-ink)' : 'var(--color-am-muted)' }}>
                  {DIAS[i]}
                </span>

                {linha.ativo ? (
                  <div className="flex items-center gap-2 flex-1 flex-wrap">
                    <input
                      type="time"
                      value={linha.hora_inicio}
                      onChange={e => atualizar(i, { hora_inicio: e.target.value })}
                      className="am-input"
                      style={{ width: 110 }}
                    />
                    <span className="text-[11px] text-am-muted">às</span>
                    <input
                      type="time"
                      value={linha.hora_fim}
                      onChange={e => atualizar(i, { hora_fim: e.target.value })}
                      className="am-input"
                      style={{ width: 110 }}
                    />
                    {linha.hora_fim <= linha.hora_inicio && (
                      <span className="text-[10px] font-medium" style={{ color: '#C83030' }}>
                        fim deve ser após o início
                      </span>
                    )}
                  </div>
                ) : (
                  <span className="text-[11px] text-am-muted">Não atende</span>
                )}
              </div>
            ))}
          </div>

          {/* Telefone do advogado */}
          <div className="space-y-1.5">
            <label className="am-label">WhatsApp do advogado (aprovações)</label>
            <input
              type="tel"
              value={telefoneAdvogado}
              onChange={e => { setTelefoneAdvogado(e.target.value); setSalvo(false); setErro(null) }}
              placeholder="(11) 99999-9999"
              className="am-input"
            />
            <p className="am-hint">
              Número que recebe as solicitações de reunião para aprovar respondendo "1" ou "2".
              Separado do número do escritório usado pelos clientes.
            </p>
          </div>

          {/* Prévia dos próximos slots */}
          <div className="rounded-xl px-4 py-3"
            style={{ background: 'rgba(58,122,184,0.05)', border: '1px solid rgba(58,122,184,0.18)' }}>
            <p className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-am-secondary mb-2">
              <Sparkles size={10} /> Próximos horários que a IA vai oferecer
            </p>
            {slotsLoading ? (
              <Loader2 size={14} className="animate-spin text-am-muted" />
            ) : (slots ?? []).length > 0 ? (
              <div className="flex items-center gap-2 flex-wrap">
                {(slots ?? []).map((s, i) => (
                  <span key={i} className="text-[11px] font-semibold px-2.5 py-1 rounded-lg"
                    style={{ background: 'white', color: 'var(--color-am-blue)', border: '1px solid rgba(18,72,190,0.20)' }}>
                    {s.label}
                  </span>
                ))}
              </div>
            ) : (
              <p className="text-[11px] text-am-muted">
                Nenhum slot disponível — ative pelo menos um dia acima e salve.
              </p>
            )}
          </div>

          {erro && (
            <div className="flex items-start gap-2 px-3 py-2.5 rounded-xl text-xs"
              style={{ background: 'rgba(200,48,48,0.06)', border: '1px solid rgba(200,48,48,0.20)', color: '#C83030' }}>
              <AlertTriangle size={13} className="flex-shrink-0 mt-0.5" /> {erro}
            </div>
          )}

          <div className="flex justify-end">
            <button
              type="button"
              disabled={salvarMut.isPending || horarioInvalido}
              onClick={() => salvarMut.mutate()}
              className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-white text-xs font-bold transition-fast"
              style={{
                background: salvo ? '#1A9E78' : 'var(--color-am-blue)',
                opacity: salvarMut.isPending || horarioInvalido ? 0.6 : 1,
                cursor: salvarMut.isPending || horarioInvalido ? 'not-allowed' : 'pointer',
              }}>
              {salvarMut.isPending
                ? <><Loader2 size={13} className="animate-spin" /> Salvando…</>
                : salvo
                  ? <><CheckCircle size={13} /> Horários salvos</>
                  : <><Save size={13} /> Salvar horários</>}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
