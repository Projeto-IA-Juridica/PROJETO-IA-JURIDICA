import type { Cliente, Processo, RAGDoc, OnboardingStatus } from './index'
import type { DashboardStats } from './analytics'
import type { CRMCard, CRMResumo } from './crm'
import type { Mensagem } from './chat'

const hoje = new Date()
const semanaAtras = new Date(hoje.getTime() - 7 * 86400000).toISOString()
const hojeIso = hoje.toISOString()

export const MOCK_ME = {
  id: 1,
  nome: 'Marcos Silva',
  email: 'marcos@admin.com',
  role: 'admin',
  escritorio_id: 1,
  oab: 'SP123456'
}

export const MOCK_CLIENTES: Cliente[] = [
  { id: 1, nome: 'João Pedro Andrade', telefone_whatsapp: '+55 11 98888-1111', cpf: '111.222.333-44', data_nascimento: '1985-04-12', profissao: 'Engenheiro', empresa: 'Tech Corp', status: 'ativo', ativo: true, crm_nivel: 'em_risco', crm_score: 42 },
  { id: 2, nome: 'Maria Stella Fontes', telefone_whatsapp: '+55 11 97777-2222', cpf: '222.333.444-55', data_nascimento: '1990-11-20', profissao: 'Médica', empresa: 'Hospital Central', status: 'ativo', ativo: true, crm_nivel: 'excelente', crm_score: 95 },
  { id: 3, nome: 'Carlos Eduardo Mendes', telefone_whatsapp: '+55 11 96666-3333', cpf: '333.444.555-66', data_nascimento: '1978-02-05', profissao: 'Comerciante', empresa: 'Mendes Varejo', status: 'ativo', ativo: true, crm_nivel: 'satisfeito', crm_score: 82 },
  { id: 4, nome: 'Luciana Martins Vaz', telefone_whatsapp: '+55 11 95555-4444', cpf: '444.555.666-77', data_nascimento: '1982-08-16', profissao: 'Professora', empresa: 'Escola Municipal', status: 'ativo', ativo: true, crm_nivel: 'critico', crm_score: 25 },
  { id: 5, nome: 'Roberto Almeida Souza', telefone_whatsapp: '+55 11 94444-5555', cpf: '555.666.777-88', data_nascimento: '1995-01-30', profissao: 'Publicitário', empresa: 'Agência Criativa', status: 'ativo', ativo: true, crm_nivel: 'neutro', crm_score: 65 },
]

export const MOCK_PROCESSOS: Record<number, Processo[]> = {
  1: [{ id: 101, numero_cnj: '0011223-44.2023.8.26.0001', tipo_acao: 'Indenizatória', polo_cliente: 'Autor', status: 'Em andamento', tribunal: 'TJSP', ultimo_andamento: 'Conclusos para o Juiz', data_ultimo_andamento: hojeIso, monitoramento_ativo: true, score_risco: 88, score_nivel: 'alto', score_interpretacao: 'O processo encontra-se concluso, mas devido à demora superior a 60 dias da vara e precedentes contrários da 2ª Câmara, o algoritmo indica alerta de risco probatório.' }],
  2: [{ id: 102, numero_cnj: '0022334-55.2022.5.02.0000', tipo_acao: 'Reclamatória Trabalhista', polo_cliente: 'Autor', status: 'Em andamento', tribunal: 'TRT2', ultimo_andamento: 'Audiência de Instrução Designada', data_ultimo_andamento: semanaAtras, monitoramento_ativo: true, score_risco: 25, score_nivel: 'baixo', score_interpretacao: 'Boas provas acostadas aos autos. Risco considerado baixo com base na documentação prévia da empresa.' }],
  3: [{ id: 103, numero_cnj: '0033445-66.2021.8.26.0100', tipo_acao: 'Ação de Cobrança', polo_cliente: 'Réu', status: 'Em andamento', tribunal: 'TJSP', ultimo_andamento: 'Juntada de Contestação', data_ultimo_andamento: semanaAtras, monitoramento_ativo: true, score_risco: 55, score_nivel: 'moderado', score_interpretacao: 'Situação equilibrada. Risco moderado pela ausência parcial de recibos assinados pelo Autor, devendo aguardar instrução processual.' }],
  4: [{ id: 104, numero_cnj: '0044556-77.2020.4.03.6100', tipo_acao: 'Mandado de Segurança', polo_cliente: 'Impetrante', status: 'Em andamento', tribunal: 'TRF3', ultimo_andamento: 'Liminar Indeferida', data_ultimo_andamento: semanaAtras, monitoramento_ativo: false, score_risco: 92, score_nivel: 'critico', score_interpretacao: 'O indeferimento liminar aliado ao entendimento do STJ no Tema Vinculante dificulta drasticamente a reforma no mérito.' }],
  5: [{ id: 105, numero_cnj: '0055667-88.2019.8.26.0053', tipo_acao: 'Execução Fiscal', polo_cliente: 'Executado', status: 'Suspenso', tribunal: 'TJSP', ultimo_andamento: 'Suspensão do processo (Art. 40 da LEF)', data_ultimo_andamento: semanaAtras, monitoramento_ativo: true, score_risco: 35, score_nivel: 'baixo', score_interpretacao: 'Execução sem movimentação de bloqueio iminente. Risco baixo temporário por prescrição intercorrente a ser analisada futuramente.' }]
}

