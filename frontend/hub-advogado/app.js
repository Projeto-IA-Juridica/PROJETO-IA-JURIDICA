'use strict'

/* ══════════════════════════════════════════════════════
   Amicus — Hub do Advogado
   app.js — dados, estado e renderização
   ══════════════════════════════════════════════════════ */

// ── Constantes de apresentação ────────────────────────────

const RISK_COLOR = { baixo: '#1A9E78', moderado: '#D08010', alto: '#C83030' }
const RISK_LABEL = { baixo: 'Risco Baixo', moderado: 'Risco Moderado', alto: 'Risco Alto' }

const RISK_DESC = {
  baixo:
    'Este processo apresenta baixo risco. As condições são favoráveis — o tipo de ação tem bom histórico neste tribunal e não há fatores agravantes identificados. Você pode atender este cliente com tranquilidade.',
  moderado:
    'Este processo tem risco moderado. Há pontos de atenção que merecem acompanhamento próximo. Recomendamos manter o cliente bem informado sobre cada andamento.',
  alto:
    'Este processo apresenta alto risco. Fatores como complexidade da ação ou histórico desfavorável no tribunal aumentam a incerteza. Vale redobrar a atenção e alinhar as expectativas do cliente com clareza.',
}

const COMP_LABELS = {
  complexidade_juridica: 'Complexidade jurídica',
  duracao_estimada:      'Duração estimada',
  historico_vara:        'Histórico da vara',
  valor_causa:           'Valor da causa',
  fase_processual:       'Fase processual',
}

const TIPO_LABELS = {
  tese:          'Tese',
  jurisprudencia:'Jurisprudência',
  peticao:       'Petição',
  sentenca:      'Sentença',
  parecer:       'Parecer',
}

const INTENT_LABELS = {
  saudacao:                      'Boas-vindas',
  status_processo:               'Consulta de andamento',
  duvida_termo:                  'Dúvida jurídica',
  prazo:                         'Consulta de prazo',
  parecer_juridico:              'Parecer jurídico',
  estrategia_processual:         'Estratégia processual',
  negociacao:                    'Negociação',
  decisao_judicial_impacto_alto: 'Decisão de alto impacto',
  outro:                         'Atendimento geral',
}

const ESCALATION_INTENTS = new Set([
  'parecer_juridico',
  'estrategia_processual',
  'negociacao',
  'decisao_judicial_impacto_alto',
])

const AI_REPLIES = {
  processo:
    'O processo está na fase de instrução processual. O último andamento registrado indica que a audiência foi designada — este é um momento importante. Recomendo preparar documentos e testemunhas com antecedência.',
  prazo:
    'Os prazos processuais são contados em dias úteis, a partir da intimação formal. Para verificar datas exatas, recomendo consultar o portal e-SAJ ou contatar diretamente o cartório da vara.',
  risco:
    'A análise de risco considera 5 componentes: complexidade jurídica, histórico do juízo, fase processual, valor em disputa e estimativa de duração. Cada fator é ponderado para gerar o score final de 0 a 100.',
  default:
    'Com base nos dados do processo, o próximo passo recomendado é aguardar a movimentação agendada. Fique à vontade para perguntar sobre termos jurídicos, prazos ou qualquer outra dúvida.',
}

// ── Documentos do escritório (base RAG) ───────────────────

const DOCS = [
  { titulo: 'Tese — Danos Morais por Falha na Prestação de Serviços', tipo: 'tese', chunks: 8 },
  { titulo: 'Jurisprudência STJ 2023 — Responsabilidade Civil', tipo: 'jurisprudencia', chunks: 12 },
  { titulo: 'Petição Modelo — Indenização Consumidor', tipo: 'peticao', chunks: 6 },
]

// ── Dados dos clientes (mock — substitua pela API) ────────

