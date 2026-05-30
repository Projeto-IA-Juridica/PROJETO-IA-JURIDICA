import { useCallback, useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { Send } from 'lucide-react'

interface Props {
  placeholders: string[]
  onChange?:    (e: React.ChangeEvent<HTMLInputElement>) => void
  onSubmit:     (value: string) => void
  disabled?:    boolean
  className?:   string
}

type Particle = {
  x: number; y: number
  r: number
  color: string
  vx: number; vy: number
}

export function PlaceholdersAndVanishInput({
  placeholders,
  onChange,
  onSubmit,
  disabled = false,
  className = '',
}: Props) {
  const [value, setValue]             = useState('')
  const [animating, setAnimating]     = useState(false)
  const [phIndex, setPhIndex]         = useState(0)
  const inputRef                      = useRef<HTMLInputElement>(null)
  const canvasRef                     = useRef<HTMLCanvasElement>(null)
  const particlesRef                  = useRef<Particle[]>([])
  const rafRef                        = useRef(0)

  /* ── Ciclar placeholders a cada 3s ── */
  useEffect(() => {
    const id = setInterval(
      () => setPhIndex((i) => (i + 1) % placeholders.length),
      3000,
    )
    return () => clearInterval(id)
  }, [placeholders.length])

  /* ── Rasteriza o texto no canvas para extrair pixels ── */
  const rasterize = useCallback(() => {
    const canvas = canvasRef.current
    const input  = inputRef.current
    if (!canvas || !input || !value) return

    const ctx = canvas.getContext('2d')!
    const W   = canvas.width
    const H   = canvas.height
    ctx.clearRect(0, 0, W, H)

    const style = getComputedStyle(input)
    ctx.font      = `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`
    ctx.fillStyle = style.color || '#0C1E30'
    ctx.fillText(value, 16, H * 0.68)

    const imgData = ctx.getImageData(0, 0, W, H).data
    const pixels: Particle[] = []

    for (let i = 0; i < imgData.length; i += 4) {
      if (imgData[i + 3] > 120) {
        const px = (i / 4) % W
        const py = Math.floor(i / 4 / W)
        pixels.push({
          x: px, y: py, r: 1.2,
          color: `rgba(${imgData[i]},${imgData[i+1]},${imgData[i+2]},${imgData[i+3]/255})`,
          vx: (Math.random() - 0.5) * 2.4,
          vy: -(Math.random() * 1.8 + 0.4),
        })
      }
    }
    particlesRef.current = pixels
  }, [value])

  /* ── Animação de vanish ── */
  function startVanish(submitted: string) {
    setAnimating(true)
    rasterize()

    const canvas   = canvasRef.current!
    const ctx      = canvas.getContext('2d')!
    const duration = 620
    const start    = performance.now()
    const parts    = [...particlesRef.current]

    const frame = (now: number) => {
      const t = Math.min((now - start) / duration, 1)
      ctx.clearRect(0, 0, canvas.width, canvas.height)

      parts.forEach((p) => {
        ctx.globalAlpha = 1 - t
        ctx.fillStyle   = p.color
        ctx.fillRect(
          p.x + p.vx * t * 28,
          p.y + p.vy * t * 22,
          p.r, p.r,
        )
      })
      ctx.globalAlpha = 1

      if (t < 1) {
        rafRef.current = requestAnimationFrame(frame)
      } else {
        ctx.clearRect(0, 0, canvas.width, canvas.height)
        setValue('')
        setAnimating(false)
        onSubmit(submitted)
      }
    }
    rafRef.current = requestAnimationFrame(frame)
  }

  useEffect(() => () => cancelAnimationFrame(rafRef.current), [])

  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const trimmed = value.trim()
    if (!trimmed || disabled || animating) return
    startVanish(trimmed)
  }

  return (
    <form
      onSubmit={handleSubmit}
      className={`relative flex items-center w-full ${className}`}
    >
      {/* Canvas overlay — visível só durante vanish */}
      <canvas
        ref={canvasRef}
        width={800}
        height={45}
        className="absolute inset-0 pointer-events-none rounded-xl"
        style={{ zIndex: 5, opacity: animating ? 1 : 0 }}
      />

      {/* Placeholder animado */}
      <div className="absolute left-4 right-12 top-1/2 -translate-y-1/2 overflow-hidden pointer-events-none" style={{ zIndex: 3 }}>
        <AnimatePresence mode="wait">
          {!value && !animating && (
            <motion.p
              key={phIndex}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.28 }}
              className="text-xs text-am-muted truncate select-none"
            >
              {placeholders[phIndex]}
            </motion.p>
          )}
        </AnimatePresence>
      </div>

      {/* Input */}
      <label htmlFor="hub-ia-input" className="sr-only">Mensagem para o assistente</label>
      <input
        id="hub-ia-input"
        ref={inputRef}
        value={animating ? '' : value}
        onChange={(e) => {
          if (animating) return
          setValue(e.target.value)
          onChange?.(e)
        }}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault()
            const trimmed = value.trim()
            if (trimmed && !disabled && !animating) startVanish(trimmed)
          }
        }}
        disabled={disabled || animating}
        autoComplete="off"
        className="w-full pl-4 pr-12 py-3 text-xs rounded-xl border border-am-border
          bg-am-bg text-am-ink outline-none transition-fast
          placeholder:text-transparent focus:border-am-blue
          disabled:opacity-60"
        style={{ position: 'relative', zIndex: 2, caretColor: animating ? 'transparent' : undefined }}
      />

      {/* Botão enviar */}
      <motion.button
        type="submit"
        aria-label="Enviar mensagem"
        disabled={!value.trim() || disabled || animating}
        className="absolute right-2 top-1/2 -translate-y-1/2 w-8 h-8 flex items-center
          justify-center rounded-lg text-white transition-fast
          disabled:opacity-35 disabled:cursor-not-allowed"
        style={{ background: 'var(--color-am-blue)', zIndex: 6 }}
        whileTap={{ scale: 0.88 }}
        animate={{ scale: value.trim() ? 1 : 0.90, opacity: value.trim() ? 1 : 0.5 }}
        transition={{ duration: 0.15 }}
      >
        <Send size={12} />
      </motion.button>
    </form>
  )
}
