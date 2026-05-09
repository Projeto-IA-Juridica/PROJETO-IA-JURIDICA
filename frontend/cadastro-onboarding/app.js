/* ── Estado global ───────────────────────────────────────────── */
var state = {
  step: 1,
  s1: { email:"", pass:"", confirm:"" },
  s2: { nome:"", cnpj:"", oab:"", responsavel:"", advogados:"1", areas:[] },
  s3: { inicio:"08:00", fim:"18:00", dias:["Seg","Ter","Qua","Qui","Sex"] },
  s4: { assistente:"", tom:"" },
  aceite: false,
};

var AREAS  = ["Cível","Trabalhista","Família","Previdenciário","Criminal","Tributário","Empresarial","Digital","Consumidor","Imobiliário"];
var TONS   = ["Formal e técnico","Formal e acessível","Próximo e cordial","Neutro e objetivo"];
var DAYS   = ["Seg","Ter","Qua","Qui","Sex","Sáb","Dom"];
var LABELS = ["Acesso","Escritório","WhatsApp","Persona","OAB","Ativação"];

var TITLES = [
  { h:"Crie seu acesso",           p:"Defina o e-mail e a senha para acessar a plataforma amicus." },
  { h:"Configure seu escritório",  p:"Em poucos minutos sua IA estará pronta para atender clientes no WhatsApp 24h." },
  { h:"Conecte seu WhatsApp",      p:"Leia o QR Code no WhatsApp do escritório para ativar o canal de atendimento." },
  { h:"Configure a persona da IA", p:"Defina como sua assistente virtual vai se apresentar para os clientes." },
  { h:"Conformidade OAB",          p:"Aceite os termos exigidos pelo Provimento 205/2021 para uso ético da IA." },
  { h:"Ativar o escritório",       p:"Revise os dados e ative sua conta para começar a atender." },
];

/* ── Logo amicus ─────────────────────────────────────────────── */
(function() {
  var wrap = document.getElementById("logo-nav");
  "amicus".split("").forEach(function(l) {
    var span = document.createElement("span");
    span.className = "am-letter";
    span.textContent = l;
    span.addEventListener("mouseenter", function() { span.style.color="#3A7AB8"; span.style.transform="translateY(-2px)"; });
    span.addEventListener("mouseleave", function() { span.style.color="#0C1E30"; span.style.transform="translateY(0)"; });
    wrap.appendChild(span);
  });
})();

/* ── Força da senha ──────────────────────────────────────────── */
function getStrength(pass) {
  if (!pass) return { score:0, label:"", color:"transparent" };
  var score = 0;
  if (pass.length >= 8)            score++;
  if (/[A-Z]/.test(pass))         score++;
  if (/[0-9]/.test(pass))         score++;
  if (/[^A-Za-z0-9]/.test(pass))  score++;
  var map = [
    { label:"",         color:"transparent" },
    { label:"Fraca",    color:"#D63B3B" },
    { label:"Razoável", color:"#D4900A" },
    { label:"Boa",      color:"#3A7AB8" },
    { label:"Forte",    color:"#2E9E6B" },
  ];
  return Object.assign({ score:score }, map[score]);
}

/* ── SVG ícones ──────────────────────────────────────────────── */
var SVG_CHECK = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 12 9 17 20 7"/></svg>';
var SVG_CLOCK = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#3A7AB8" stroke-width="1.8" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>';

