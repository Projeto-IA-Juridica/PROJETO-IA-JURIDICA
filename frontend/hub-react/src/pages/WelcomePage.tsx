import { useState, useEffect, useRef } from 'react'

interface Props {
  onStart: () => void
}

/* ── Grade de perspectiva 3D interativa ─────────────────────────────────── */
function PerspectiveGrid() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const targetVP  = useRef({ x: 0.5, y: 0.42 })
  const currentVP = useRef({ x: 0.5, y: 0.42 })
  const rafRef    = useRef(0)

  useEffect(() => {
    const canvas = canvasRef.current!
    const ctx    = canvas.getContext('2d')!

    const resize = () => {
      canvas.width  = canvas.offsetWidth
      canvas.height = canvas.offsetHeight
    }

    const onMove = (e: MouseEvent) => {
      const r = canvas.getBoundingClientRect()
      targetVP.current = {
        x: 0.5  + (e.clientX / r.width  - 0.5) * 0.14,
        y: 0.42 + (e.clientY / r.height - 0.5) * 0.09,
      }
    }

    const draw = (ts: number) => {
      const W = canvas.width
      const H = canvas.height
      const t = ts / 1000

      ctx.clearRect(0, 0, W, H)

      /* Lerp suave do ponto de fuga — peso baixo = sensação de câmera 3D */
      currentVP.current.x += (targetVP.current.x - currentVP.current.x) * 0.028
      currentVP.current.y += (targetVP.current.y - currentVP.current.y) * 0.028

      const vpx = currentVP.current.x * W
      const vpy = currentVP.current.y * H

      ctx.lineCap = 'round'

      /* ── Linhas radiais (convergindo ao VP) ── */
      const RADIAL = 16
      const extraW = W * 0.25  // extende um pouco além das bordas

      for (let i = 0; i <= RADIAL; i++) {
        // Pontos igualmente espaçados na borda inferior (+ margem lateral)
        const x = -extraW + (i / RADIAL) * (W + extraW * 2)
        const distFromCenter = Math.abs(x - vpx) / (W * 0.6)
        const alpha = Math.max(0.04, 0.18 - distFromCenter * 0.10)

        ctx.strokeStyle = `rgba(18,72,210,${alpha})`
        ctx.lineWidth   = 0.65
        ctx.beginPath()
        ctx.moveTo(vpx, vpy)
        ctx.lineTo(x, H + 4)
        ctx.stroke()
      }

      /* ── Linhas horizontais em perspectiva (chão) ── */
      const HORIZ   = 10
      const advance = (t * 0.055) % 1.0  // avança lentamente em loop

      for (let i = 0; i < HORIZ; i++) {
        const rawT   = (i / HORIZ + advance) % 1.0
        const perspT = rawT * rawT * rawT  // cúbico = perspectiva mais realista

        const y = vpy + perspT * (H - vpy + 8)
        if (y > H + 4 || y < vpy - 2) continue

        const alpha = perspT * 0.28
        const lw    = 0.35 + perspT * 0.9

        ctx.strokeStyle = `rgba(18,72,210,${alpha})`
        ctx.lineWidth   = lw
        ctx.beginPath()
        ctx.moveTo(0, y)
        ctx.lineTo(W, y)
        ctx.stroke()
      }

      /* ── Linhas horizontais teto (espelho acima do VP) ── */
      for (let i = 0; i < Math.floor(HORIZ * 0.6); i++) {
        const rawT   = (i / (HORIZ * 0.6) + advance * 0.7) % 1.0
        const perspT = rawT * rawT

        const y = vpy - perspT * vpy * 1.1
        if (y < -4 || y > vpy + 2) continue

        const alpha = perspT * 0.14
        const lw    = 0.3 + perspT * 0.5

        ctx.strokeStyle = `rgba(18,72,210,${alpha})`
        ctx.lineWidth   = lw
        ctx.beginPath()
        ctx.moveTo(0, y)
        ctx.lineTo(W, y)
        ctx.stroke()
      }

      /* ── Halo no ponto de fuga ── */
      const halo = ctx.createRadialGradient(vpx, vpy, 0, vpx, vpy, 55)
      halo.addColorStop(0,   `rgba(18,72,210,${0.12 + Math.sin(t * 0.9) * 0.03})`)
      halo.addColorStop(0.5, 'rgba(18,72,210,0.04)')
      halo.addColorStop(1,   'rgba(18,72,210,0.00)')
      ctx.fillStyle = halo
      ctx.beginPath()
      ctx.arc(vpx, vpy, 55, 0, Math.PI * 2)
      ctx.fill()

      /* ── Elipse de horizonte (profundidade extra) ── */
      ctx.strokeStyle = `rgba(18,72,210,${0.07 + Math.sin(t * 0.6) * 0.02})`
      ctx.lineWidth   = 0.8
      ctx.beginPath()
      ctx.ellipse(vpx, vpy, W * 0.32, H * 0.06, 0, 0, Math.PI * 2)
      ctx.stroke()

      rafRef.current = requestAnimationFrame(draw)
    }

    window.addEventListener('mousemove', onMove)
    const ro = new ResizeObserver(resize)
    ro.observe(canvas)
    resize()
    rafRef.current = requestAnimationFrame(draw)

    return () => {
      window.removeEventListener('mousemove', onMove)
      ro.disconnect()
      cancelAnimationFrame(rafRef.current)
    }
  }, [])

  return (
    <canvas
      ref={canvasRef}
      className="absolute inset-0 w-full h-full"
      style={{ zIndex: 1, pointerEvents: 'none' }}
    />
  )
}

