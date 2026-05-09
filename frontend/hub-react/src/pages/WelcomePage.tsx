import { useEffect, useRef } from 'react'
import { Sparkles } from 'lucide-react'
import { EncryptedText } from '../components/ui/EncryptedText'

interface Props {
  onStart: () => void
}

/* ── Corredor 3D interativo ──────────────────────────────────────────────── */
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
        x: 0.5  + (e.clientX / r.width  - 0.5) * 0.18,
        y: 0.42 + (e.clientY / r.height - 0.5) * 0.13,
      }
    }

    const draw = (ts: number) => {
      const W = canvas.width
      const H = canvas.height
      const t = ts / 1000

      ctx.clearRect(0, 0, W, H)

      currentVP.current.x += (targetVP.current.x - currentVP.current.x) * 0.026
      currentVP.current.y += (targetVP.current.y - currentVP.current.y) * 0.026

      const vpx = currentVP.current.x * W
      const vpy = currentVP.current.y * H

      ctx.lineCap = 'round'

      /* helper: linha com gradiente de opacidade ao longo do traçado */
      function gLine(
        x1: number, y1: number, x2: number, y2: number,
        c1: string, c2: string, lw: number,
      ) {
        const g = ctx.createLinearGradient(x1, y1, x2, y2)
        g.addColorStop(0, c1)
        g.addColorStop(1, c2)
        ctx.strokeStyle = g
        ctx.lineWidth   = lw
        ctx.beginPath()
        ctx.moveTo(x1, y1)
        ctx.lineTo(x2, y2)
        ctx.stroke()
      }

      /* ── Piso infinito: linhas convergindo ao VP + fileiras animadas ── */
      const COLS     = 16
      const ROWS     = 12
      const floorAdv = (t * 0.055) % (1 / ROWS)

      for (let i = 0; i <= COLS; i++) {
        const bx    = (i / COLS) * W
        const dist  = Math.abs(bx - vpx) / (W * 0.55)
        const alpha = Math.max(0.02, 0.18 - dist * 0.08)
        gLine(vpx, vpy, bx, H + 2, 'rgba(18,72,210,0)', `rgba(18,72,210,${alpha})`, 0.6)
      }

      for (let i = 0; i < ROWS; i++) {
        const rawT   = ((i / ROWS) + floorAdv) % 1.0
        const perspT = Math.pow(rawT, 2.4)
        const y      = vpy + perspT * (H - vpy + 4)
        if (y > H + 4 || y < vpy - 2) continue
        ctx.strokeStyle = `rgba(18,72,210,${perspT * 0.28})`
        ctx.lineWidth   = 0.3 + perspT * 0.9
        ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke()
      }

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
        <div className="mb-0">
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
            paddingRight: '0.1em',
            background: 'linear-gradient(160deg, #0C1E30 0%, #1248BE 60%, #4A8ED4 100%)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            backgroundClip: 'text',
          }}
        >
          amicus
        </h1>

        {/* Welcome encrypted */}
        <p className="mt-3 text-sm font-medium tracking-wide" style={{ color: 'rgba(12,30,48,0.38)' }}>
          Welcome to{' '}
          <span style={{ color: '#1248BE' }}>
            <EncryptedText
              text="amicus"
              encryptedClassName="font-mono opacity-40"
              revealedClassName="font-bold"
              revealDelayMs={80}
              startDelay={600}
            />
          </span>
        </p>

        {/* Tagline */}
        <p
          className="mt-2 text-xs font-medium max-w-[22rem] leading-relaxed"
          style={{ color: 'rgba(12,30,48,0.32)' }}
        >
          Otimizando seu escritório de maneira inteligente
        </p>

        {/* Botão Começar */}
        <button className="spkbtn" onClick={onStart} style={{ marginTop: '2.5rem' }}>
          <Sparkles size={16} className="spkbtn-sparkle" />
          <span className="spkbtn-text">Começar</span>
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