const CLIENTES = [
  {
    id: 1,
    nome: 'João da Silva',
    telefone: '(11) 99999-0001',
    cpf: '123.456.789-00',
    nascimento: '15/03/1980',
    profissao: 'Engenheiro Civil',
    empresa: 'Tech Corp Ltda.',
    status: 'ativo',
    processo: {
      cnj: '0001234-56.2023.8.26.0100',
      tribunal: 'TJ-SP — 3ª Vara Cível',
      classe: 'Procedimento Comum Cível',
      assunto: 'Indenização por Danos Morais',
      polo: 'autor',
      ajuizamento: '15/03/2023',
      ultimo_andamento: 'Audiência de instrução e julgamento designada',
      data_andamento: '20/11/2024',
      andamentos: [
        { date: '20/11/2024', text: 'Audiência de instrução e julgamento designada', active: true },
        { date: '01/10/2024', text: 'Manifestação das partes — petição protocolada no sistema', active: false },
        { date: '15/08/2024', text: 'Juntada de documentos — réplica à contestação', active: false },
        { date: '02/07/2024', text: 'Contestação apresentada pela parte contrária', active: false },
      ],
    },
    score: {
      valor: 72,
      nivel: 'alto',
      componentes: {
        complexidade_juridica: 80,
        duracao_estimada: 65,
        historico_vara: 70,
        valor_causa: 60,
        fase_processual: 75,
      },
    },
    chat: [
      {
        role: 'assistant',
        content: 'Olá, João! Bem-vindo ao Amicus. Estou acompanhando seu processo de indenização no TJ-SP. A última movimentação indica audiência agendada — como posso ajudar hoje?',
        intencao: 'saudacao',
      },
    ],
  },
  {
    id: 2,
    nome: 'Maria Santos',
    telefone: '(21) 98888-0002',
    cpf: '987.654.321-00',
    nascimento: '22/07/1975',
    profissao: 'Médica',
    empresa: 'Hospital ABC',
    status: 'ativo',
    processo: null,
    score: null,
    chat: [
      {
        role: 'assistant',
        content: 'Olá, Maria! Seja bem-vinda ao Amicus. Ainda não há processo vinculado ao seu cadastro. Caso queira vincular um processo ou tirar dúvidas jurídicas, estou à disposição.',
        intencao: 'saudacao',
      },
    ],
  },
  {
    id: 3,
    nome: 'Carlos Oliveira',
    telefone: '(31) 97777-0003',
    cpf: '456.789.012-00',
    nascimento: '08/11/1990',
    profissao: 'Empresário',
    empresa: 'Oliveira Holdings',
    status: 'ativo',
    processo: {
      cnj: '0005678-90.2022.8.26.0053',
      tribunal: 'TJ-SP — 1ª Vara Empresarial',
      classe: 'Ação de Cobrança',
      assunto: 'Inadimplemento Contratual',
      polo: 'reu',
      ajuizamento: '10/06/2022',
      ultimo_andamento: 'Sentença — procedência parcial do pedido',
      data_andamento: '12/09/2024',
      andamentos: [
        { date: '12/09/2024', text: 'Sentença — procedência parcial do pedido', active: true },
        { date: '28/06/2024', text: 'Alegações finais — prazo encerrado', active: false },
        { date: '14/03/2024', text: 'Audiência de instrução realizada', active: false },
        { date: '10/01/2024', text: 'Designação de audiência', active: false },
      ],
    },
    score: {
      valor: 34,
      nivel: 'baixo',
      componentes: {
        complexidade_juridica: 40,
        duracao_estimada: 30,
        historico_vara: 25,
        valor_causa: 45,
        fase_processual: 30,
      },
    },
    chat: [
      {
        role: 'assistant',
        content: 'Olá, Carlos! Seu processo de cobrança teve movimentação recente favorável — sentença com procedência parcial. Posso detalhar os próximos passos ou explicar os termos da decisão.',
        intencao: 'saudacao',
      },
    ],
  },
]

// ── Estado da aplicação ───────────────────────────────────

const state = {
  activeId: 1,
  activeTab: 'processo',
  typing: false,
  // Histórico de chat por cliente (inicializado com o greeting)
  chatHistories: Object.fromEntries(CLIENTES.map(c => [c.id, [...c.chat]])),
}

// ── Inicialização ─────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  renderStats()
  renderClientList()
  selectClient(1)

  document.getElementById('search-input').addEventListener('input', e => {
    renderClientList(e.target.value)
  })
})

// ── Stats strip ───────────────────────────────────────────

