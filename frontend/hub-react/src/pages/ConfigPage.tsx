import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Settings, Save, Bot, Clock, MessageSquare, Building2, CheckCircle, Loader2, AlertTriangle, BarChart2, Brain, Users, LogOut, CreditCard, ExternalLink } from 'lucide-react'
import type { Configuracoes } from '../types'
import { getConfig, saveConfig } from '../api/config'
import { fetchMe, logout } from '../api/auth'
import { fetchMetricasHub } from '../api/hub'
import {
  getBillingStatus,
  getPortalUrl,
  redirectToPortal,
  labelStatus,
  isAssinaturaAtiva,
  PLANOS,
} from '../api/billing'

const DEFAULT_TEMPLATES = {
  template_boas_vindas:  'Olá {{nome}}, seja bem-vindo(a) ao {{escritorio}}! Sou a {{persona}} e estou aqui para auxiliá-lo(a). Como posso ajudar?',
  template_atualizacao:  'Olá {{nome}}, temos uma atualização importante sobre o seu processo {{processo}}. {{mensagem}}',
  template_sem_novidade: 'Olá {{nome}}, verificamos o andamento do seu processo {{processo}} e não há novidades para informar no momento. Seguimos acompanhando de perto.',
}

const EMPTY_CFG: Configuracoes = {
  nome:                 '',
  cnpj:                 '',
  email:                '',
  telefone:             '',
  persona_nome:         '',
  persona_tom:          'formal',
  horario_inicio:       '08:00',
  horario_fim:          '18:00',
  template_boas_vindas: DEFAULT_TEMPLATES.template_boas_vindas,
  template_atualizacao: DEFAULT_TEMPLATES.template_atualizacao,
  template_sem_novidade: DEFAULT_TEMPLATES.template_sem_novidade,
}

const TOM_OPTS: { value: Configuracoes['persona_tom']; label: string; desc: string }[] = [
  { value: 'formal',   label: 'Formal',   desc: 'Linguagem técnica e protocolar'  },
  { value: 'amigavel', label: 'Amigável', desc: 'Tom próximo e acolhedor'         },
  { value: 'neutro',   label: 'Neutro',   desc: 'Equilibrado e imparcial'         },
]

