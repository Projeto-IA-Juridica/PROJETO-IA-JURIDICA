import { useQuery } from '@tanstack/react-query'
import { Scale, Clock, AlertCircle, User, Phone, Star, Gavel } from 'lucide-react'
import { fetchProcessos } from '../api/processos'
import type { CRMClienteCard, Processo } from '../types'
import Skeleton from '../components/Skeleton'
import RiskChip from '../components/RiskChip'

/* Borda lateral do card muda por status — único elemento que troca de cor */
const POLO_BORDER: Record<string, string> = {
  autor: '#1A9E78',  /* favorável */
  reu:   '#C83030',  /* risco */
}

function InfoRow({ label, value, mono = false, accent = false }: {
  label: string
  value?: string | null
  mono?: boolean
  accent?: boolean
}) {
  return (
    <div className="space-y-1">
      <dt className="text-[10px] font-bold uppercase tracking-wider text-am-muted">{label}</dt>
      <dd
        className={`text-sm leading-snug font-semibold ${mono ? 'font-mono text-xs' : ''}`}
        style={{ color: accent ? 'var(--color-am-blue)' : 'var(--color-am-ink)' }}
      >
        {value ?? <span className="text-am-muted font-normal text-xs">—</span>}
      </dd>
    </div>
  )
}

function SectionCard({ title, badge, accentColor, icon, children }: {
  title: string
  badge?: React.ReactNode
  accentColor?: string
  icon?: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <div
      className="bg-white rounded-xl overflow-hidden card-shadow"
      style={{
        border: '1px solid var(--color-am-border)',
        borderLeft: accentColor ? `3px solid ${accentColor}` : '1px solid var(--color-am-border)',
      }}
    >
      <div
        className="flex items-center justify-between px-4 sm:px-5 py-3.5"
        style={{ background: 'var(--color-am-bg)', borderBottom: '1px solid var(--color-am-border)' }}
      >
        <div className="flex items-center gap-2">
          {icon && <span className="text-am-blue">{icon}</span>}
          <span className="text-[10px] font-bold text-am-secondary uppercase tracking-wider">{title}</span>
        </div>
        {badge}
      </div>
      <div className="px-4 sm:px-5 py-4 sm:py-5">{children}</div>
    </div>
  )
}