/* ── Render step indicator ───────────────────────────────────── */
function renderIndicator() {
  var html = "";
  LABELS.forEach(function(label, i) {
    var n      = i + 1;
    var done   = n < state.step;
    var active = n === state.step;
    if (i > 0) {
      html += '<div class="si-line' + (done||active?" done":"") + '"></div>';
    }
    html += '<div class="si-wrap">';
    html += '<div class="si-circle' + (done?" done":active?" active":"") + '">';
    if (done) html += SVG_CHECK;
    else      html += n;
    html += '</div>';
    html += '<span class="si-label' + (done||active?" active":"") + '">' + label + '</span>';
    html += '</div>';
  });
  document.getElementById("step-indicator").innerHTML = html;
  document.getElementById("step-num").textContent = state.step;
  document.getElementById("progress-bar").style.width = (((state.step-1)/5)*100) + "%";
  document.getElementById("step-title").textContent = TITLES[state.step-1].h;
  document.getElementById("step-sub").textContent   = TITLES[state.step-1].p;
  var btnNext = document.getElementById("btn-next");
  var btnPrev = document.getElementById("btn-prev");
  btnNext.textContent = state.step===6 ? "Ativar escritório →" : state.step===5 ? "Aceitar e continuar →" : "Próximo →";
  btnPrev.classList.toggle("hidden", state.step === 1);
}

/* ── Validação ───────────────────────────────────────────────── */
function validate() {
  var e = {};
  if (state.step === 1) {
    if (!state.s1.email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(state.s1.email))
      e.email = "E-mail inválido.";
    if (!state.s1.pass || getStrength(state.s1.pass).score < 2)
      e.pass = "Senha muito fraca. Use letras maiúsculas, números e símbolos.";
    if (!state.s1.confirm)
      e.confirm = "Confirme sua senha.";
    else if (state.s1.confirm !== state.s1.pass)
      e.confirm = "As senhas não coincidem.";
  }
  if (state.step === 2) {
    if (!state.s2.nome.trim())        e.nome        = "Nome do escritório obrigatório.";
    if (!state.s2.oab.trim())         e.oab         = "OAB obrigatória.";
    if (!state.s2.responsavel.trim()) e.responsavel = "Nome do responsável obrigatório.";
  }
  if (state.step === 3) {
    if (!state.s3.dias || state.s3.dias.length === 0)
      e.dias = "Selecione ao menos um dia de atendimento.";
  }
  if (state.step === 4) {
    if (!state.s4.assistente.trim()) e.assistente = "Dê um nome para sua assistente.";
  }
  if (state.step === 5) {
    if (!state.aceite) e.aceite = "Você deve aceitar os termos para continuar.";
  }
  return e;
}