/* ── Métricas Hub IA (admin only) ───────────────────────────────────────── */
function MetricasHubSection() {
  const { data: me } = useQuery({
    queryKey: ['me'],
    queryFn: fetchMe,
    staleTime: 5 * 60_000,
  })

  const isAdmin = me?.role === 'admin'

  const { data: metricas, isLoading } = useQuery({
    queryKey: ['hub-metricas'],
    queryFn: fetchMetricasHub,
    enabled: isAdmin,
    staleTime: 5 * 60_000,
  })

  if (!isAdmin) return null

  const intencaoLabel = (i: string) =>
    i === 'analise_peticao' ? 'Análise de Petição' : i === 'duvida_juridica' ? 'Dúvida Jurídica' : i

  const maxSessoes = Math.max(1, ...(metricas?.advogados_mais_ativos ?? []).map(a => a.total_sessoes))
  const maxTotal   = Math.max(1, ...(metricas?.intencoes_top5 ?? []).map(i => i.total))

  return (
    <div className="bg-white rounded-2xl card-shadow border border-am-border p-5 card-border-hover">
      <SectionTitle
        icon={<BarChart2 size={14} />}
        label="Métricas do Hub IA"
        desc={`Uso do mês ${metricas?.mes_atual ?? '—'} · somente administradores`}
      />

      {isLoading ? (
        <div className="flex items-center justify-center h-20">
          <Loader2 size={20} className="animate-spin text-am-muted" />
        </div>
      ) : metricas ? (
        <div className="space-y-5">
          {/* KPIs */}
          <div className="grid grid-cols-3 gap-3">
            {[
              { label: 'Sessões',       value: metricas.total_sessoes.toLocaleString('pt-BR'),                  color: '#1248BE' },
              { label: 'Tokens total',  value: (metricas.tokens_input_total + metricas.tokens_output_total).toLocaleString('pt-BR'), color: '#6B7CFF' },
              { label: 'Custo (USD)',   value: `$${Number(metricas.custo_total_usd).toFixed(4)}`,               color: '#1A9E78' },
            ].map(({ label, value, color }) => (
              <div key={label} className="text-center py-3 px-2 rounded-xl"
                style={{ background: `${color}08`, border: `1px solid ${color}18` }}>
                <p className="text-sm font-extrabold leading-none mb-1" style={{ color }}>{value}</p>
                <p className="text-[10px] text-am-muted">{label}</p>
              </div>
            ))}
          </div>

          {/* Top 5 Intenções */}
          {metricas.intencoes_top5.length > 0 && (
            <div>
              <div className="flex items-center gap-1.5 mb-2">
                <Brain size={11} style={{ color: 'var(--color-am-blue)' }} />
                <p className="text-[10px] font-bold uppercase tracking-wider text-am-secondary">Top intenções</p>
              </div>
              <div className="space-y-2">
                {metricas.intencoes_top5.map(({ intencao, total }) => {
                  const pct = Math.round((total / maxTotal) * 100)
                  return (
                    <div key={intencao} className="flex items-center gap-2">
                      <span className="text-[11px] text-am-secondary w-36 flex-shrink-0 truncate">{intencaoLabel(intencao)}</span>
                      <div className="flex-1 h-1.5 rounded-full overflow-hidden" style={{ background: 'rgba(18,72,190,0.08)' }}>
                        <div className="h-full rounded-full" style={{ width: `${pct}%`, background: 'var(--color-am-blue)', transition: 'width 0.6s ease' }} />
                      </div>
                      <span className="text-[10px] font-bold text-am-ink w-6 text-right flex-shrink-0">{total}</span>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Advogados mais ativos */}
          {metricas.advogados_mais_ativos.length > 0 && (
            <div>
              <div className="flex items-center gap-1.5 mb-2">
                <Users size={11} style={{ color: 'var(--color-am-blue)' }} />
                <p className="text-[10px] font-bold uppercase tracking-wider text-am-secondary">Advogados mais ativos</p>
              </div>
              <div className="space-y-2">
                {metricas.advogados_mais_ativos.map(({ usuario_id, total_sessoes }) => {
                  const pct = Math.round((total_sessoes / maxSessoes) * 100)
                  return (
                    <div key={usuario_id} className="flex items-center gap-2">
                      <span className="text-[11px] text-am-secondary w-36 flex-shrink-0">Usuário #{usuario_id}</span>
                      <div className="flex-1 h-1.5 rounded-full overflow-hidden" style={{ background: 'rgba(107,124,255,0.08)' }}>
                        <div className="h-full rounded-full" style={{ width: `${pct}%`, background: '#6B7CFF', transition: 'width 0.6s ease' }} />
                      </div>
                      <span className="text-[10px] font-bold text-am-ink w-6 text-right flex-shrink-0">{total_sessoes}</span>
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </div>
      ) : null}
    </div>
  )
}

/* ── Seção de Assinatura / Billing ───────────────────────────────────────── */

function BillingSection() {
  const { data: me } = useQuery({ queryKey: ['me'], queryFn: fetchMe, staleTime: 5 * 60_000 })
  const isAdmin = me?.role === 'admin'

  const { data: billing, isLoading } = useQuery({
    queryKey: ['billing-status'],
    queryFn: getBillingStatus,
    enabled: isAdmin,
    staleTime: 60_000,
  })

  const [abrindoPortal, setAbrindoPortal] = useState(false)
  const [portalErro, setPortalErro] = useState<string | null>(null)

  if (!isAdmin) return null

  async function handleAbrirPortal() {
    setPortalErro(null)
    setAbrindoPortal(true)
    try {
      const res = await getPortalUrl()
      if (res.portal_url) {
        redirectToPortal(res.portal_url)
      } else if (!res.stripe_habilitado) {
        setPortalErro('Pagamento não está configurado neste ambiente.')
      }
    } catch {
      setPortalErro('Erro ao abrir o portal. Tente novamente.')
    } finally {
      setAbrindoPortal(false)
    }
  }

  const planoAtual = PLANOS.find(p => p.id === billing?.plano)
  const statusAtivo = billing ? isAssinaturaAtiva(billing.assinatura_status) : true

  return (
    <div className="bg-white rounded-2xl card-shadow border border-am-border p-5 card-border-hover">
      <SectionTitle
        icon={<CreditCard size={14} />}
        label="Assinatura"
        desc="Gerencie seu plano e método de pagamento"
      />

      {isLoading ? (
        <div className="flex items-center justify-center h-16">
          <Loader2 size={18} className="animate-spin text-am-muted" />
        </div>
      ) : billing ? (
        <div className="space-y-4">
          {/* Status + plano */}
          <div className="flex items-center justify-between flex-wrap gap-3">
            <div className="flex items-center gap-3">
              <div className="flex flex-col gap-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-bold text-am-ink">
                    {planoAtual?.nome ?? billing.plano}
                  </span>
                  {planoAtual && (
                    <span className="text-xs text-am-muted">{planoAtual.preco}/mês</span>
                  )}
                </div>
                <div className="flex items-center gap-1.5">
                  <span
                    style={{
                      width: 6, height: 6, borderRadius: '50%', display: 'inline-block',
                      background: statusAtivo ? 'var(--color-am-green)' : '#C83030',
                    }}
                  />
                  <span className="text-[11px]" style={{ color: statusAtivo ? 'var(--color-am-green)' : '#C83030' }}>
                    {labelStatus(billing.assinatura_status)}
                  </span>
                </div>
              </div>
            </div>

            {/* Botão portal */}
            {billing.stripe_habilitado && billing.stripe_customer_id && (
              <button
                type="button"
                onClick={handleAbrirPortal}
                disabled={abrindoPortal}
                className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold transition-fast border"
                style={{
                  color: 'var(--color-am-blue)',
                  borderColor: 'rgba(18,72,190,0.25)',
                  background: 'rgba(18,72,190,0.04)',
                  opacity: abrindoPortal ? 0.7 : 1,
                  cursor: abrindoPortal ? 'not-allowed' : 'pointer',
                }}
              >
                {abrindoPortal
                  ? <><Loader2 size={12} className="animate-spin" /> Abrindo…</>
                  : <><ExternalLink size={12} /> Gerenciar assinatura</>}
              </button>
            )}
          </div>

          {/* Banner de aviso para status problemáticos */}
          {!statusAtivo && (
            <div className="flex items-start gap-2 px-4 py-3 rounded-xl text-xs"
              style={{ background: 'rgba(200,48,48,0.06)', border: '1px solid rgba(200,48,48,0.20)', color: '#C83030' }}>
              <AlertTriangle size={13} className="flex-shrink-0 mt-0.5" />
              <span>
                {billing.assinatura_status === 'past_due'
                  ? 'Pagamento em atraso. Clique em "Gerenciar assinatura" para atualizar o cartão.'
                  : 'Assinatura inativa. Clique em "Gerenciar assinatura" para reativar.'}
              </span>
            </div>
          )}

          {/* Datas */}
          {billing.trial_expira_em && billing.assinatura_status === 'trialing' && (
            <p className="text-[11px] text-am-muted">
              Trial gratuito até{' '}
              <strong className="text-am-ink">
                {new Date(billing.trial_expira_em).toLocaleDateString('pt-BR')}
              </strong>
            </p>
          )}
          {billing.assinatura_expira_em && billing.assinatura_status === 'active' && (
            <p className="text-[11px] text-am-muted">
              Próxima cobrança em{' '}
              <strong className="text-am-ink">
                {new Date(billing.assinatura_expira_em).toLocaleDateString('pt-BR')}
              </strong>
            </p>
          )}

          {/* Erro ao abrir portal */}
          {portalErro && (
            <p className="text-xs text-red-600">{portalErro}</p>
          )}
        </div>
      ) : (
        <p className="text-xs text-am-muted">Não foi possível carregar informações de assinatura.</p>
      )}
    </div>
  )
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

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <label className="am-label">{label}</label>
      {children}
      {hint && <p className="am-hint">{hint}</p>}
    </div>
  )
}

const inputCls = "am-input"

export default function ConfigPage() {
  const qc = useQueryClient()
  const [cfg, setCfg] = useState<Configuracoes>(EMPTY_CFG)
  const [saveOk, setSaveOk] = useState(false)
  const [apiError, setApiError] = useState<string | null>(null)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['escritorio-config'],
    queryFn: getConfig,
    staleTime: 60_000,
  })

  useEffect(() => {
    if (!data) return
    setCfg({
      ...data,
      template_boas_vindas:  data.template_boas_vindas  ?? DEFAULT_TEMPLATES.template_boas_vindas,
      template_atualizacao:  data.template_atualizacao  ?? DEFAULT_TEMPLATES.template_atualizacao,
      template_sem_novidade: data.template_sem_novidade ?? DEFAULT_TEMPLATES.template_sem_novidade,
    })
  }, [data])

  const mutation = useMutation({
    mutationFn: (payload: Omit<Configuracoes, 'cnpj'>) => saveConfig(payload),
    onSuccess: (updated) => {
      qc.setQueryData(['escritorio-config'], updated)
      setSaveOk(true)
      setApiError(null)
      setTimeout(() => setSaveOk(false), 3000)
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setApiError(detail ?? 'Erro ao salvar configurações. Tente novamente.')
    },
  })

  function update<K extends keyof Configuracoes>(key: K, value: Configuracoes[K]) {
    setCfg((prev) => ({ ...prev, [key]: value }))
    setSaveOk(false)
    setApiError(null)
  }

  function handleSave(e: React.SyntheticEvent) {
    e.preventDefault()
    const { cnpj: _cnpj, ...payload } = cfg
    mutation.mutate(payload)
  }

  const isSaving = mutation.isPending

  async function handleLogout() {
    await logout()
    window.dispatchEvent(new Event('amicus:session-expired'))
  }

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Loader2 size={24} className="animate-spin text-am-muted" />
      </div>
    )
  }

  if (isError) {
    return (
      <div className="flex-1 flex items-center justify-center p-8">
        <div className="flex items-center gap-2 text-xs text-am-secondary">
          <AlertTriangle size={14} style={{ color: '#C83030' }} />
          Não foi possível carregar as configurações. Tente recarregar a página.
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto">
      <form onSubmit={handleSave}>
        <div className="px-6 pt-3 pb-5 max-w-4xl mx-auto space-y-6 page-enter">

          {/* Header */}
          <div className="flex items-center justify-between flex-wrap gap-4">
            <div>
              <h2 className="text-sm font-bold text-am-ink tracking-tight">Configurações</h2>
              <p className="text-xs text-am-muted mt-0.5">Personalize o escritório e a IA</p>
            </div>
            <div className="flex items-center gap-2">
              <button type="button" onClick={handleLogout}
                className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold transition-fast border"
                style={{ color: 'var(--color-am-secondary)', borderColor: 'var(--color-am-border)', background: 'var(--color-am-bg)' }}
                onMouseEnter={(e) => { e.currentTarget.style.color = '#C83030'; e.currentTarget.style.borderColor = 'rgba(200,48,48,0.35)'; e.currentTarget.style.background = 'rgba(200,48,48,0.05)' }}
                onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--color-am-secondary)'; e.currentTarget.style.borderColor = 'var(--color-am-border)'; e.currentTarget.style.background = 'var(--color-am-bg)' }}>
                <LogOut size={13} /> Sair
              </button>
              <button type="submit" disabled={isSaving}
                className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-white text-xs font-bold transition-fast"
                style={{ background: saveOk ? '#1A9E78' : 'var(--color-am-blue)', opacity: isSaving ? 0.7 : 1, cursor: isSaving ? 'not-allowed' : 'pointer' }}
                onMouseEnter={(e) => { if (!saveOk && !isSaving) e.currentTarget.style.background = 'var(--color-am-blue-hover)' }}
                onMouseLeave={(e) => { if (!saveOk && !isSaving) e.currentTarget.style.background = 'var(--color-am-blue)' }}>
                {isSaving
                  ? <><Loader2 size={13} className="animate-spin" /> Salvando…</>
                  : saveOk
                    ? <><CheckCircle size={13} /> Salvo</>
                    : <><Save size={13} /> Salvar</>}
              </button>
            </div>
          </div>

          {/* Erro global de API */}
          {apiError && (
            <div className="flex items-start gap-2 px-4 py-3 rounded-xl text-xs"
              style={{ background: 'rgba(200,48,48,0.06)', border: '1px solid rgba(200,48,48,0.20)', color: '#C83030' }}>
              <AlertTriangle size={13} className="flex-shrink-0 mt-0.5" />
              {apiError}
            </div>
          )}

          {/* Dados do escritório */}
          <div className="bg-white rounded-2xl card-shadow border border-am-border p-5 card-border-hover">
            <SectionTitle icon={<Building2 size={14} />} label="Dados do Escritório" desc="Informações básicas do seu escritório" />
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="sm:col-span-2">
                <Field label="Nome do escritório">
                  <input type="text" value={cfg.nome}
                    onChange={(e) => update('nome', e.target.value)}
                    className={inputCls} />
                </Field>
              </div>
              <Field label="CNPJ">
                <input type="text" value={cfg.cnpj} readOnly className={inputCls} />
              </Field>
              <Field label="E-mail">
                <input type="email" value={cfg.email}
                  onChange={(e) => update('email', e.target.value)}
                  className={inputCls} />
              </Field>
              <Field label="Telefone / WhatsApp">
                <input type="tel" value={cfg.telefone ?? ''} placeholder="(11) 9 9999-9999"
                  onChange={(e) => update('telefone', e.target.value)}
                  className={inputCls} />
              </Field>
            </div>
          </div>

          {/* Persona da IA */}
          <div className="bg-white rounded-2xl card-shadow border border-am-border p-5 card-border-hover">
            <SectionTitle icon={<Bot size={14} />} label="Persona da IA" desc="Como a IA se apresentará aos clientes" />
            <div className="space-y-4">
              <Field label="Nome da persona">
                <input type="text" value={cfg.persona_nome}
                  onChange={(e) => update('persona_nome', e.target.value)}
                  className={inputCls} />
              </Field>

              <Field label="Tom de comunicação">
                <div className="grid grid-cols-3 gap-2 mt-1">
                  {TOM_OPTS.map((opt) => {
                    const active = cfg.persona_tom === opt.value
                    return (
                      <button key={opt.value} type="button"
                        onClick={() => update('persona_tom', opt.value)}
                        className="flex flex-col items-start gap-1 px-3 py-2.5 rounded-xl border transition-fast text-left"
                        style={active
                          ? { background: 'var(--color-am-surface)', border: '1px solid var(--color-am-blue)', borderLeft: '3px solid var(--color-am-blue)' }
                          : { background: 'var(--color-am-bg)', border: '1px solid var(--color-am-border)' }}>
                        <span className="text-xs font-bold" style={{ color: active ? 'var(--color-am-blue)' : 'var(--color-am-ink)' }}>
                          {opt.label}
                        </span>
                        <span className="text-[10px] text-am-muted leading-tight">{opt.desc}</span>
                      </button>
                    )
                  })}
                </div>
              </Field>
            </div>
          </div>

          {/* Horários */}
          <div className="bg-white rounded-2xl card-shadow border border-am-border p-5 card-border-hover">
            <SectionTitle icon={<Clock size={14} />} label="Horário de Atendimento" desc="Janela de respostas automáticas" />
            <div className="grid grid-cols-2 gap-4">
              <Field label="Início">
                <input type="time" value={cfg.horario_inicio}
                  onChange={(e) => update('horario_inicio', e.target.value)}
                  className={inputCls} />
              </Field>
              <Field label="Fim">
                <input type="time" value={cfg.horario_fim}
                  onChange={(e) => update('horario_fim', e.target.value)}
                  className={inputCls} />
              </Field>
            </div>
            <p className="text-[10px] text-am-muted mt-3">
              Fora desse horário, a IA responde informando que o escritório está fechado e que entrará em contato em breve.
            </p>
          </div>

          {/* Templates */}
          <div className="bg-white rounded-2xl card-shadow border border-am-border p-5 card-border-hover">
            <SectionTitle icon={<MessageSquare size={14} />} label="Mensagens Automáticas" desc="Templates enviados via WhatsApp" />
            <div className="space-y-4">
              {([
                { key: 'template_boas_vindas',  label: 'Boas-vindas',             hint: 'Enviado quando um novo cliente inicia contato.' },
                { key: 'template_atualizacao',  label: 'Atualização de processo', hint: 'Enviado ao detectar novo andamento.' },
                { key: 'template_sem_novidade', label: 'Sem novidades',           hint: 'Enviado quando o processo não tem andamentos recentes.' },
              ] as const).map(({ key, label, hint }) => (
                <Field key={key} label={label} hint={hint}>
                  <textarea rows={3} value={cfg[key]}
                    onChange={(e) => update(key, e.target.value)}
                    className="am-textarea"
                  />
                </Field>
              ))}
              <div className="rounded-xl px-4 py-3 text-[10px] text-am-secondary leading-relaxed"
                style={{ background: 'rgba(58,122,184,0.05)', border: '1px solid rgba(58,122,184,0.18)' }}>
                <strong className="text-am-ink">Variáveis disponíveis:</strong>
                {' '}{'{{nome}}'} — nome do cliente,
                {' '}{'{{escritorio}}'} — nome do escritório,
                {' '}{'{{persona}}'} — nome da IA,
                {' '}{'{{processo}}'} — número CNJ,
                {' '}{'{{mensagem}}'} — texto do andamento
              </div>
            </div>
          </div>

          {/* Assinatura / Billing — admin only */}
          <BillingSection />

          {/* Métricas Hub IA — admin only */}
          <MetricasHubSection />

          {/* Salvar fixo */}
          <div className="flex justify-end pb-2">
            <button type="submit" disabled={isSaving}
              className="flex items-center gap-2 px-6 py-3 rounded-xl text-white text-xs font-bold transition-fast"
              style={{ background: saveOk ? '#1A9E78' : 'var(--color-am-blue)', opacity: isSaving ? 0.7 : 1, cursor: isSaving ? 'not-allowed' : 'pointer' }}
              onMouseEnter={(e) => { if (!saveOk && !isSaving) e.currentTarget.style.background = 'var(--color-am-blue-hover)' }}
              onMouseLeave={(e) => { if (!saveOk && !isSaving) e.currentTarget.style.background = 'var(--color-am-blue)' }}>
              {isSaving
                ? <><Loader2 size={14} className="animate-spin" /> Salvando…</>
                : saveOk
                  ? <><CheckCircle size={14} /> Configurações salvas</>
                  : <><Save size={14} /> Salvar configurações</>}
            </button>
          </div>
        </div>
      </form>
    </div>
  )
}