export default function ProcessoTab({ cliente }: { cliente: CRMClienteCard }) {
  const { data, isLoading } = useQuery({
    queryKey: ['processos', cliente.id],
    queryFn: () => fetchProcessos(cliente.id),
    enabled: cliente.total_processos > 0,
  })
  const processo: Processo | null = data?.items[0] ?? null

  return (
    <div className="p-4 sm:p-6 space-y-4">

      {/* Cliente */}
      <SectionCard
        title="Dados do Cliente"
        icon={<User size={13} />}
        badge={
          <span
            className="text-[10px] font-bold px-2.5 py-1 rounded-lg"
            style={{ color: '#1A9E78', background: 'rgba(26,158,120,0.08)', border: '1px solid rgba(26,158,120,0.2)' }}
          >
            Ativo
          </span>
        }
      >
        <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-4">
          <InfoRow label="Nome completo" value={cliente.nome} />
          <div className="space-y-1">
            <dt className="text-[10px] font-bold uppercase tracking-wider text-am-muted">Telefone</dt>
            <dd className="flex items-center gap-1.5">
              <Phone size={11} className="text-am-muted" />
              <span className="text-xs font-mono font-semibold text-am-ink">
                {cliente.telefone_whatsapp ?? '—'}
              </span>
            </dd>
          </div>
          {cliente.nps_medio != null && (
            <div className="space-y-1">
              <dt className="text-[10px] font-bold uppercase tracking-wider text-am-muted">NPS Médio</dt>
              <dd className="flex items-center gap-1.5">
                <Star size={11} style={{ color: '#D08010' }} />
                <span className="text-sm font-bold text-am-ink">{cliente.nps_medio.toFixed(1)}</span>
              </dd>
            </div>
          )}
          {cliente.crm_nivel && (
            <div className="space-y-1">
              <dt className="text-[10px] font-bold uppercase tracking-wider text-am-muted">Status CRM</dt>
              <dd><RiskChip nivel={cliente.crm_nivel} size="md" /></dd>
            </div>
          )}
        </dl>
        {cliente.crm_resumo && (
          <p className="mt-4 pt-4 text-xs text-am-secondary leading-relaxed"
            style={{ borderTop: '1px solid var(--color-am-border)' }}>
            {cliente.crm_resumo}
          </p>
        )}
      </SectionCard>

      {/* Skeleton */}
      {isLoading && cliente.total_processos > 0 && (
        <div className="space-y-2">
          <Skeleton className="h-5 w-1/3" />
          <Skeleton className="h-4 w-1/2" />
          <Skeleton className="h-4 w-2/3" />
        </div>
      )}

      {/* Processo */}
      {!isLoading && processo && (
        <SectionCard
          title="Processo Judicial"
          icon={<Gavel size={13} />}
          accentColor={POLO_BORDER[processo.polo_cliente ?? ''] ?? 'var(--color-am-blue)'}
          badge={
            <span
              className="text-[10px] font-bold px-2.5 py-1 rounded-lg"
              style={processo.polo_cliente === 'autor'
                ? { color: '#1A9E78', background: 'rgba(26,158,120,0.08)',  border: '1px solid rgba(26,158,120,0.2)'  }
                : { color: '#C83030', background: 'rgba(200,48,48,0.08)',   border: '1px solid rgba(200,48,48,0.2)'   }
              }
            >
              {processo.polo_cliente === 'autor' ? 'Autor' : 'Réu'}
            </span>
          }
        >
          <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-4">
            <div className="sm:col-span-2">
              <InfoRow label="Número CNJ" value={processo.numero_cnj} mono accent />
            </div>
            <InfoRow label="Tribunal"    value={processo.tribunal}  />
            <InfoRow label="Vara"        value={processo.vara}      />
            <InfoRow label="Comarca"     value={processo.comarca}   />
            <InfoRow label="Tipo de ação" value={processo.tipo_acao} />
            <InfoRow label="Status"      value={processo.status}    />
            {processo.data_distribuicao && (
              <InfoRow
                label="Distribuição"
                value={new Date(processo.data_distribuicao).toLocaleDateString('pt-BR')}
              />
            )}
            {processo.valor_causa && (
              <div className="space-y-1">
                <dt className="text-[10px] font-bold uppercase tracking-wider text-am-muted">Valor da causa</dt>
                <dd className="text-sm font-bold text-am-ink">
                  R$ {Number(processo.valor_causa).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                </dd>
              </div>
            )}
          </dl>

          {processo.score_risco != null && (
            <div className="mt-5 pt-4 flex flex-wrap items-center gap-3"
              style={{ borderTop: '1px solid var(--color-am-border)' }}>
              <RiskChip nivel={processo.score_nivel} score={processo.score_risco} size="md" />
              {processo.score_interpretacao && (
                <p className="text-xs text-am-secondary leading-relaxed">{processo.score_interpretacao}</p>
              )}
            </div>
          )}
        </SectionCard>
      )}

      {/* Sem processo */}
      {!isLoading && !processo && cliente.total_processos === 0 && (
        <div className="flex flex-col items-center justify-center py-14 gap-4">
          <div
            className="w-12 h-12 rounded-2xl flex items-center justify-center"
            style={{ background: 'var(--color-am-surface)', border: '1px solid var(--color-am-border)' }}
          >
            <Scale size={22} strokeWidth={1.5} className="text-am-blue" />
          </div>
          <div className="text-center">
            <div className="text-sm font-bold text-am-ink mb-1">Sem processo vinculado</div>
            <div className="text-xs text-am-muted max-w-xs">
              Este cliente não possui processo judicial cadastrado no sistema.
            </div>
          </div>
        </div>
      )}

      {/* Andamentos — borda azul (instrução normal) */}
      {processo?.andamentos && processo.andamentos.length > 0 && (
        <SectionCard
          title="Histórico de Andamentos"
          icon={<Clock size={13} />}
          accentColor="var(--color-am-blue)"
        >
          <ol className="space-y-0">
            {processo.andamentos.map((a, i) => (
              <li key={i} className="flex gap-4 pb-5 last:pb-0">
                <div className="flex flex-col items-center flex-shrink-0">
                  <div
                    className="w-2.5 h-2.5 rounded-full mt-0.5 flex-shrink-0"
                    style={{
                      background: i === 0 ? 'var(--color-am-blue)' : 'var(--color-am-blue-light)',
                      boxShadow: i === 0 ? '0 0 0 3px rgba(58,122,184,0.15)' : 'none',
                    }}
                  />
                  {i < processo.andamentos.length - 1 && (
                    <div className="w-px flex-1 mt-1.5 bg-am-border" />
                  )}
                </div>
                <div className="pb-1 min-w-0">
                  <time className="text-[10px] font-bold text-am-muted block mb-1">
                    {new Date(a.data).toLocaleDateString('pt-BR', {
                      day: '2-digit', month: 'long', year: 'numeric',
                    })}
                  </time>
                  <p className={`text-xs leading-relaxed ${i === 0 ? 'font-semibold text-am-ink' : 'text-am-secondary'}`}>
                    {a.descricao}
                  </p>
                </div>
              </li>
            ))}
          </ol>
        </SectionCard>
      )}

      {/* Ação sugerida — borda âmbar */}
      {cliente.crm_acao_sugerida && (
        <div
          className="flex items-start gap-3 p-4 rounded-xl"
          style={{
            background: 'rgba(208,128,16,0.06)',
            border: '1px solid rgba(208,128,16,0.22)',
            borderLeft: '3px solid #D08010',
          }}
        >
          <AlertCircle size={15} style={{ color: '#D08010' }} className="flex-shrink-0 mt-0.5" />
          <div>
            <div className="text-xs font-bold mb-0.5" style={{ color: '#D08010' }}>Ação sugerida pela IA</div>
            <div className="text-xs text-am-secondary leading-relaxed">{cliente.crm_acao_sugerida}</div>
          </div>
        </div>
      )}
    </div>
  )
}
