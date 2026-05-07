import { useQuery } from '@tanstack/react-query'
import { Scale, Clock, AlertCircle } from 'lucide-react'
import { fetchProcessos } from '../api/processos'
import type { CRMClienteCard, Processo } from '../types'
import Skeleton from '../components/Skeleton'
import RiskChip from '../components/RiskChip'

function InfoRow({ label, value, mono = false }: { label: string; value?: string | null; mono?: boolean }) {
  return (
    <div>
      <dt className="text-[10px] text-am-muted uppercase tracking-wider font-medium mb-0.5">{label}</dt>
      <dd className={`text-xs text-am-ink ${mono ? 'font-mono' : 'font-medium'}`}>{value ?? '—'}</dd>
    </div>
  )
}

function Section({ title, badge, borderColor, children }: {
  title: string
  badge?: React.ReactNode
  borderColor?: string
  children: React.ReactNode
}) {
  return (
    <div
      className="bg-white rounded-xl border border-am-border overflow-hidden"
      style={borderColor ? { borderLeft: `3px solid ${borderColor}` } : {}}
    >
      <div className="flex items-center justify-between px-5 py-3.5 border-b border-am-border">
        <span className="text-[10px] font-semibold text-am-muted uppercase tracking-wider">{title}</span>
        {badge}
      </div>
      <div className="px-5 py-4">{children}</div>
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
    <div className="p-6 space-y-4">
      {/* Client info */}
      <Section title="Cliente" badge={<span className="text-[10px] font-semibold text-am-green bg-green-50 px-2 py-0.5 rounded-md">Ativo</span>}>
        <dl className="grid grid-cols-2 gap-x-8 gap-y-4">
          <InfoRow label="Nome completo" value={cliente.nome} />
          <InfoRow label="Telefone" value={cliente.telefone_whatsapp} mono />
          {cliente.nps_medio != null && (
            <InfoRow label="NPS médio" value={String(cliente.nps_medio.toFixed(1))} />
          )}
          {cliente.crm_nivel && (
            <div>
              <dt className="text-[10px] text-am-muted uppercase tracking-wider font-medium mb-0.5">Status CRM</dt>
              <dd><RiskChip nivel={cliente.crm_nivel} size="md" /></dd>
            </div>
          )}
        </dl>
        {cliente.crm_resumo && (
          <p className="mt-4 pt-4 border-t border-am-border text-xs text-am-secondary leading-relaxed">
            {cliente.crm_resumo}
          </p>
        )}
      </Section>

      {/* Processo */}
      {isLoading && cliente.total_processos > 0 && (
        <div className="space-y-2">
          <Skeleton className="h-4 w-1/3" />
          <Skeleton className="h-3 w-1/2" />
          <Skeleton className="h-3 w-2/3" />
        </div>
      )}

      {!isLoading && processo && (
        <Section
          title="Processo Judicial"
          borderColor={processo.polo_cliente === 'autor' ? '#1A9E78' : '#C83030'}
          badge={
            <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-md
              ${processo.polo_cliente === 'autor'
                ? 'text-am-green bg-green-50'
                : 'text-am-red bg-red-50'}`}
            >
              {processo.polo_cliente === 'autor' ? 'Autor' : 'Réu'}
            </span>
          }
        >
          <dl className="grid grid-cols-2 gap-x-8 gap-y-4">
            <InfoRow label="Número CNJ" value={processo.numero_cnj} mono />
            <InfoRow label="Tribunal" value={processo.tribunal} />
            <InfoRow label="Vara" value={processo.vara} />
            <InfoRow label="Comarca" value={processo.comarca} />
            <InfoRow label="Tipo de ação" value={processo.tipo_acao} />
            <InfoRow label="Status" value={processo.status} />
            {processo.data_distribuicao && (
              <InfoRow label="Distribuição" value={new Date(processo.data_distribuicao).toLocaleDateString('pt-BR')} />
            )}
            {processo.valor_causa && (
              <InfoRow label="Valor da causa" value={`R$ ${Number(processo.valor_causa).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}`} />
            )}
          </dl>

          {processo.score_risco != null && (
            <div className="mt-4 pt-4 border-t border-am-border flex items-center gap-3">
              <RiskChip nivel={processo.score_nivel} score={processo.score_risco} size="md" />
              {processo.score_interpretacao && (
                <p className="text-xs text-am-secondary leading-relaxed">{processo.score_interpretacao}</p>
              )}
            </div>
          )}
        </Section>
      )}

      {!isLoading && !processo && cliente.total_processos === 0 && (
        <div className="flex flex-col items-center justify-center py-12 gap-3 text-am-muted">
          <Scale size={32} strokeWidth={1.5} />
          <div className="text-sm font-medium text-am-secondary">Sem processo vinculado</div>
          <div className="text-xs text-center max-w-xs">
            Este cliente não possui processo judicial cadastrado no sistema.
          </div>
        </div>
      )}

      {/* Andamentos */}
      {processo?.andamentos && processo.andamentos.length > 0 && (
        <Section title="Histórico de Andamentos">
          <ol className="relative space-y-0">
            {processo.andamentos.map((a, i) => (
              <li key={i} className="flex gap-4 pb-5 last:pb-0">
                <div className="flex flex-col items-center flex-shrink-0">
                  <div className={`w-2 h-2 rounded-full mt-0.5 flex-shrink-0
                    ${i === 0 ? 'bg-am-blue' : 'bg-am-blue-light'}`}
                  />
                  {i < processo.andamentos.length - 1 && (
                    <div className="w-px flex-1 bg-am-border mt-1" />
                  )}
                </div>
                <div className="pb-1">
                  <div className="flex items-center gap-2 mb-0.5">
                    <Clock size={9} className="text-am-muted" />
                    <time className="text-[10px] text-am-muted">
                      {new Date(a.data).toLocaleDateString('pt-BR')}
                    </time>
                  </div>
                  <p className={`text-xs leading-relaxed ${i === 0 ? 'font-medium text-am-ink' : 'text-am-secondary'}`}>
                    {a.descricao}
                  </p>
                </div>
              </li>
            ))}
          </ol>
        </Section>
      )}

      {/* CRM action */}
      {cliente.crm_acao_sugerida && (
        <div className="flex items-start gap-3 p-4 rounded-xl bg-amber-50 border border-amber-100">
          <AlertCircle size={14} className="text-am-amber flex-shrink-0 mt-0.5" />
          <div>
            <div className="text-xs font-semibold text-am-amber mb-0.5">Ação sugerida</div>
            <div className="text-xs text-am-secondary">{cliente.crm_acao_sugerida}</div>
          </div>
        </div>
      )}
    </div>
  )
}
