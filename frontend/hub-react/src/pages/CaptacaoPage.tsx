import { motion } from 'framer-motion'
import {
  Target, Search, Dna, Sparkles, Building2, User,
  ShieldCheck, Clock, CheckCircle2,
} from 'lucide-react'

const FUNCIONALIDADES = [
  {
    icon: <Search size={14} style={{ color: '#3A7AB8' }} />,
    titulo: 'Descoberta por tipo de ação',
    descricao: 'Busca automática em tribunais por processos do seu ramo (trabalhista, cível, família) e identifica as partes envolvidas.',
  },
  {
    icon: <Dna size={14} style={{ color: '#1A9E78' }} />,
    titulo: 'Compatibilidade com o DNA do escritório',
    descricao: 'Cada lead é pontuado pela IA com base no perfil de causas que o seu escritório já domina.',
  },
  {
    icon: <Target size={14} style={{ color: '#D08010' }} />,
    titulo: 'Filtro de partes sem advogado',
    descricao: 'Prioriza litigantes que ainda não têm representação jurídica — a janela de oportunidade mais valiosa.',
  },
  {
    icon: <Building2 size={14} style={{ color: '#3A7AB8' }} />,
    titulo: 'Enriquecimento B2B e B2C',
    descricao: 'Para empresas: CNPJ, porte, setor e sócios via Receita Federal. Para pessoas: polo processual e histórico público.',
  },
  {
    icon: <Sparkles size={14} style={{ color: '#8B5CF6' }} />,
    titulo: 'Abordagem sugerida pela IA',
    descricao: 'Cada lead vem acompanhado de um texto personalizado sugerindo como iniciar o contato com aquele potencial cliente.',
  },
  {
    icon: <ShieldCheck size={14} style={{ color: '#1A9E78' }} />,
    titulo: 'Conformidade LGPD nativa',
    descricao: 'Nenhum dado pessoal sensível (CPF, telefone, e-mail) é armazenado. Apenas informações públicas processuais.',
  },
]

export default function CaptacaoPage() {
  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="flex flex-col h-full w-full max-w-3xl mx-auto">

        {/* Header */}
        <div className="flex-shrink-0 px-6 pt-5 pb-4">
          <h2 className="text-sm font-bold text-am-ink tracking-tight">Captação</h2>
          <p className="text-xs text-am-muted mt-0.5">Leads qualificados pela IA</p>
        </div>

        {/* Conteúdo */}
        <div className="flex-1 overflow-y-auto">
          <div className="px-6 pb-8 space-y-5">

            {/* Badge Em desenvolvimento */}
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.35 }}
              className="flex items-center gap-2"
            >
              <span
                className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider"
                style={{ background: 'rgba(208,128,16,0.10)', color: '#D08010', border: '1px solid rgba(208,128,16,0.25)' }}
              >
                <Clock size={9} />
                Em desenvolvimento
              </span>
            </motion.div>

            {/* Card principal */}
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, delay: 0.05 }}
              className="bg-white rounded-2xl overflow-hidden"
              style={{ border: '1px solid var(--color-am-border)', boxShadow: '0 2px 12px rgba(12,30,48,0.06)' }}
            >
              {/* Topo gradiente */}
              <div
                className="px-6 py-7 flex flex-col items-center text-center gap-4"
                style={{ background: 'linear-gradient(160deg, rgba(18,72,190,0.05) 0%, rgba(26,158,120,0.05) 100%)' }}
              >
                <div
                  className="w-14 h-14 rounded-2xl flex items-center justify-center"
                  style={{ background: 'linear-gradient(135deg,#1248BE,#3A7AB8)', boxShadow: '0 4px 16px rgba(18,72,190,0.25)' }}
                >
                  <Target size={24} color="white" strokeWidth={1.8} />
                </div>

                <div className="space-y-1.5">
                  <h3 className="text-base font-bold text-am-ink">Captação Inteligente de Leads</h3>
                  <p className="text-xs text-am-secondary leading-relaxed max-w-[340px]">
                    Estamos desenvolvendo um motor de prospecção que varre tribunais automaticamente,
                    identifica litigantes sem representação jurídica e os qualifica com base no perfil do seu escritório.
                  </p>
                </div>
              </div>

              {/* Divisor */}
              <div className="h-px" style={{ background: 'var(--color-am-border)' }} />

              {/* O que estará disponível */}
              <div className="px-5 py-4">
                <p className="text-[10px] font-bold text-am-muted uppercase tracking-wider mb-3">
                  O que estará disponível
                </p>
                <div className="space-y-3">
                  {FUNCIONALIDADES.map((f, i) => (
                    <motion.div
                      key={f.titulo}
                      initial={{ opacity: 0, x: -8 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ duration: 0.3, delay: 0.1 + i * 0.05 }}
                      className="flex items-start gap-3"
                    >
                      <div
                        className="w-7 h-7 rounded-xl flex items-center justify-center flex-shrink-0 mt-0.5"
                        style={{ background: 'rgba(12,30,48,0.04)', border: '1px solid var(--color-am-border)' }}
                      >
                        {f.icon}
                      </div>
                      <div>
                        <p className="text-xs font-semibold text-am-ink leading-snug">{f.titulo}</p>
                        <p className="text-[11px] text-am-muted leading-relaxed mt-0.5">{f.descricao}</p>
                      </div>
                    </motion.div>
                  ))}
                </div>
              </div>
            </motion.div>

            {/* Card de tipos de lead */}
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, delay: 0.2 }}
              className="grid grid-cols-2 gap-3"
            >
              {[
                {
                  icon: <Building2 size={16} style={{ color: '#3A7AB8' }} />,
                  label: 'B2B — Empresas',
                  desc: 'Pessoas jurídicas litigando sem representação',
                  color: '#3A7AB8',
                  bg: 'rgba(58,122,184,0.07)',
                },
                {
                  icon: <User size={16} style={{ color: '#1A9E78' }} />,
                  label: 'B2C — Pessoas',
                  desc: 'Pessoas físicas em processos públicos',
                  color: '#1A9E78',
                  bg: 'rgba(26,158,120,0.07)',
                },
              ].map((item) => (
                <div
                  key={item.label}
                  className="bg-white rounded-2xl p-4 flex flex-col gap-2"
                  style={{ border: '1px solid var(--color-am-border)' }}
                >
                  <div className="w-8 h-8 rounded-xl flex items-center justify-center" style={{ background: item.bg }}>
                    {item.icon}
                  </div>
                  <div>
                    <p className="text-xs font-bold" style={{ color: item.color }}>{item.label}</p>
                    <p className="text-[10px] text-am-muted mt-0.5 leading-snug">{item.desc}</p>
                  </div>
                </div>
              ))}
            </motion.div>

            {/* Rodapé informativo */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.4, delay: 0.3 }}
              className="flex items-start gap-2.5 rounded-2xl p-3.5"
              style={{ background: 'rgba(58,122,184,0.05)', border: '1px solid rgba(58,122,184,0.15)' }}
            >
              <CheckCircle2 size={13} className="flex-shrink-0 mt-0.5" style={{ color: '#3A7AB8' }} />
              <p className="text-[11px] leading-relaxed" style={{ color: '#1A3A5C' }}>
                Esta funcionalidade será liberada em breve. As demais áreas do sistema — Hub IA, CRM,
                monitoramento de processos e atendimento via WhatsApp — já estão disponíveis e funcionando normalmente.
              </p>
            </motion.div>

          </div>
        </div>
      </div>
    </div>
  )
}