/* ── Next / Prev ─────────────────────────────────────────────── */
function nextStep() {
  var errs = validate();

  // Limpa erros anteriores
  document.querySelectorAll(".field-err-inline").forEach(function(el){ el.remove(); });
  document.getElementById("form-error").classList.add("hidden");

  if (Object.keys(errs).length > 0) {
    // Mostra erro acima do campo específico
    var fieldMap = {
      email:       "f-email",
      pass:        "f-pass",
      confirm:     "f-confirm",
      nome:        "f-nome",
      oab:         "f-oab",
      responsavel: "f-resp",
      dias:        "days-pills",
      assistente:  "f-assistente",
      aceite:      "aceite-wrap",
    };
    var shown = false;
    Object.keys(errs).forEach(function(key) {
      var elId = fieldMap[key];
      var el   = elId ? document.getElementById(elId) : null;
      if (el) {
        var errEl = document.createElement("p");
        errEl.className = "field-err field-err-inline";
        errEl.style.marginBottom = "6px";
        errEl.textContent = errs[key];
        el.parentNode.insertBefore(errEl, el);
        if (!shown) { el.scrollIntoView({ behavior:"smooth", block:"center" }); shown = true; }
      }
    });
    return;
  }

  /* ── Fetches comentados — descomentar quando backend estiver pronto ──

  if (state.step === 1) {
    // await fetch('/auth/register', {
    //   method: 'POST', headers: {'Content-Type':'application/json'},
    //   body: JSON.stringify({ email: state.s1.email, password: state.s1.pass })
    // }).then(r => r.json()).then(d => localStorage.setItem('amicus_token', d.token));
  }
  if (state.step === 2) {
    // const token = localStorage.getItem('amicus_token');
    // await fetch('/escritorios', {
    //   method: 'POST', headers: {'Content-Type':'application/json','Authorization':'Bearer '+token},
    //   body: JSON.stringify(state.s2)
    // });
  }
  if (state.step === 3) {
    // const token = localStorage.getItem('amicus_token');
    // await fetch('/whatsapp/janela', {
    //   method: 'POST', headers: {'Content-Type':'application/json','Authorization':'Bearer '+token},
    //   body: JSON.stringify({ inicio: state.s3.inicio, fim: state.s3.fim, dias: state.s3.dias })
    // });
  }
  if (state.step === 4) {
    // const token = localStorage.getItem('amicus_token');
    // await fetch('/escritorios/persona', {
    //   method: 'POST', headers: {'Content-Type':'application/json','Authorization':'Bearer '+token},
    //   body: JSON.stringify({ assistente: state.s4.assistente, tom: state.s4.tom })
    // });
  }
  if (state.step === 5) {
    // const token = localStorage.getItem('amicus_token');
    // await fetch('/escritorios/compliance', {
    //   method: 'POST', headers: {'Content-Type':'application/json','Authorization':'Bearer '+token},
    //   body: JSON.stringify({ aceite: true })
    // });
  }
  if (state.step === 6) {
    // const token = localStorage.getItem('amicus_token');
    // await fetch('/escritorios/ativar', {
    //   method: 'POST', headers: {'Authorization':'Bearer '+token}
    // }).then(r => r.json()).then(d => window.location.href = d.redirect || '/dashboard');
  }
  ── fim dos fetches ── */

  if (state.step < 6) {
    state.step++;
    render();
  } else {
    document.getElementById("wizard").classList.add("hidden");
    document.getElementById("done-screen").classList.remove("hidden");
  }
}

function prevStep() {
  if (state.step > 1) { state.step--; render(); }
  document.getElementById("form-error").classList.add("hidden");
}

/* ── ETAPA 1 ─────────────────────────────────────────────────── */
function renderStep1() {
  return '' +
  '<div class="field-group">' +
    '<label class="field-label">E-mail profissional <span class="req">*</span></label>' +
    '<input type="email" id="f-email" placeholder="voce@escritorio.com.br" value="'+esc(state.s1.email)+'"/>' +
  '</div>' +
  '<div class="field-group">' +
    '<label class="field-label">Senha <span class="req">*</span></label>' +
    '<div class="pass-wrap">' +
      '<input type="password" id="f-pass" placeholder="Mínimo 8 caracteres" value="'+esc(state.s1.pass)+'"/>' +
      '<button class="eye-btn" onclick="toggleEye(\'f-pass\',this)" type="button">'+eyeIcon(false)+'</button>' +
    '</div>' +
    '<div id="strength-bars" class="strength-bars">'+strengthBarsHtml(state.s1.pass)+'</div>' +
    '<span id="strength-label" class="strength-label" style="color:'+getStrength(state.s1.pass).color+'">'+getStrength(state.s1.pass).label+'</span>' +
  '</div>' +
  '<div class="field-group">' +
    '<label class="field-label">Confirmar senha <span class="req">*</span></label>' +
    '<div class="pass-wrap">' +
      '<input type="password" id="f-confirm" placeholder="Repita a senha" value="'+esc(state.s1.confirm)+'"/>' +
      '<button class="eye-btn" onclick="toggleEye(\'f-confirm\',this)" type="button">'+eyeIcon(false)+'</button>' +
    '</div>' +
    (state.s1.confirm && state.s1.confirm===state.s1.pass ? '<p class="field-ok">Senhas coincidem ✓</p>' : '') +
    (state.s1.confirm && state.s1.confirm!==state.s1.pass ? '<p class="field-err">As senhas não coincidem.</p>' : '') +
  '</div>' +
  '<div class="info-box">Seus dados são protegidos por <strong>AES-256</strong> e nunca compartilhados com terceiros.</div>';
}