function renderStats() {
  const total = CLIENTES.length
  const comProc = CLIENTES.filter(c => c.processo).length
  const risco = CLIENTES.filter(c => c.score?.nivel === 'alto').length

  document.getElementById('stats-strip').innerHTML = `
    <div class="stat-cell">
      <div class="stat-val">${total}</div>
      <div class="stat-lbl">Clientes</div>
    </div>
    <div class="stat-cell">
      <div class="stat-val">${comProc}</div>
      <div class="stat-lbl">Com processo</div>
    </div>
    <div class="stat-cell">
      <div class="stat-val" style="color:#C83030">${risco}</div>
      <div class="stat-lbl">Risco alto</div>
    </div>
  `
}

// ── Lista de clientes ─────────────────────────────────────

function renderClientList(filter = '') {
  const el = document.getElementById('client-list')
  const filtered = CLIENTES.filter(c =>
    c.nome.toLowerCase().includes(filter.toLowerCase())
  )

  if (!filtered.length) {
    el.innerHTML = '<div style="padding:24px 12px;text-align:center;font-size:12px;color:#8AAAC0">Nenhum cliente encontrado</div>'
    return
  }

  el.innerHTML = filtered.map(c => clientItemHTML(c)).join('')

  filtered.forEach(c => {
    el.querySelector(`[data-id="${c.id}"]`).addEventListener('click', () => selectClient(c.id))
  })

  // Marca o ativo
  el.querySelectorAll('.client-item').forEach(el => {
    el.classList.toggle('active', parseInt(el.dataset.id) === state.activeId)
  })
}

function clientItemHTML(c) {
  const nivel = c.score?.nivel ?? null
  const borderColor = nivel ? RISK_COLOR[nivel] : '#A8C8E8'
  const badgeCls = nivel ?? 'none'
  const badgeLabel = nivel === 'alto' ? 'Alto' : nivel === 'moderado' ? 'Moderado' : nivel === 'baixo' ? 'Baixo' : '—'
  const sub = c.processo ? c.processo.classe : 'Sem processo vinculado'
  const init = c.nome.split(' ').slice(0, 2).map(n => n[0]).join('')

  return `
    <div class="client-item" data-id="${c.id}" style="border-left-color:${borderColor}">
      <div class="client-avatar">${init}</div>
      <div class="client-info">
        <div class="client-name">${c.nome}</div>
        <div class="client-sub">${sub}</div>
      </div>
      <span class="risk-badge ${badgeCls}">${badgeLabel}</span>
    </div>
  `
}

// ── Selecionar cliente ────────────────────────────────────

function selectClient(id) {
  state.activeId = id
  state.activeTab = 'processo'

  document.querySelectorAll('.client-item').forEach(el => {
    el.classList.toggle('active', parseInt(el.dataset.id) === id)
  })

  const c = CLIENTES.find(c => c.id === id)
  renderHeader(c)
  renderTabs(c)
  renderBody(c)
}

// ── Header ────────────────────────────────────────────────

function renderHeader(c) {
  const cnj = c.processo ? c.processo.cnj : 'Sem processo judicial vinculado'
  let badges = ''

  if (c.processo) {
    const polo = c.processo.polo
    badges += `<span class="polo-badge ${polo}">${polo === 'autor' ? 'Autor' : 'Réu'}</span>`
  }

  if (c.score) {
    const color = RISK_COLOR[c.score.nivel]
    badges += `
      <span class="score-chip" style="color:${color};background:${hexAlpha(color, 0.07)};border:1px solid ${hexAlpha(color, 0.18)}">
        ${c.score.valor}/100 · ${RISK_LABEL[c.score.nivel]}
      </span>
    `
  }

  document.getElementById('detail-header').innerHTML = `
    <div class="detail-header-row">
      <div>
        <div class="detail-name">${c.nome}</div>
        <div class="detail-cnj">${cnj}</div>
      </div>
      <div class="detail-badges">${badges}</div>
    </div>
  `
}

// ── Tabs ──────────────────────────────────────────────────

const TABS_DEF = [
  { id: 'processo',    icon: iconFile(),   label: 'Processo' },
  { id: 'score',       icon: iconBar(),    label: 'Score de Risco' },
  { id: 'chat',        icon: iconMsg(),    label: 'IA Assistente' },
  { id: 'documentos',  icon: iconBook(),   label: 'Documentos' },
]

