/**
 * Painel interno da Máquina de Vendas — self-contained.
 * Leads quentes no topo (ação humana), funil ao vivo, upload de planilha e
 * fila de revisão. Estilos inline/locais; zero dependência do app do cliente.
 */

import { useMemo, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { Upload, Flame, AlertTriangle, Check, Loader2, ExternalLink } from 'lucide-react'
import {
  getFunil, getExcecoes, getQuentes, importarPlanilha, editarMensagem, aprovarExcecao,
  FUNIL_ORDEM, GATILHO_LABEL, type AlvoExcecao,
} from './api'

const card: CSSProperties = {
  background: 'var(--card)', border: '1px solid var(--border)', borderRadius: 16, padding: 20,
}

function Section({ icon, title, desc, children }: { icon: ReactNode; title: string; desc: string; children: ReactNode }) {
  return (
    <section style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <div style={{ width: 40, height: 40, borderRadius: 14, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(58,122,184,0.1)', border: '1px solid rgba(58,122,184,0.18)' }}>{icon}</div>
        <div>
          <h2 style={{ margin: 0, fontSize: 18, fontWeight: 800, letterSpacing: '-0.01em' }}>{title}</h2>
          <p style={{ margin: '2px 0 0', fontSize: 12, color: 'var(--muted)' }}>{desc}</p>
        </div>
      </div>
      {children}
    </section>
  )
}

function FunilView() {
  const { data: funil } = useQuery({ queryKey: ['funil'], queryFn: getFunil, refetchInterval: 15000 })
  const max = useMemo(() => Math.max(1, ...Object.values(funil ?? {})), [funil])
  return (
    <div style={{ ...card, display: 'flex', flexDirection: 'column', gap: 10 }}>
      {FUNIL_ORDEM.map(({ status, label, cor }) => {
        const n = funil?.[status] ?? 0
        return (
          <div key={status} style={{ display: 'grid', gridTemplateColumns: '130px 1fr 36px', alignItems: 'center', gap: 12 }}>
            <span style={{ fontSize: 12, color: 'var(--secondary)', textAlign: 'right' }}>{label}</span>
            <div style={{ height: 24, borderRadius: 6, overflow: 'hidden', background: `color-mix(in srgb, ${cor} 8%, transparent)` }}>
              <motion.div initial={{ width: 0 }} animate={{ width: `${(n / max) * 100}%` }} transition={{ duration: 0.7, ease: [0.4, 0, 0.2, 1] }} style={{ height: '100%', borderRadius: 6, background: cor }} />
            </div>
            <span className="tabnum" style={{ fontSize: 14, fontWeight: 700 }}>{n}</span>
          </div>
        )
      })}
    </div>
  )
}

function UploadCard() {
  const qc = useQueryClient()
  const inputRef = useRef<HTMLInputElement>(null)
  const [msg, setMsg] = useState<string | null>(null)
  const mut = useMutation({
    mutationFn: importarPlanilha,
    onSuccess: (r) => { setMsg(`${r.importados} importados · ${r.para_enriquecer} p/ enriquecer · ${r.desqualificados + r.classe_c_ignorados} filtrados fora`); qc.invalidateQueries({ queryKey: ['funil'] }) },
    onError: () => setMsg('Falha ao importar. Confira o cabeçalho do CSV.'),
  })
  return (
    <div style={{ ...card, display: 'flex', flexDirection: 'column', gap: 12 }}>
      <p style={{ margin: 0, fontSize: 12, color: 'var(--muted)' }}>
        CSV: nome_escritorio, nome_contato, oab, whatsapp, cidade, area, num_advogados, tem_vaga, anuncia, instagram_ativo, whatsapp_publico, <b>processo_cnj</b>
      </p>
      <input ref={inputRef} type="file" accept=".csv" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) mut.mutate(f) }} />
      <button onClick={() => inputRef.current?.click()} disabled={mut.isPending}
        style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, height: 44, borderRadius: 12, fontWeight: 700, color: '#fff', background: 'var(--blue)', opacity: mut.isPending ? 0.6 : 1 }}>
        {mut.isPending ? <Loader2 size={18} className="spin" /> : <Upload size={18} />}
        {mut.isPending ? 'Importando…' : 'Subir planilha de alvos'}
      </button>
      {msg && <p style={{ margin: 0, fontSize: 12, color: 'var(--secondary)' }}>{msg}</p>}
    </div>
  )
}

