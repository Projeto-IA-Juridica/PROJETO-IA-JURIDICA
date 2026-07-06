import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CalendarClock, Check, MessageSquare, X } from 'lucide-react'
import {
  cancelarAgendamento,
  confirmarAgendamento,
  sugerirNovosHorarios,
  type Agendamento,
} from '../../api/agendamentos'

const QUERY_KEYS_AGENDAMENTO = [
  ['agendamentos-pendentes'],
  ['agendamentos-eventos'],
  ['agendamentos-proximas'],
] as const

function initials(nome: string | null) {
  if (!nome) return '?'
  return nome.split(' ').slice(0, 2).map(n => n[0]?.toUpperCase() ?? '').join('')
}

export function labelHorario(ag: Agendamento): string {
  const pos = ag.opcao_selecionada_pos
  if (ag.opcoes_propostas && pos !== null && ag.opcoes_propostas[pos]) {
    return ag.opcoes_propostas[pos].label
  }
  if (ag.data_hora_inicio) {
    const d = new Date(ag.data_hora_inicio)
    return d.toLocaleString('pt-BR', {
      weekday: 'long', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
    })
  }
  return 'horário a definir'
}

interface Props {
  agendamento: Agendamento
  /** compacto = sem contexto de conversa (usado no expand da Agenda) */
  compact?: boolean
}

