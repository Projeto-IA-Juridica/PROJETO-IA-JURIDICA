/* ── Logo amicus ─────────────────────────────────────────────── */
(function () {
  var wrap    = document.getElementById("logo-nav");
  var TINTA   = "#0C1E30";
  var PRIMARY = "#3A7AB8";

  "amicus".split("").forEach(function (l) {
    var span = document.createElement("span");
    span.className   = "am-letter";
    span.textContent = l;
    span.addEventListener("mouseenter", function () {
      span.style.color     = PRIMARY;
      span.style.transform = "translateY(-2px)";
    });
    span.addEventListener("mouseleave", function () {
      span.style.color     = TINTA;
      span.style.transform = "translateY(0)";
    });
    wrap.appendChild(span);
  });
})();

/* ── Máscara telefone ────────────────────────────────────────── */
(function () {
  var tel = document.getElementById("f-tel");
  if (!tel) return;
  tel.addEventListener("input", function () {
    var v = tel.value.replace(/\D/g, "").slice(0, 11);
    if (v.length <= 10) {
      v = v.replace(/^(\d{2})(\d{4})(\d{0,4})/, "($1) $2-$3");
    } else {
      v = v.replace(/^(\d{2})(\d{5})(\d{0,4})/, "($1) $2-$3");
    }
    tel.value = v;
  });
})();

/* ── Envio WhatsApp ──────────────────────────────────────────── */
(function () {
  var WHATSAPP = (document.querySelector('meta[name="amicus:whatsapp"]') || {}).content || "5500000000000";

  var form    = document.getElementById("contact-form");
  var errorEl = document.getElementById("form-error");
  var success = document.getElementById("success-state");

  form.addEventListener("submit", function (e) {
    e.preventDefault();

    var nome    = document.getElementById("f-nome").value.trim();
    var email   = document.getElementById("f-email").value.trim();
    var tel     = document.getElementById("f-tel").value.trim();
    var empresa = document.getElementById("f-empresa").value.trim();
    var msg     = document.getElementById("f-msg").value.trim();

    if (!nome || !email || !tel || !empresa || !msg) {
      errorEl.style.display = "block";
      return;
    }
    errorEl.style.display = "none";

    var texto = [
      "Olá! Recebi um contato pelo site amicus:",
      "",
      "👤 Nome: "         + nome,
      "📧 E-mail: "       + email,
      "📱 Telefone: "     + tel,
      "🏛️ Escritório: "  + empresa,
      "",
      "💬 Mensagem:",
      msg,
    ].join("\n");

    window.open(
      "https://wa.me/" + WHATSAPP + "?text=" + encodeURIComponent(texto),
      "_blank"
    );

    form.style.display    = "none";
    success.style.display = "block";
  });
})();