function CardExcecao({ alvo }: { alvo: AlvoExcecao }) {
  const qc = useQueryClient()
  const [texto, setTexto] = useState(alvo.mensagem ?? '')
  const invalidar = () => { qc.invalidateQueries({ queryKey: ['excecao'] }); qc.invalidateQueries({ queryKey: ['funil'] }) }
  const salvar = useMutation({ mutationFn: () => editarMensagem(alvo.id, texto) })
  const aprovar = useMutation({ mutationFn: () => aprovarExcecao(alvo.id), onSuccess: invalidar })
  return (
    <div style={{ ...card, padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontWeight: 700, fontSize: 14 }}>{alvo.escritorio}</span>
        <span style={{ fontSize: 10, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', padding: '2px 8px', borderRadius: 99, background: 'rgba(208,128,16,0.12)', color: 'var(--amber)' }}>confiança {alvo.confianca ?? 0}</span>
      </div>
      {alvo.observacao && <p style={{ margin: 0, fontSize: 12, color: 'var(--amber)' }}>⚠ {alvo.observacao}</p>}
      <textarea value={texto} onChange={(e) => setTexto(e.target.value)} rows={5}
        style={{ width: '100%', fontSize: 13, borderRadius: 12, padding: 12, resize: 'none', color: 'var(--ink)', background: 'var(--bg)', border: '1px solid var(--border)' }} />
      <div style={{ display: 'flex', gap: 8 }}>
        <button onClick={() => salvar.mutate()} style={{ flex: 1, height: 36, borderRadius: 8, fontSize: 13, fontWeight: 600, color: 'var(--secondary)', background: 'transparent', border: '1px solid var(--border)' }}>
          {salvar.isPending ? 'Salvando…' : 'Salvar edição'}
        </button>
        <button onClick={() => aprovar.mutate()} style={{ flex: 1, height: 36, borderRadius: 8, fontSize: 13, fontWeight: 700, color: '#fff', background: 'var(--green)', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
          <Check size={15} /> Aprovar p/ envio
        </button>
      </div>
    </div>
  )
}

export default function VendasPage() {
  const { data: excecoes } = useQuery({ queryKey: ['excecao'], queryFn: getExcecoes, refetchInterval: 20000 })
  const { data: quentes } = useQuery({ queryKey: ['quentes'], queryFn: getQuentes, refetchInterval: 12000 })
  const vazio: CSSProperties = { ...card, textAlign: 'center', fontSize: 13, color: 'var(--muted)' }

  return (
    <div style={{ maxWidth: 1000, margin: '0 auto', padding: '28px 16px', display: 'flex', flexDirection: 'column', gap: 32 }}>
      <div>
        <h1 style={{ margin: 0, fontSize: 24, fontWeight: 800, letterSpacing: '-0.02em' }}>Máquina de Vendas</h1>
        <p style={{ margin: '4px 0 0', fontSize: 14, color: 'var(--muted)' }}>Uso interno. A Clara prospecta, qualifica e passa o bastão — você entra nos quentes.</p>
      </div>

      <Section icon={<Flame size={18} color="var(--red)" />} title="Leads quentes" desc="Handoff da Clara — SLA de 15 min">
        {quentes && quentes.length > 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {quentes.map((q) => (
              <div key={q.id} style={{ ...card, padding: 16, display: 'flex', alignItems: 'center', gap: 16, border: '1px solid rgba(200,48,48,0.25)' }}>
                <div style={{ width: 40, height: 40, borderRadius: 99, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(200,48,48,0.1)', flexShrink: 0 }}><Flame size={18} color="var(--red)" /></div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 700, fontSize: 14, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{q.escritorio}{q.contato ? ` — ${q.contato}` : ''}</div>
                  <div style={{ fontSize: 12, color: 'var(--muted)' }}>{q.gatilho ? GATILHO_LABEL[q.gatilho] ?? q.gatilho : 'lead quente'}{q.cidade ? ` · ${q.cidade}` : ''}{q.socio ? ` · para ${q.socio}` : ''}</div>
                </div>
                <a href={`https://wa.me/${q.whatsapp.replace(/\D/g, '')}`} target="_blank" rel="noreferrer" style={{ display: 'flex', alignItems: 'center', gap: 6, height: 36, padding: '0 12px', borderRadius: 8, fontSize: 13, fontWeight: 700, color: '#fff', background: 'var(--green)', flexShrink: 0 }}>Abrir <ExternalLink size={14} /></a>
              </div>
            ))}
          </div>
        ) : (
          <div style={vazio}>Nenhum lead quente agora. A Clara avisa aqui e no seu WhatsApp quando um esquentar.</div>
        )}
      </Section>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 24 }}>
        <Section icon={<Flame size={18} color="var(--blue)" />} title="Funil" desc="Atualiza a cada 15s"><FunilView /></Section>
        <Section icon={<Upload size={18} color="var(--blue)" />} title="Alimentar a máquina" desc="Sua planilha vira abordagem"><UploadCard /></Section>
      </div>

      <Section icon={<AlertTriangle size={18} color="var(--amber)" />} title="Revisão humana" desc="Só os espelhos que a validação não teve certeza">
        {excecoes && excecoes.length > 0 ? (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 12 }}>
            {excecoes.map((a) => <CardExcecao key={a.id} alvo={a} />)}
          </div>
        ) : (
          <div style={{ ...vazio, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}><Check size={16} color="var(--green)" /> Fila limpa. Tudo que estava duvidoso já foi revisado.</div>
        )}
      </Section>
    </div>
  )
}