/* ── ETAPA 2 ─────────────────────────────────────────────────── */
function renderStep2() {
  var areasHtml = AREAS.map(function(a) {
    return '<button type="button" class="pill'+(state.s2.areas.includes(a)?" selected":"") +'" onclick="toggleArea(\''+a+'\')">' + a + '</button>';
  }).join("");
  return '' +
  '<div class="field-group">' +
    '<label class="field-label">Nome do escritório <span class="req">*</span></label>' +
    '<input type="text" id="f-nome" placeholder="Silva & Associados Advogados" value="'+esc(state.s2.nome)+'"/>' +
  '</div>' +
  '<div class="field-row">' +
    '<div class="field-group"><label class="field-label">CNPJ</label><input type="text" id="f-cnpj" placeholder="00.000.000/0001-81" value="'+esc(state.s2.cnpj)+'"/></div>' +
    '<div class="field-group"><label class="field-label">OAB do responsável <span class="req">*</span></label><input type="text" id="f-oab" placeholder="SP 123.456" value="'+esc(state.s2.oab)+'"/></div>' +
  '</div>' +
  '<div class="field-row">' +
    '<div class="field-group"><label class="field-label">Nome do responsável <span class="req">*</span></label><input type="text" id="f-resp" placeholder="Dr. João Silva" value="'+esc(state.s2.responsavel)+'"/></div>' +
    '<div class="field-group"><label class="field-label">Nº de advogados</label>' +
      '<select id="f-adv">' + ["1","2–5","6–15","15–50","50+"].map(function(o){ return '<option'+(state.s2.advogados===o?" selected":"")+'>'+o+'</option>'; }).join("") + '</select>' +
    '</div>' +
  '</div>' +
  '<div class="field-group"><label class="field-label">Áreas de atuação</label><div class="pills" id="areas-pills">'+areasHtml+'</div></div>' +
  '<div class="info-box">Dados protegidos por <strong>AES-256</strong>. Nunca compartilhamos com terceiros. Conforme a Lei 13.709/2018.</div>';
}

