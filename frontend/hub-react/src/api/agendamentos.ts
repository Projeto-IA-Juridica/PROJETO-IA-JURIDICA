import { api } from './client'

/* ── Tipos ── */

export type AgendamentoStatus =
  | 'aguardando_cliente'
  | 'aguardando_advogado'
  | 'confirmado'
  | 'cancelado'
  | 'expirado'

export interface OpcaoHorario {
  inicio: string
  fim: string
  label: string
  conflito_prazo?: boolean
}

export interface MensagemContexto {
  autor: 'cliente' | 'ia'
  texto: string
}

export interface Agendamento {
  id: number
  status: AgendamentoStatus
  cliente_id: number
  cliente_nome: string | null
  processo_id: number | null
  interacao_id: number | null
  data_hora_inicio: string | null
  data_hora_fim: string | null
  opcoes_propostas: OpcaoHorario[] | null
  opcao_selecionada_pos: number | null
  canal_aprovacao: 'hub' | 'whatsapp' | null
  motivo_cliente: string | null
  nota_advogado: string | null
  expira_em: string | null
  proposta_enviada_em: string | null
  resposta_cliente_em: string | null
  resposta_advogado_em: string | null
  motivo_cancelamento: string | null
  created_at: string
  updated_at: string
  conflito_prazo: boolean
  conflito_descricao: string | null
  contexto_conversa: MensagemContexto[]
}

export interface PrazoAgenda {
  data: string // YYYY-MM-DD
  descricao: string
  processo_id: number | null
  cliente_id: number | null
  cliente_nome: string | null
  numero_cnj: string | null
  /** data calculada de prazo relativo ("15 dias úteis") — aproximação */
  estimado?: boolean
}

export interface EventosAgenda {
  agendamentos: Agendamento[]
  prazos: PrazoAgenda[]
  tem_disponibilidade: boolean
}

export interface DisponibilidadeDia {
  dia_semana: number // 0=segunda … 5=sábado
  hora_inicio: string // "09:00"
  hora_fim: string // "18:00"
  ativo: boolean
}

export interface SlotPrevia {
  inicio: string
  fim: string
  label: string
  conflito_prazo?: boolean
}

/* ── Agendamentos (Hub do advogado) ── */

export async function listarAgendamentos(params?: {
  status?: AgendamentoStatus
  data_inicio?: string
  data_fim?: string
  page?: number
  page_size?: number
}): Promise<Agendamento[]> {
  const { data } = await api.get<Agendamento[]>('/agendamentos', { params })
  return data
}

export async function confirmarAgendamento(id: number): Promise<Agendamento> {
  const { data } = await api.post<Agendamento>(`/agendamentos/${id}/confirmar`)
  return data
}

export async function sugerirNovosHorarios(
  id: number,
  nota_advogado?: string,
): Promise<Agendamento> {
  const { data } = await api.post<Agendamento>(`/agendamentos/${id}/sugerir`, {
    nota_advogado: nota_advogado || null,
  })
  return data
}

export async function cancelarAgendamento(id: number, motivo?: string): Promise<Agendamento> {
  const { data } = await api.post<Agendamento>(`/agendamentos/${id}/cancelar`, {
    motivo: motivo || null,
  })
  return data
}

/* ── Agenda semanal ── */

export async function fetchEventosAgenda(inicioISO: string, fimISO: string): Promise<EventosAgenda> {
  const { data } = await api.get<EventosAgenda>('/agenda/eventos', {
    params: { inicio: inicioISO, fim: fimISO },
  })
  return data
}

/* ── Disponibilidade (Configurações) ── */

export async function fetchDisponibilidade(): Promise<DisponibilidadeDia[]> {
  const { data } = await api.get<DisponibilidadeDia[]>('/agenda/disponibilidade')
  return data
}

export async function salvarDisponibilidade(
  dias: DisponibilidadeDia[],
): Promise<DisponibilidadeDia[]> {
  const { data } = await api.put<DisponibilidadeDia[]>('/agenda/disponibilidade', dias)
  return data
}

export async function fetchSlotsPrevia(numSlots = 3, duracaoMin = 60): Promise<SlotPrevia[]> {
  const { data } = await api.get<SlotPrevia[]>('/agenda/slots', {
    params: { num_slots: numSlots, duracao_min: duracaoMin },
  })
  return data
}
