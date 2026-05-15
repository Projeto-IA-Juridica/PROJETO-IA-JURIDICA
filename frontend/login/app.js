/* ── Paleta ───────────────────────────────────────────────────── */
var BG      = "#F4F8FC";
var PRIMARIO= "#3A7AB8";
var TINTA   = "#0C1E30";

/* ── Logo amicus animado (navbar) ────────────────────────────── */
(function () {
  var wrap = document.getElementById("logo-nav");
  "amicus".split("").forEach(function (l, i) {
    var span = document.createElement("span");
    span.className   = "am-letter";
    span.textContent = l;
    span.addEventListener("mouseenter", function () {
      span.style.color     = PRIMARIO;
      span.style.transform = "translateY(-2px)";
    });
    span.addEventListener("mouseleave", function () {
      span.style.color     = TINTA;
      span.style.transform = "translateY(0)";
    });
    wrap.appendChild(span);
  });
})();

/* ── Toggle olho senha ───────────────────────────────────────── */
(function () {
  var btn     = document.getElementById("toggle-pass");
  var input   = document.getElementById("pass-input");
  var eyeOn   = document.getElementById("eye-icon");
  var eyeOff  = document.getElementById("eye-off-icon");
  var visible = false;

  btn.addEventListener("click", function () {
    visible = !visible;
    input.type     = visible ? "text"  : "password";
    eyeOn.style.display  = visible ? "none"  : "block";
    eyeOff.style.display = visible ? "block" : "none";
  });
})();

/* ── Foco nos inputs — muda cor do ícone ────────────────────── */
(function () {
  var fields = [
    { input: "email-input", icon: 0 },
    { input: "pass-input",  icon: 1 },
  ];
  var icons = document.querySelectorAll(".input-icon");

  fields.forEach(function (f, idx) {
    var el = document.getElementById(f.input);
    if (!el) return;
    el.addEventListener("focus", function () {
      if (icons[idx]) icons[idx].setAttribute("stroke", PRIMARIO);
    });
    el.addEventListener("blur", function () {
      if (icons[idx]) icons[idx].setAttribute("stroke", "#B0C8DC");
    });
  });
})();

/* ── Wave background ─────────────────────────────────────────── */
(function () {
  var cv = document.getElementById("wave-canvas");
  var cx = cv.getContext("2d");
  var t  = 0;
  var LINES = 60;
  var waves = [
    { A: 55, f: 0.0032, s: 0.012, p: 0.0 },
    { A: 35, f: 0.0058, s: 0.019, p: 1.4 },
    { A: 22, f: 0.0094, s: 0.027, p: 2.9 },
    { A: 14, f: 0.0150, s: 0.021, p: 0.8 },
  ];

  function lerp(a, b, n) { return Math.round(a + (b - a) * n); }

  function resize() {
    cv.width  = window.innerWidth;
    cv.height = window.innerHeight;
  }
  resize();
  window.addEventListener("resize", resize);

  function loop() {
    var W = cv.width, H = cv.height;
    cx.clearRect(0, 0, W, H);
    cx.fillStyle = BG;
    cx.fillRect(0, 0, W, H);

    for (var i = 0; i < LINES; i++) {
      var frac  = i / (LINES - 1);
      var baseY = frac * H;
      var mid   = Math.abs(frac - 0.5) * 2;
      var n2    = frac < 0.5 ? frac * 2 : (1 - frac) * 2;
      var r = lerp(234, 58, n2);
      var g = lerp(242, 122, n2);
      var b = lerp(250, 184, n2);

      cx.beginPath();
      cx.strokeStyle = "rgb(" + r + "," + g + "," + b + ")";
      cx.globalAlpha = 0.12 + (1 - mid) * 0.32;
      cx.lineWidth   = 0.4  + (1 - mid) * 0.9;

      for (var x = 0; x <= W; x += 3) {
        var dy = 0;
        waves.forEach(function (w) {
          dy += w.A * Math.sin(x * w.f + t * w.s + i * 0.20 + w.p);
        });
        var y = baseY + dy;
        x === 0 ? cx.moveTo(x, y) : cx.lineTo(x, y);
      }
      cx.stroke();
    }

    cx.globalAlpha = 1;
    t += 0.5;
    requestAnimationFrame(loop);
  }

  loop();
})();