/* ── ETAPA 3 ─────────────────────────────────────────────────── */
function renderStep3() {
  var daysHtml = DAYS.map(function(d) {
    return '<button type="button" class="pill'+(state.s3.dias.includes(d)?" selected":"")+'" onclick="toggleDay(\''+d+'\')" style="width:46px;text-align:center">'+d+'</button>';
  }).join("");
  var diasOrdenados = DAYS.filter(function(d){ return state.s3.dias.includes(d); }).join(", ");
  var hh = state.s3.inicio.split(":")[0], mm = state.s3.inicio.split(":")[1];
  var hh2= state.s3.fim.split(":")[0],   mm2= state.s3.fim.split(":")[1];
  var hOpts = Array.from({length:24},function(_,i){var v=String(i).padStart(2,"0"); return '<option'+(v===hh?" selected":"")+' value="'+v+'">  '+v+'h</option>';}).join("");
  var mOpts = ["00","15","30","45"].map(function(v){ return '<option'+(v===mm?" selected":"")+' value="'+v+'">  '+v+'min</option>';}).join("");
  var hOpts2= Array.from({length:24},function(_,i){var v=String(i).padStart(2,"0"); return '<option'+(v===hh2?" selected":"")+' value="'+v+'">  '+v+'h</option>';}).join("");
  var mOpts2= ["00","15","30","45"].map(function(v){ return '<option'+(v===mm2?" selected":"")+' value="'+v+'">  '+v+'min</option>';}).join("");

  return '' +
  '<div class="qr-center">' +
    '<div class="qr-box">' +
      '<svg width="130" height="130" viewBox="0 0 130 130">' +
        '<rect x="0" y="0" width="40" height="40" rx="4" fill="#3A7AB8" opacity="0.8"/><rect x="8" y="8" width="24" height="24" rx="2" fill="white"/><rect x="12" y="12" width="16" height="16" rx="1" fill="#3A7AB8"/>' +
        '<rect x="90" y="0" width="40" height="40" rx="4" fill="#3A7AB8" opacity="0.8"/><rect x="98" y="8" width="24" height="24" rx="2" fill="white"/><rect x="102" y="12" width="16" height="16" rx="1" fill="#3A7AB8"/>' +
        '<rect x="0" y="90" width="40" height="40" rx="4" fill="#3A7AB8" opacity="0.8"/><rect x="8" y="98" width="24" height="24" rx="2" fill="white"/><rect x="12" y="102" width="16" height="16" rx="1" fill="#3A7AB8"/>' +
        '<rect x="50" y="10" width="8" height="8" rx="1" fill="#3A7AB8" opacity="0.5"/><rect x="62" y="10" width="8" height="8" rx="1" fill="#3A7AB8" opacity="0.5"/>' +
        '<rect x="10" y="50" width="8" height="8" rx="1" fill="#3A7AB8" opacity="0.5"/><rect x="10" y="62" width="8" height="8" rx="1" fill="#3A7AB8" opacity="0.5"/>' +
        '<rect x="50" y="50" width="30" height="30" rx="4" fill="#3A7AB8" opacity="0.12"/><rect x="56" y="56" width="18" height="18" rx="2" fill="#3A7AB8" opacity="0.45"/>' +
      '</svg>' +
    '</div>' +
    '<p class="qr-hint">WhatsApp → Dispositivos vinculados → Vincular dispositivo</p>' +
    '<div class="qr-status"><div class="qr-dot"></div><span>Aguardando conexão…</span></div>' +
  '</div>' +
  '<div style="height:1px;background:#D4E6F4;margin:4px 0 22px"></div>' +
  '<div style="font-size:13px;font-weight:700;color:#0C1E30;margin-bottom:4px">Janela de envio de mensagens</div>' +
  '<p style="font-size:13px;color:#6A849C;line-height:1.6;margin-bottom:18px">Define quando a IA pode enviar mensagens aos clientes. Fora desse horário as mensagens ficam em fila — ninguém receberá mensagens fora do horário configurado.</p>' +
  '<div class="field-group"><label class="field-label">Dias de atendimento</label><div class="pills" id="days-pills">'+daysHtml+'</div></div>' +
  '<div class="field-row" style="margin-bottom:16px">' +
    '<div class="time-picker-wrap"><div class="time-picker-label">Início</div><div class="time-picker-box">'+SVG_CLOCK+'<select id="tp-h1" onchange="updateTime(\'inicio\')">'+hOpts+'</select><span class="time-sep">:</span><select id="tp-m1" onchange="updateTime(\'inicio\')">'+mOpts+'</select></div></div>' +
    '<div class="time-picker-wrap"><div class="time-picker-label">Fim</div><div class="time-picker-box">'+SVG_CLOCK+'<select id="tp-h2" onchange="updateTime(\'fim\')">'+hOpts2+'</select><span class="time-sep">:</span><select id="tp-m2" onchange="updateTime(\'fim\')">'+mOpts2+'</select></div></div>' +
  '</div>' +
  '<div class="horario-preview">'+SVG_CLOCK+'<span id="horario-txt">A IA enviará mensagens de <strong>'+state.s3.inicio+'</strong> às <strong>'+state.s3.fim+'</strong> nos dias: <strong>'+diasOrdenados+'</strong>.</span></div>';
}