function renderTabs(c) {
  document.getElementById('detail-tabs').innerHTML = TABS_DEF.map(t => {
    const disabled = (t.id === 'score' && !c.score) ? 'disabled' : ''
    const active = t.id === state.activeTab ? 'active' : ''
    return `
      <button class="tab-btn ${active}" data-tab="${t.id}" ${disabled}
              onclick="switchTab('${t.id}', ${c.id})">
        ${t.icon} ${t.label}
      </button>
    `
  }).join('')
}

function switchTab(tab, clientId) {
  const c = CLIENTES.find(c => c.id === clientId)
  if (tab === 'score' && !c.score) return
  state.activeTab = tab

  document.querySelectorAll('.tab-btn').forEach(el => {
    el.classList.toggle('active', el.dataset.tab === tab)
  })

  document.querySelectorAll('.tab-panel').forEach(el => {
    el.classList.toggle('active', el.id === `tab-${tab}`)
  })

  const chatPanel = document.getElementById('tab-chat')
  if (chatPanel) chatPanel.classList.toggle('active', tab === 'chat')

  if (tab === 'score') setTimeout(() => animateBars(), 40)
  if (tab === 'chat') {
    const msgs = document.getElementById('chat-messages')
    if (msgs) msgs.scrollTop = msgs.scrollHeight
  }
}

// ── Body ──────────────────────────────────────────────────

function renderBody(c) {
  document.getElementById('detail-body').innerHTML = `
    <div class="tab-panel active" id="tab-processo">
      ${renderProcessoTab(c)}
    </div>
    <div class="tab-panel" id="tab-score">
      ${renderScoreTab(c)}
    </div>
    <div id="tab-chat">
      ${renderChatPanel(c)}
    </div>
    <div class="tab-panel" id="tab-documentos">
      ${renderDocumentosTab()}
    </div>
  `
  bindChatInput(c.id)
}

// ── Tab: Processo ─────────────────────────────────────────

function renderProcessoTab(c) {
  const p = c.processo

  const cardCliente = `
    <div class="section">
      <div class="section-head">
        <span class="section-kicker">Cliente</span>
        <span class="status-badge">Ativo</span>
      </div>
      <div class="section-body">
        <div class="info-grid">
          ${infoItem('Nome completo', c.nome)}
          ${infoItem('CPF', c.cpf, true)}
          ${infoItem('Telefone', c.telefone, true)}
          ${infoItem('Nascimento', c.nascimento)}
          ${infoItem('Profissão', c.profissao)}
          ${infoItem('Empresa', c.empresa)}
        </div>
      </div>
    </div>
  `

  const cardProcesso = p ? `
    <div class="section" style="border-left:3px solid ${p.polo === 'autor' ? '#1A9E78' : '#C83030'}">
      <div class="section-head">
        <span class="section-kicker">Processo Judicial</span>
        <span class="polo-badge ${p.polo}">${p.polo === 'autor' ? 'Autor' : 'Réu'}</span>
      </div>
      <div class="section-body">
        <div class="info-grid">
          ${infoItem('Número CNJ', p.cnj, true)}
          ${infoItem('Polo', p.polo === 'autor' ? 'Autor' : 'Réu')}
          ${infoItem('Tribunal', p.tribunal)}
          ${infoItem('Classe', p.classe)}
          ${infoItem('Assunto', p.assunto)}
          ${infoItem('Ajuizamento', p.ajuizamento)}
          ${infoItem('Último andamento', p.ultimo_andamento)}
          ${infoItem('Data', p.data_andamento)}
        </div>
      </div>
    </div>
  ` : `
    <div class="section">
      <div class="section-head"><span class="section-kicker">Processo Judicial</span></div>
      <div class="section-body">
        <div class="empty-state">
          ${iconScale(28, '#A8C8E8')}
          <div style="font-size:13px;font-weight:500;color:#4A6A88;margin-top:8px">Sem processo vinculado</div>
          <div style="font-size:12px;color:#8AAAC0;margin-top:4px;max-width:220px">Este cliente não possui processo judicial cadastrado.</div>
        </div>
      </div>
    </div>
  `

  const cardAndamentos = p ? `
    <div class="section">
      <div class="section-head">
        <span class="section-kicker">Histórico de Andamentos</span>
      </div>
      <div class="section-body">
        ${p.andamentos.map(a => `
          <div class="andamento">
            <div class="andamento-line" style="background:${a.active ? '#3A7AB8' : 'rgba(168,200,232,.4)'}"></div>
            <div>
              <div class="andamento-date">${a.date}</div>
              <div class="andamento-text" style="color:${a.active ? '#0C1E30' : '#4A6A88'};font-weight:${a.active ? 500 : 400}">
                ${a.text}
              </div>
            </div>
          </div>
        `).join('')}
      </div>
    </div>
  ` : ''

  return `
    <div class="two-col" style="margin-bottom:0">${cardCliente}${cardProcesso}</div>
    ${cardAndamentos}
  `
}

