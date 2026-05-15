import { useEffect, useRef } from 'react'

export interface WaveConfig {
  A: number; f: number; s: number; p: number
}

export function useWaveCanvas(waves: WaveConfig[], lines = 60) {
  const ref = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const cv = ref.current
    if (!cv) return
    const cx = cv.getContext('2d')!
    let t = 0, animId: number

    const resize = () => {
      cv.width  = window.innerWidth
      cv.height = window.innerHeight
    }
    resize()
    window.addEventListener('resize', resize)

    const loop = () => {
      const W = cv.width, H = cv.height
      cx.clearRect(0, 0, W, H)
      cx.fillStyle = '#F4F8FC'
      cx.fillRect(0, 0, W, H)

      for (let i = 0; i < lines; i++) {
        const frac  = i / (lines - 1)
        const baseY = frac * H
        const mid   = Math.abs(frac - 0.5) * 2
        const n2    = frac < 0.5 ? frac * 2 : (1 - frac) * 2
        const r = Math.round(234 + (58  - 234) * n2)
        const g = Math.round(242 + (122 - 242) * n2)
        const b = Math.round(250 + (184 - 250) * n2)

        cx.beginPath()
        cx.strokeStyle = `rgb(${r},${g},${b})`
        cx.globalAlpha = 0.12 + (1 - mid) * 0.32
        cx.lineWidth   = 0.4  + (1 - mid) * 0.9

        for (let x = 0; x <= W; x += 3) {
          let dy = 0
          waves.forEach(w => { dy += w.A * Math.sin(x * w.f + t * w.s + i * 0.20 + w.p) })
          x === 0 ? cx.moveTo(x, baseY + dy) : cx.lineTo(x, baseY + dy)
        }
        cx.stroke()
      }

      cx.globalAlpha = 1
      t += 0.5
      animId = requestAnimationFrame(loop)
    }
    loop()

    return () => {
      window.removeEventListener('resize', resize)
      cancelAnimationFrame(animId)
    }
  }, [])

  return ref
}