/* ── ETAPA 4 ─────────────────────────────────────────────────── */
function renderStep4() {
  var nome    = state.s4.assistente || "Sofia";
  var preview = "Olá! Sou " + nome + ", assistente virtual do escritório. Em que posso ajudar?";
  var tonsHtml = TONS.map(function(t) {
    return '<button type="button" class="ton-btn'+(state.s4.tom===t?" selected":"")+'" onclick="selectTon(\''+t+'\')">' + t + '</button>';
  }).join("");
  return '' +
  '<div class="field-group">' +
    '<label class="field-label">Nome da assistente <span class="req">*</span></label>' +
    '<input type="text" id="f-assistente" placeholder="Ex: Sofia, Laura, Rafael, Bruno…" value="'+esc(state.s4.assistente)+'"/>' +
  '</div>' +
  '<div class="field-group"><label class="field-label">Tom de comunicação</label><div class="ton-grid">'+tonsHtml+'</div></div>' +
  '<div class="wp-preview">' +
    '<div class="wp-preview-label">Pré-visualização</div>' +
    '<div class="wp-bubble"><p class="wp-bubble-text" id="wp-preview-text">'+esc(preview)+'</p><p class="wp-bubble-time">08:00 ✓✓</p></div>' +
  '</div>';
}

/* ── ETAPA 5 ─────────────────────────────────────────────────── */
function renderStep5() {
  var items = [
    ["A IA não emite pareceres jurídicos","Respostas informativas; estratégias são escaladas ao advogado."],
    ["Score de risco exclusivo para advogados","Probabilidade de resultado nunca é exibida ao cliente."],
    ["Prospecção B2C sem dados pessoais","Sem CPF, telefone ou e-mail via fontes processuais."],
    ["Disclaimer na 1ª interação","Configurado automaticamente em cada conversa iniciada."],
    ["Escalação automática fora de escopo","Pareceres e situações sensíveis vão diretamente ao advogado."],
  ];
  var itemsHtml = items.map(function(item) {
    return '<div class="check-item"><div class="check-icon">'+SVG_CHECK+'</div><div><div class="check-item-title">'+item[0]+'</div><div class="check-item-sub">'+item[1]+'</div></div></div>';
  }).join("");
  return itemsHtml +
  '<div class="aceite-wrap'+(state.aceite?" checked":"")+'" id="aceite-wrap">' +
    '<input type="checkbox" id="aceite-cb"'+(state.aceite?" checked":"") +' onchange="toggleAceite(this)"/>' +
    '<label for="aceite-cb">Declaro que li e concordo com os termos de uso ético da IA conforme o Provimento 205/2021 do Conselho Federal da OAB. <span style="color:#3A7AB8">*</span></label>' +
  '</div>' +
  (!state.aceite ? '<p class="aceite-warn">⚠ Obrigatório para avançar.</p>' : '');
}

/* ── ETAPA 6 ─────────────────────────────────────────────────── */
function renderStep6() {
  var dias = state.s3.dias || [];
  var diasOrdenados = DAYS.filter(function(d){ return dias.includes(d); }).join(", ");
  var rows = [
    { label:"E-mail",         value: state.s1.email || "—",                    filled: !!state.s1.email,       hi: false },
    { label:"Escritório",     value: state.s2.nome  || "—",                    filled: !!state.s2.nome,        hi: false },
    { label:"OAB",            value: state.s2.oab   || "—",                    filled: !!state.s2.oab,         hi: false },
    { label:"WhatsApp",       value: "Conectado ✓",                             filled: true,                   hi: true  },
    { label:"Janela de envio",value: state.s3.inicio+"–"+state.s3.fim+" · "+diasOrdenados, filled: true,       hi: false },
    { label:"Assistente",     value: state.s4.assistente ? state.s4.assistente+(state.s4.tom?" · "+state.s4.tom:"") : "—", filled: !!state.s4.assistente, hi: false },
    { label:"Conformidade",   value: state.aceite ? "OAB + LGPD ✓" : "Pendente", filled: state.aceite,         hi: state.aceite },
  ];
  var rowsHtml = rows.map(function(r) {
    var valClass = r.hi ? "summary-val green" : r.filled ? "summary-val" : "summary-val faint";
    return '<div class="summary-row'+(r.hi?" highlight":"")+'"><span class="summary-key">'+r.label+'</span><span class="'+valClass+'">'+esc(r.value)+'</span></div>';
  }).join("");
  return '<div class="summary-header">' +
    '<div class="summary-icon"><svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#2E9E6B" stroke-width="2" stroke-linecap="round"><polyline points="20 6 9 12 4 9"/></svg></div>' +
    '<div class="summary-title">Tudo pronto!</div>' +
    '<div class="summary-sub">Revise os dados e ative seu escritório.</div>' +
  '</div>' +
  rowsHtml +
  '<div class="info-box">Enviaremos uma mensagem de teste no WhatsApp configurado assim que você ativar.</div>';
}