function infoItem(label, value, mono = false) {
  return `
    <div>
      <div class="info-label">${label}</div>
      <div class="info-val${mono ? ' mono' : ''}">${value || '—'}</div>
    </div>
  `
}

// ── Tab: Score de Risco ───────────────────────────────────

function renderScoreTab(c) {
  if (!c.score) return `
    <div class="empty-state" style="margin:40px auto">
      ${iconBar(30, '#A8C8E8')}
      <div style="font-size:13px;font-weight:500;color:#4A6A88;margin-top:8px">Análise indisponível</div>
      <div style="font-size:12px;color:#8AAAC0;margin-top:4px">Processo judicial necessário para gerar o score.</div>
    </div>
  `

  const { valor, nivel, componentes } = c.score
  const color = RISK_COLOR[nivel]

  const comps = Object.entries(componentes).map(([key, val]) => {
    const c = val >= 65 ? '#C83030' : val >= 40 ? '#D08010' : '#1A9E78'
    const lbl = val >= 65 ? 'Desfavorável' : val >= 40 ? 'Atenção' : 'Favorável'
    return `
      <div class="comp-row">
        <div class="comp-label">${COMP_LABELS[key]}</div>
        <div class="comp-bar">
          <div class="progress-track" style="height:5px">
            <div class="progress-fill" data-target="${val}" style="background:${c}"></div>
          </div>
        </div>
        <div class="comp-status" style="color:${c}">${lbl}</div>
      </div>
    `
  }).join('')

  return `
    <div class="section" style="border-left:3px solid ${color}">
      <div class="section-body">
        <div class="score-overview">
          <div style="flex-shrink:0">
            <div class="score-big" style="color:${color}">${valor}</div>
            <div class="score-level" style="color:${color}">${RISK_LABEL[nivel]}</div>
          </div>
          <div style="flex:1">
            <div style="margin-bottom:12px">
              <div class="progress-track" style="height:8px">
                <div class="progress-fill" data-target="${valor}" style="background:${color}"></div>
              </div>
            </div>
            <p class="score-desc">${RISK_DESC[nivel]}</p>
          </div>
        </div>
      </div>
    </div>
    <details class="score-details" open>
      <summary class="score-details-summary">Como chegamos a esta análise? Ver detalhes</summary>
      <div class="section">
        <div class="section-head">
          <span class="section-kicker">Detalhamento dos componentes</span>
        </div>
        <div class="section-body">
          ${comps}
          <p class="score-caveat">
            Esta análise é de uso interno e não representa previsão de resultado (OAB Provimento 205/2021).
          </p>
        </div>
      </div>
    </details>
  `
}

function animateBars() {
  document.querySelectorAll('.progress-fill[data-target]').forEach(el => {
    el.style.width = el.dataset.target + '%'
  })
}

// ── Tab: Chat IA ──────────────────────────────────────────

function ragDocsForClient(c) {
  if (!c.processo) return [DOCS[1]]
  const assunto = (c.processo.assunto || '').toLowerCase()
  return DOCS.filter(d => {
    if (/dano|moral|indeniz|consumidor/.test(assunto)) return true
    if (/contrat|cobran|inadimpl/.test(assunto) && d.tipo === 'jurisprudencia') return true
    return d.tipo === 'jurisprudencia'
  })
}