export default function AprovacaoCard({ agendamento: ag, compact = false }: Props) {
  const qc = useQueryClient()
  const [modo, setModo] = useState<'normal' | 'sugerir' | 'recusar'>('normal')
  const [nota, setNota] = useState('')
  const [erro, setErro] = useState<string | null>(null)

  function invalidar() {
    QUERY_KEYS_AGENDAMENTO.forEach(k => qc.invalidateQueries({ queryKey: [...k] }))
  }

  function extrairErro(e: unknown): string {
    return (
      (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      ?? 'Não foi possível concluir. Tente novamente.'
    )
  }

  const confirmarMut = useMutation({
    mutationFn: () => confirmarAgendamento(ag.id),
    onSuccess: invalidar,
    onError: (e: unknown) => setErro(extrairErro(e)),
  })
  const sugerirMut = useMutation({
    mutationFn: () => sugerirNovosHorarios(ag.id, nota.trim() || undefined),
    onSuccess: () => { setModo('normal'); setNota(''); invalidar() },
    onError: (e: unknown) => setErro(extrairErro(e)),
  })
  const recusarMut = useMutation({
    mutationFn: () => cancelarAgendamento(ag.id, 'Recusado pelo advogado'),
    onSuccess: invalidar,
    onError: (e: unknown) => setErro(extrairErro(e)),
  })

  const pendente = confirmarMut.isPending || sugerirMut.isPending || recusarMut.isPending

  return (
    <div
      className="rounded-2xl overflow-hidden"
      style={{
        background: 'linear-gradient(180deg, rgba(208,128,16,0.06), rgba(208,128,16,0.02))',
        border: '1px solid rgba(208,128,16,0.30)',
        boxShadow: '0 2px 10px rgba(208,128,16,0.08)',
      }}>

      {/* Cabeçalho */}
      <div className="flex items-start gap-3 px-4 pt-4">
        <div className="w-9 h-9 rounded-xl flex items-center justify-center text-xs font-bold text-white flex-shrink-0"
          style={{ background: 'linear-gradient(135deg,#D08010,#E8A030)' }}>
          {initials(ag.cliente_nome)}
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-xs font-bold text-am-ink">
            ⏰ {ag.cliente_nome ?? `Cliente #${ag.cliente_id}`} quer reunião
          </p>
          <p className="flex items-center gap-1 text-[11px] font-semibold mt-1" style={{ color: '#D08010' }}>
            <CalendarClock size={11} /> {labelHorario(ag)}
          </p>
        </div>
        {ag.resposta_cliente_em && (
          <span className="text-[10px] text-am-muted flex-shrink-0">
            {new Date(ag.resposta_cliente_em).toLocaleString('pt-BR', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}
          </span>
        )}
      </div>

      <div className="px-4 pb-4 pt-3 space-y-3">
        {/* Motivo detectado */}
        {ag.motivo_cliente && (
          <div className="rounded-xl px-3 py-2.5" style={{ background: 'white', border: '1px solid var(--color-am-border)' }}>
            <p className="text-[9px] font-bold uppercase tracking-widest text-am-muted mb-1">Motivo detectado pela IA</p>
            <p className="text-[11px] text-am-ink leading-relaxed italic">“{ag.motivo_cliente}”</p>
          </div>
        )}

        {/* Contexto da conversa */}
        {!compact && ag.contexto_conversa.length > 0 && (
          <div className="rounded-xl px-3 py-2.5" style={{ background: 'white', border: '1px solid var(--color-am-border)' }}>
            <p className="flex items-center gap-1 text-[9px] font-bold uppercase tracking-widest text-am-muted mb-1.5">
              <MessageSquare size={9} /> Contexto da conversa
            </p>
            <div className="space-y-1">
              {ag.contexto_conversa.map((m, i) => (
                <p key={i} className="text-[11px] leading-relaxed">
                  <span className="font-bold" style={{ color: m.autor === 'cliente' ? 'var(--color-am-blue)' : 'var(--color-am-muted)' }}>
                    {m.autor === 'cliente' ? 'Cliente' : 'IA'}:
                  </span>{' '}
                  <span className="text-am-secondary">{m.texto}</span>
                </p>
              ))}
            </div>
          </div>
        )}

        {/* Alerta de conflito de prazo */}
        {ag.conflito_prazo && (
          <div className="flex items-start gap-2 rounded-xl px-3 py-2.5"
            style={{ background: 'rgba(200,48,48,0.06)', border: '1px solid rgba(200,48,48,0.25)' }}>
            <AlertTriangle size={13} className="flex-shrink-0 mt-0.5" style={{ color: '#C83030' }} />
            <p className="text-[11px] font-medium leading-relaxed" style={{ color: '#C83030' }}>
              {ag.conflito_descricao ?? 'Prazo processual próximo — verifique a agenda'}
            </p>
          </div>
        )}

        {erro && (
          <p className="text-[11px] font-medium" style={{ color: '#C83030' }}>{erro}</p>
        )}

        {/* Ações */}
        {modo === 'normal' && (
          <div className="flex items-center gap-2 flex-wrap">
            <button
              disabled={pendente}
              onClick={() => { setErro(null); confirmarMut.mutate() }}
              className="press flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-bold text-white"
              style={{
                background: 'linear-gradient(135deg,#1A9E78,#25C896)',
                opacity: pendente ? 0.6 : 1,
                cursor: pendente ? 'not-allowed' : 'pointer',
              }}>
              {confirmarMut.isPending
                ? <span className="w-3 h-3 rounded-full border-2 border-white border-t-transparent animate-spin" />
                : <Check size={12} />}
              Confirmar
            </button>
            <button
              disabled={pendente}
              onClick={() => { setErro(null); setModo('sugerir') }}
              className="press px-4 py-2 rounded-xl text-xs font-semibold"
              style={{
                background: 'white', color: 'var(--color-am-blue)',
                border: '1px solid rgba(18,72,190,0.25)',
                cursor: pendente ? 'not-allowed' : 'pointer',
              }}>
              Sugerir outro horário
            </button>
            <button
              disabled={pendente}
              onClick={() => { setErro(null); setModo('recusar') }}
              className="press flex items-center gap-1 px-4 py-2 rounded-xl text-xs font-semibold"
              style={{
                background: 'rgba(200,48,48,0.05)', color: '#C83030',
                border: '1px solid rgba(200,48,48,0.22)',
                cursor: pendente ? 'not-allowed' : 'pointer',
              }}>
              <X size={11} /> Recusar
            </button>
          </div>
        )}

        {/* Sugerir novos horários */}
        {modo === 'sugerir' && (
          <div className="space-y-2">
            <p className="text-[11px] text-am-secondary leading-relaxed">
              A IA vai gerar <strong>3 novas opções</strong> com base na sua disponibilidade
              e reenviar ao cliente pelo WhatsApp.
            </p>
            <textarea
              value={nota}
              onChange={e => setNota(e.target.value)}
              maxLength={500}
              rows={2}
              placeholder="Nota interna (opcional, não é enviada ao cliente)"
              className="am-textarea"
            />
            <div className="flex items-center gap-2">
              <button
                disabled={sugerirMut.isPending}
                onClick={() => sugerirMut.mutate()}
                className="press flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-bold text-white"
                style={{ background: 'linear-gradient(135deg,#1248BE,#3A7AB8)', opacity: sugerirMut.isPending ? 0.6 : 1 }}>
                {sugerirMut.isPending
                  ? <span className="w-3 h-3 rounded-full border-2 border-white border-t-transparent animate-spin" />
                  : <CalendarClock size={12} />}
                Gerar novas opções
              </button>
              <button
                disabled={sugerirMut.isPending}
                onClick={() => setModo('normal')}
                className="press px-4 py-2 rounded-xl text-xs font-semibold"
                style={{ background: 'white', color: 'var(--color-am-secondary)', border: '1px solid var(--color-am-border)' }}>
                Voltar
              </button>
            </div>
          </div>
        )}

        {/* Confirmação de recusa */}
        {modo === 'recusar' && (
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[11px] font-medium text-am-secondary">
              Recusar e avisar o cliente pelo WhatsApp?
            </span>
            <button
              disabled={recusarMut.isPending}
              onClick={() => recusarMut.mutate()}
              className="press flex items-center gap-1 px-3.5 py-1.5 rounded-xl text-xs font-bold text-white"
              style={{ background: '#C83030', opacity: recusarMut.isPending ? 0.6 : 1 }}>
              {recusarMut.isPending
                ? <span className="w-3 h-3 rounded-full border-2 border-white border-t-transparent animate-spin" />
                : <X size={11} />}
              Sim, recusar
            </button>
            <button
              disabled={recusarMut.isPending}
              onClick={() => setModo('normal')}
              className="press px-3.5 py-1.5 rounded-xl text-xs font-semibold"
              style={{ background: 'white', color: 'var(--color-am-secondary)', border: '1px solid var(--color-am-border)' }}>
              Voltar
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