/* ── Render principal ────────────────────────────────────────── */
function render() {
  renderIndicator();
  var card = document.getElementById("step-card");
  if      (state.step===1) card.innerHTML = renderStep1();
  else if (state.step===2) card.innerHTML = renderStep2();
  else if (state.step===3) card.innerHTML = renderStep3();
  else if (state.step===4) card.innerHTML = renderStep4();
  else if (state.step===5) card.innerHTML = renderStep5();
  else if (state.step===6) card.innerHTML = renderStep6();
  bindEvents();
}

/* ── Bind events após render ─────────────────────────────────── */
function bindEvents() {
  var map = {
    "f-email":     function(v){ state.s1.email = v; clearFieldErr("f-email"); },
    "f-pass":      function(v){ state.s1.pass = v; updateStrength(v); updateConfirmFeedback(); clearFieldErr("f-pass"); },
    "f-confirm":   function(v){ state.s1.confirm = v; updateConfirmFeedback(); clearFieldErr("f-confirm"); },
    "f-nome":      function(v){ state.s2.nome = v; clearFieldErr("f-nome"); },
    "f-cnpj":      function(v){ state.s2.cnpj = v; },
    "f-oab":       function(v){ state.s2.oab = v; clearFieldErr("f-oab"); },
    "f-resp":      function(v){ state.s2.responsavel = v; clearFieldErr("f-resp"); },
    "f-adv":       function(v){ state.s2.advogados = v; },
    "f-assistente":function(v){ state.s4.assistente = v; updateWpPreview(v); clearFieldErr("f-assistente"); },
  };
  Object.keys(map).forEach(function(id) {
    var el = document.getElementById(id);
    if (el) el.addEventListener("input", function(){ map[id](el.value); });
  });
}

function clearFieldErr(elId) {
  var el = document.getElementById(elId);
  if (!el) return;
  var prev = el.parentNode.querySelector(".field-err-inline");
  if (prev) prev.remove();
}

function updateStrength(pass) {
  var s = getStrength(pass);
  var bars = document.getElementById("strength-bars");
  var lbl  = document.getElementById("strength-label");
  if (!bars) return;
  bars.innerHTML = [1,2,3,4].map(function(n){
    return '<div class="strength-bar" style="background:'+(n<=s.score?s.color:"#D4E6F4")+'"></div>';
  }).join("");
  lbl.textContent = s.label;
  lbl.style.color = s.color;
}

function updateConfirmFeedback() {
  var wrap = document.querySelector(".pass-wrap + .pass-wrap") || document.querySelector("#f-confirm");
  if (!wrap) return;
  var parent = document.querySelector("#f-confirm") && document.querySelector("#f-confirm").parentNode.parentNode;
  if (!parent) return;
  var old = parent.querySelector(".field-ok,.field-err");
  if (old) old.remove();
  if (state.s1.confirm && state.s1.confirm === state.s1.pass) {
    var ok = document.createElement("p"); ok.className="field-ok"; ok.textContent="Senhas coincidem ✓"; parent.appendChild(ok);
  } else if (state.s1.confirm && state.s1.confirm !== state.s1.pass) {
    var er = document.createElement("p"); er.className="field-err"; er.textContent="As senhas não coincidem."; parent.appendChild(er);
  }
}