function renderChatPanel(c) {
  const history = state.chatHistories[c.id] || []
  const msgs = history.map(m => bubbleHTML(m)).join('')
  const ragDocs = ragDocsForClient(c)

  const ragPanel = `
    <div class="rag-panel">
      <div class="rag-panel-title">
        ${iconBook(11, '#3A7AB8')}
        Documentos ativos para ${c.nome.split(' ')[0]}
      </div>
      <div class="rag-panel-docs">
        ${ragDocs.map(d => `
          <span class="rag-doc-chip">
            <span class="rag-doc-type">${TIPO_LABELS[d.tipo] ?? d.tipo}</span>
            ${d.titulo}
          </span>
        `).join('')}
      </div>
    </div>
  `

  return `
    <div class="chat-ai-strip">
      ${iconScale(12, '#3A7AB8')}
      IA configurada como <strong style="color:#0C1E30;margin:0 4px">Dra. Camila</strong>
      · Tom formal · Verifica fatos antes de responder
    </div>
    ${ragPanel}
    <div class="chat-messages" id="chat-messages">${msgs}</div>
    <div class="chat-input-area">
      <textarea id="chat-input" class="chat-input" rows="1"
        placeholder="Pergunte sobre o processo, termos jurídicos ou tire dúvidas…"></textarea>
      <button id="send-btn" class="send-btn" onclick="handleSend(${c.id})">
        ${iconSend()}
      </button>
    </div>
  `
}

function bubbleHTML(msg) {
  const isUser = msg.role === 'user'
  const intentLabel = msg.intencao ? (INTENT_LABELS[msg.intencao] ?? msg.intencao) : ''

  let badges = ''
  if (!isUser && intentLabel) {
    badges += `<span class="msg-badge intent">${intentLabel}</span>`
    if (msg.ragAtivo)  badges += `<span class="msg-badge rag">📚 Usando documentos do escritório</span>`
    if (msg.escalacao) badges += `<span class="msg-badge escalacao">🚨 Questão importante — advogado notificado</span>`
  }

  return `
    <div class="msg-wrap ${msg.role}">
      ${!isUser ? '<div class="msg-sender">Dra. Camila · Amicus IA</div>' : ''}
      <div class="bubble ${msg.role}">${msg.content}</div>
      ${badges ? `<div class="msg-badges">${badges}</div>` : ''}
    </div>
  `
}

function bindChatInput(clientId) {
  const input = document.getElementById('chat-input')
  if (!input) return
  input.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(clientId) }
  })
  input.addEventListener('input', () => {
    input.style.height = 'auto'
    input.style.height = Math.min(input.scrollHeight, 100) + 'px'
  })
}

async function handleSend(clientId) {
  if (state.typing) return
  const input = document.getElementById('chat-input')
  const btn = document.getElementById('send-btn')
  const text = (input?.value || '').trim()
  if (!text) return

  input.value = ''
  input.style.height = 'auto'

  const userMsg = { role: 'user', content: text }
  state.chatHistories[clientId].push(userMsg)

  const msgs = document.getElementById('chat-messages')
  msgs.insertAdjacentHTML('beforeend', bubbleHTML(userMsg))
  msgs.scrollTop = msgs.scrollHeight

  // Typing indicator
  state.typing = true
  if (btn) btn.disabled = true

  msgs.insertAdjacentHTML('beforeend', `
    <div class="msg-wrap assistant" id="typing-indicator">
      <div class="msg-sender">Dra. Camila está digitando…</div>
      <div class="bubble assistant">
        <div class="typing-dots"><span></span><span></span><span></span></div>
      </div>
    </div>
  `)
  msgs.scrollTop = msgs.scrollHeight

  await sleep(1100 + Math.random() * 600)

  document.getElementById('typing-indicator')?.remove()

  const q = text.toLowerCase()

  // Determina intenção
  let intencao
  if (/parecer|fundamentação|fundamento/.test(q))           intencao = 'parecer_juridico'
  else if (/estratégia|estrategia|abordagem|tática/.test(q)) intencao = 'estrategia_processual'
  else if (/negociação|negociacao|acordo|conciliação/.test(q)) intencao = 'negociacao'
  else if (/decisão|decisao|sentença|sentenca|acórdão/.test(q)) intencao = 'decisao_judicial_impacto_alto'
  else if (/processo|andamento|audiência|audiencia|movimentação/.test(q)) intencao = 'status_processo'
  else if (/prazo|data|quando|vencimento/.test(q))           intencao = 'prazo'
  else if (/termo|significa|conceito|definição/.test(q))     intencao = 'duvida_termo'
  else                                                        intencao = 'outro'

  // Flags RAG e escalação
  const ragAtivo  = /processo|andamento|prazo|risco|dano|indeniz|contrat|cobran|réu|autor/.test(q)
  const escalacao = ESCALATION_INTENTS.has(intencao)

  // Escolhe resposta pela semântica da mensagem
  let reply
  if (/processo|andamento|audiência|audiencia|movimentação/.test(q))
    reply = AI_REPLIES.processo
  else if (/prazo|data|quando|vencimento/.test(q))
    reply = AI_REPLIES.prazo
  else if (/risco|score|análise|analise|componente/.test(q))
    reply = AI_REPLIES.risco
  else
    reply = AI_REPLIES.default

  const aiMsg = { role: 'assistant', content: reply, intencao, ragAtivo, escalacao }
  state.chatHistories[clientId].push(aiMsg)
  msgs.insertAdjacentHTML('beforeend', bubbleHTML(aiMsg))
  msgs.scrollTop = msgs.scrollHeight

  state.typing = false
  if (btn) btn.disabled = false
}