export const MOCK_CHAT: Record<number, Mensagem[]> = {
  1: [
    { id: 1001, data: semanaAtras, direcao: 'recebida', mensagem_cliente: 'Bom dia, alguma novidade do meu processo?', mensagem_ia: null, tokens_input: 0, tokens_output: 0, custo_estimado: '0' },
    { id: 1002, data: semanaAtras, direcao: 'enviada', mensagem_cliente: null, mensagem_ia: 'Bom dia! Meu nome é Júlia da inteligência artificial do escritório Marcos Silva. Consultando seu processo 0011223-44.2023.8.26.0001 no TJSP, vi que o processo foi recentemente encaminhado ao Juiz para decisão. Esta etapa costuma demorar algumas semanas. Há algo mais que eu possa verificar?', tokens_input: 250, tokens_output: 80, custo_estimado: '0.005' },
    { id: 1003, data: hojeIso, direcao: 'recebida', mensagem_cliente: 'Ah, estou muito preocupado, já era pra ter saído!', mensagem_ia: null, tokens_input: 0, tokens_output: 0, custo_estimado: '0' },
    { id: 1004, data: hojeIso, direcao: 'enviada', mensagem_cliente: null, mensagem_ia: 'Entendo perfeitamente sua preocupação, João. O prazo judicial as vezes fica estendido dependendo do volume na vara. Já notifiquei nossa equipe humana para avaliar a viabilidade de protocolar uma petição cobrando andamento amanhã cedo.', intencao: 'insatisfacao_demora', usando_fallback: false, tokens_input: 420, tokens_output: 65, custo_estimado: '0.008' }
  ]
}

export const MOCK_CRM_CLIENTES: CRMCard[] = MOCK_CLIENTES.map(c => ({
  id: c.id,
  nome: c.nome,
  telefone_whatsapp: c.telefone_whatsapp,
  crm_nivel: c.crm_nivel as any,
  crm_score: c.crm_score ?? 0,
  crm_resumo: c.id === 1 ? 'Cliente irritado com a falta de andamento judicial. Exigiu retornos mas o tempo da justiça está fora do controle do escritório.' : c.id === 2 ? 'Cliente muito elogiou o último contato, satisfeita com a perícia recente.' : 'Comunicação regular, sem engajamento expressivo no WhatsApp recentemente.',
  crm_acao_sugerida: c.crm_nivel === 'critico' || c.crm_nivel === 'em_risco' ? 'Fazer uma ligação humana para acalmar os ânimos e explicar os ritos processuais detalhadamente.' : null,
  crm_analisado_em: hojeIso,
  total_processos: 1,
  nps_medio: c.crm_score ? (c.crm_score / 20) : null,
  ultimo_contato: semanaAtras
}))

export const MOCK_CRM_RESUMO: CRMResumo = {
  excelente: 1,
  satisfeito: 1,
  neutro: 1,
  em_risco: 1,
  critico: 1,
  score_medio_escritorio: 61.8,
  sem_analise: 0
}

export const MOCK_ANALYTICS: DashboardStats = {
  total_interacoes: 342,
  clientes_ativos: 45,
  nps_medio: 8.2,
  percentual_autonomia: 85.4,
  tempo_resposta_medio_ms: 1200,
  interacoes_sem_humano: 292,
  horas_economizadas: 24.5,
  custo_total_usd: 1.4502,
  escalacoes_pendentes: 3,
  tendencia_semanal: [
    { semana: 'W1', total_interacoes: 65, nps_medio: 8.1, autonomia_pct: 82 },
    { semana: 'W2', total_interacoes: 89, nps_medio: 7.9, autonomia_pct: 80 },
    { semana: 'W3', total_interacoes: 104, nps_medio: 8.4, autonomia_pct: 86 },
    { semana: 'W4', total_interacoes: 84, nps_medio: 8.6, autonomia_pct: 89 }
  ],
  por_cliente: [
    { cliente_id: 1, nome: 'João Pedro Andrade', nps_medio: 2.1, total_interacoes: 14, ultimo_contato_dias: 0, em_risco: true, sem_avaliacao: false },
    { cliente_id: 4, nome: 'Luciana Martins Vaz', nps_medio: 3.5, total_interacoes: 22, ultimo_contato_dias: 1, em_risco: true, sem_avaliacao: false },
    { cliente_id: 2, nome: 'Maria Stella Fontes', nps_medio: 9.8, total_interacoes: 4, ultimo_contato_dias: 4, em_risco: false, sem_avaliacao: false },
  ]
}

export const MOCK_RAG_DOCS: RAGDoc[] = [
  { id: 1, titulo: 'Guia de Diretrizes CLT Anual', tipo: 'peticao', total_chunks: 42, criado_em: semanaAtras },
  { id: 2, titulo: 'Jurisprudência STJ - Danos Morais Telecom', tipo: 'jurisprudencia', total_chunks: 15, criado_em: semanaAtras },
  { id: 3, titulo: 'Contrato de Honorários Padrão', tipo: 'tese', total_chunks: 6, criado_em: semanaAtras }
]

export const MOCK_STATUS: OnboardingStatus = {
  onboarding_completo: true,
  etapa_atual: 5,
  percentual_completo: 100,
  proxima_etapa: null,
  etapas: [
    { numero: 1, nome: 'Registro Básico', concluida: true, descricao: 'Informações iniciais' },
    { numero: 2, nome: 'Configuração RAG', concluida: true, descricao: 'Teses do escritório' },
    { numero: 3, nome: 'Identidade IA', concluida: true, descricao: 'Persona e tom' },
    { numero: 4, nome: 'Conexão WhatsApp', concluida: true, descricao: 'Escaneou QR Code' },
  ],
  escritorio: { id: 1, nome: 'Marcos Silva Advogados', persona_nome: 'Júlia', persona_tom: 'Empático e Acolhedor', whatsapp_conectado: true }
}