/* ── Página welcome ───────────────────────────────────────────────────────── */
export default function WelcomePage({ onStart }: Props) {
  const [btnHovered, setBtnHovered] = useState(false)

  return (
    <div
      className="relative w-full h-screen overflow-hidden select-none"
      style={{ background: '#EAF2FA' }}
    >
      {/* Grade 3D de perspectiva */}
      <PerspectiveGrid />

      {/* Conteúdo centrado */}
      <div
        className="relative flex flex-col items-center justify-center h-full px-6 text-center"
        style={{ zIndex: 10 }}
      >
        {/* Logo mark */}
        <div className="mb-2">
          <img
            src="/logo.png"
            alt="amicus"
            style={{ width: '160px', height: 'auto', display: 'block' }}
          />
        </div>

        {/* Wordmark */}
        <h1
          className="font-black"
          style={{
            fontSize: 'clamp(3.8rem, 11vw, 7.5rem)',
            letterSpacing: '-0.05em',
            lineHeight: 1,
            background: 'linear-gradient(160deg, #0C1E30 0%, #1248BE 60%, #4A8ED4 100%)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            backgroundClip: 'text',
          }}
        >
          amicus
        </h1>

        {/* Tagline */}
        <p
          className="mt-4 text-sm font-medium max-w-[22rem] leading-relaxed"
          style={{ color: 'rgba(12,30,48,0.40)' }}
        >
          Otimizando seu escritório de maneira inteligente
        </p>

        {/* Botão Começar */}
        <button
          onClick={onStart}
          onMouseEnter={() => setBtnHovered(true)}
          onMouseLeave={() => setBtnHovered(false)}
          style={{
            marginTop: '2.5rem',
            padding: '0.7rem 2.2rem',
            borderRadius: '0.9rem',
            fontSize: '0.8rem',
            fontWeight: 700,
            letterSpacing: '0.05em',
            textTransform: 'uppercase',
            background: btnHovered ? 'rgba(18,72,210,0.90)' : 'rgba(255,255,255,0.60)',
            border: btnHovered
              ? '1px solid rgba(18,72,210,0.80)'
              : '1px solid rgba(18,72,210,0.18)',
            color: btnHovered ? '#ffffff' : 'rgba(12,30,48,0.50)',
            backdropFilter: 'blur(10px)',
            boxShadow: btnHovered
              ? '0 4px 24px rgba(18,72,210,0.30)'
              : '0 1px 6px rgba(12,30,48,0.06)',
            transform: btnHovered ? 'translateY(-1px)' : 'translateY(0)',
            transition: 'all 0.20s ease',
            cursor: 'pointer',
          }}
        >
          Começar
        </button>

        {/* Linha divisória */}
        <div
          className="flex items-center gap-3"
          style={{ marginTop: '3.5rem', opacity: 0.18 }}
        >
          <div style={{ width: '2rem', height: '1px', background: '#1248BE' }} />
          <span style={{
            fontSize: '0.58rem',
            fontWeight: 700,
            textTransform: 'uppercase',
            color: '#1248BE',
            letterSpacing: '0.25em',
          }}>
            Hub do Advogado
          </span>
          <div style={{ width: '2rem', height: '1px', background: '#1248BE' }} />
        </div>
      </div>
    </div>
  )
}