// ── Tab: Documentos ───────────────────────────────────────

function renderDocumentosTab() {
  const totalChunks = DOCS.reduce((a, d) => a + d.chunks, 0)

  const list = DOCS.map(d => `
    <div class="doc-item">
      <div style="flex:1;min-width:0">
        <div style="font-size:13px;font-weight:500;color:#0C1E30">${d.titulo}</div>
        <span class="doc-type-badge">${TIPO_LABELS[d.tipo] ?? d.tipo}</span>
      </div>
      <div style="font-size:11px;color:#8AAAC0;flex-shrink:0">${d.chunks} chunks</div>
    </div>
  `).join('')

  return `
    <div class="section">
      <div class="section-head">
        <span class="section-kicker">Base de Conhecimento</span>
        <span style="font-size:11px;color:#8AAAC0">${DOCS.length} documentos · ${totalChunks} chunks</span>
      </div>
      <div class="section-body">${list}</div>
    </div>

    <div class="upload-zone">
      ${iconUpload(26, '#A8C8E8')}
      <div style="font-size:13px;font-weight:500;color:#4A6A88;margin-top:10px;margin-bottom:5px">
        Adicionar documento ao escritório
      </div>
      <div style="font-size:12px;color:#8AAAC0">
        PDF ou TXT — petições, teses, jurisprudências, pareceres
      </div>
      <button class="upload-btn">Selecionar arquivo</button>
    </div>
  `
}

// ── Ícones SVG ────────────────────────────────────────────

function iconFile(size = 12, color = 'currentColor') {
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none"
    stroke="${color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
    <polyline points="14 2 14 8 20 8"/>
  </svg>`
}

function iconBar(size = 12, color = 'currentColor') {
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none"
    stroke="${color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <line x1="18" y1="20" x2="18" y2="10"/>
    <line x1="12" y1="20" x2="12" y2="4"/>
    <line x1="6"  y1="20" x2="6"  y2="14"/>
  </svg>`
}

function iconMsg(size = 12, color = 'currentColor') {
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none"
    stroke="${color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
  </svg>`
}

function iconBook(size = 12, color = 'currentColor') {
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none"
    stroke="${color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
    <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
  </svg>`
}

function iconScale(size = 12, color = 'currentColor') {
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none"
    stroke="${color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
  </svg>`
}

function iconUpload(size = 24, color = 'currentColor') {
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none"
    stroke="${color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
    <polyline points="17 8 12 3 7 8"/>
    <line x1="12" y1="3" x2="12" y2="15"/>
  </svg>`
}

function iconSend() {
  return `<svg width="13" height="13" viewBox="0 0 24 24" fill="none"
    stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
    <path d="m22 2-7 20-4-9-9-4 20-7z"/>
    <path d="M22 2 11 13"/>
  </svg>`
}

// ── Utilitários ───────────────────────────────────────────

function sleep(ms) {
  return new Promise(r => setTimeout(r, ms))
}

// Converte hex para rgba com opacidade (para as chips de badge)
function hexAlpha(hex, alpha) {
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  return `rgba(${r},${g},${b},${alpha})`
}