function updateWpPreview(nome) {
  var el = document.getElementById("wp-preview-text");
  if (el) el.textContent = "Olá! Sou " + (nome||"Sofia") + ", assistente virtual do escritório. Em que posso ajudar?";
}

function updateHorarioPreview() {
  var el = document.getElementById("horario-txt");
  if (!el) return;
  var diasOrdenados = DAYS.filter(function(d){ return state.s3.dias.includes(d); }).join(", ");
  el.innerHTML = 'A IA enviará mensagens de <strong>'+state.s3.inicio+'</strong> às <strong>'+state.s3.fim+'</strong> nos dias: <strong>'+diasOrdenados+'</strong>.';
}

/* ── Handlers ────────────────────────────────────────────────── */
function toggleArea(a) {
  var idx = state.s2.areas.indexOf(a);
  if (idx > -1) state.s2.areas.splice(idx,1); else state.s2.areas.push(a);
  var pills = document.getElementById("areas-pills");
  if (pills) pills.querySelectorAll(".pill").forEach(function(btn){
    btn.classList.toggle("selected", state.s2.areas.includes(btn.textContent));
  });
}

function toggleDay(d) {
  var idx = state.s3.dias.indexOf(d);
  if (idx > -1) state.s3.dias.splice(idx,1); else state.s3.dias.push(d);
  var pills = document.getElementById("days-pills");
  if (pills) pills.querySelectorAll(".pill").forEach(function(btn){
    btn.classList.toggle("selected", state.s3.dias.includes(btn.textContent.trim()));
  });
  updateHorarioPreview();
}

function updateTime(field) {
  if (field === "inicio") {
    var h = document.getElementById("tp-h1").value;
    var m = document.getElementById("tp-m1").value;
    state.s3.inicio = h+":"+m;
  } else {
    var h2= document.getElementById("tp-h2").value;
    var m2= document.getElementById("tp-m2").value;
    state.s3.fim = h2+":"+m2;
  }
  updateHorarioPreview();
}

function selectTon(t) {
  state.s4.tom = t;
  document.querySelectorAll(".ton-btn").forEach(function(btn){
    btn.classList.toggle("selected", btn.textContent.trim() === t);
  });
}

function toggleAceite(cb) {
  state.aceite = cb.checked;
  var wrap = document.getElementById("aceite-wrap");
  if (wrap) wrap.classList.toggle("checked", state.aceite);
  var warn = document.querySelector(".aceite-warn");
  if (warn) warn.style.display = state.aceite ? "none" : "block";
}

function toggleEye(inputId, btn) {
  var inp = document.getElementById(inputId);
  if (!inp) return;
  var showing = inp.type === "text";
  inp.type = showing ? "password" : "text";
  btn.innerHTML = eyeIcon(!showing);
}

/* ── Utilitários ─────────────────────────────────────────────── */
function esc(str) {
  return String(str||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

function eyeIcon(visible) {
  if (visible) return '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#B0C8DC" stroke-width="1.8" stroke-linecap="round"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/></svg>';
  return '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#B0C8DC" stroke-width="1.8" stroke-linecap="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></svg>';
}

function strengthBarsHtml(pass) {
  var s = getStrength(pass);
  return [1,2,3,4].map(function(n){
    return '<div class="strength-bar" style="background:'+(n<=s.score?s.color:"#D4E6F4")+'"></div>';
  }).join("");
}

/* ── Init ────────────────────────────────────────────────────── */
render();

/* ── Enter para avançar ──────────────────────────────────────── */
document.addEventListener("keydown", function(e) {
  if (e.key === "Enter") {
    var tag = document.activeElement && document.activeElement.tagName;
    // Não avança se o foco for num textarea
    if (tag === "TEXTAREA") return;
    nextStep();
  }
});