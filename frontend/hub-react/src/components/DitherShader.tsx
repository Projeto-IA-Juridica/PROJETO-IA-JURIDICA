import { useEffect, useRef } from 'react'

/* ── Shaders ──────────────────────────────────────────────────────────────── */

const VERT = `
  attribute vec2 a_pos;
  varying vec2 v_uv;
  void main() {
    v_uv = a_pos * 0.5 + 0.5;
    gl_Position = vec4(a_pos, 0.0, 1.0);
  }
`

const FRAG = `
  precision mediump float;
  uniform sampler2D u_tex;
  uniform vec2 u_res;
  uniform float u_time;
  uniform vec3 u_dark;
  uniform vec3 u_light;
  uniform float u_grid;
  varying vec2 v_uv;

  float bayer(vec2 p) {
    vec2 q = floor(mod(p, 4.0));
    float x = q.x; float y = q.y; float t;
    if (y < 1.0) {
      if (x < 1.0) t = 0.0; else if (x < 2.0) t = 8.0;
      else if (x < 3.0) t = 2.0; else t = 10.0;
    } else if (y < 2.0) {
      if (x < 1.0) t = 12.0; else if (x < 2.0) t = 4.0;
      else if (x < 3.0) t = 14.0; else t = 6.0;
    } else if (y < 3.0) {
      if (x < 1.0) t = 3.0; else if (x < 2.0) t = 11.0;
      else if (x < 3.0) t = 1.0; else t = 9.0;
    } else {
      if (x < 1.0) t = 15.0; else if (x < 2.0) t = 7.0;
      else if (x < 3.0) t = 13.0; else t = 5.0;
    }
    return t / 16.0;
  }

  void main() {
    vec2 px  = floor(gl_FragCoord.xy / u_grid) * u_grid;
    vec2 uv  = vec2(px.x / u_res.x, 1.0 - px.y / u_res.y);
    vec4 c   = texture2D(u_tex, uv);
    float lum = dot(c.rgb, vec3(0.299, 0.587, 0.114));

    float wave = sin(u_time * 1.2 + gl_FragCoord.x * 0.04) * 0.018;
    float th   = bayer(gl_FragCoord.xy / u_grid);
    float d    = step(th, clamp(lum + wave, 0.0, 1.0));

    gl_FragColor = vec4(mix(u_dark, u_light, d), 1.0);
  }
`

/* ── Balança jurídica desenhada em canvas 2D ────────────────────────────── */

function drawScales(w: number, h: number): HTMLCanvasElement {
  const c = document.createElement('canvas')
  c.width = w; c.height = h
  const ctx = c.getContext('2d')!

  ctx.fillStyle = '#0C1E30'
  ctx.fillRect(0, 0, w, h)

  const lw = Math.max(2, w * 0.018)
  ctx.strokeStyle = '#ffffff'
  ctx.fillStyle   = '#ffffff'
  ctx.lineWidth   = lw
  ctx.lineCap     = 'round'
  ctx.lineJoin    = 'round'

  const cx      = w * 0.50
  const topY    = h * 0.10
  const baseY   = h * 0.88
  const beamY   = h * 0.28
  const leftX   = cx - w * 0.29
  const rightX  = cx + w * 0.29
  const panY    = h * 0.54
  const panR    = w * 0.145   // pan radius

  // ── Top knob ──
  ctx.beginPath()
  ctx.arc(cx, topY, lw * 2.2, 0, Math.PI * 2)
  ctx.fill()

  // ── Centre pole ──
  ctx.beginPath()
  ctx.moveTo(cx, topY + lw * 2.5)
  ctx.lineTo(cx, baseY - lw)
  ctx.stroke()

  // ── Base foot ──
  ctx.lineWidth = lw * 1.8
  ctx.beginPath()
  ctx.moveTo(cx - w * 0.17, baseY)
  ctx.lineTo(cx + w * 0.17, baseY)
  ctx.stroke()
  ctx.lineWidth = lw

  // ── Crossbeam ──
  ctx.beginPath()
  ctx.moveTo(leftX - panR, beamY)
  ctx.lineTo(rightX + panR, beamY)
  ctx.stroke()

  // ── Pivot circle at beam centre ──
  ctx.beginPath()
  ctx.arc(cx, beamY, lw * 1.6, 0, Math.PI * 2)
  ctx.fill()

  // Helper: draw one pan + strings
  function drawPan(px: number) {
    const sr = panR * 0.7          // horizontal string spread

    // Two strings angling inward to beam endpoint
    ctx.beginPath()
    ctx.moveTo(px, beamY)
    ctx.lineTo(px - sr, panY)
    ctx.moveTo(px, beamY)
    ctx.lineTo(px + sr, panY)
    ctx.stroke()

    // Rim line across top of pan
    ctx.beginPath()
    ctx.moveTo(px - sr, panY)
    ctx.lineTo(px + sr, panY)
    ctx.stroke()

    // Bowl arc (bottom half = clockwise 0 → π)
    ctx.beginPath()
    ctx.arc(px, panY, sr, 0, Math.PI, false)
    ctx.stroke()
  }

  drawPan(leftX)
  drawPan(rightX)

  return c
}

/* ── WebGL helpers ──────────────────────────────────────────────────────── */

function hex2rgb(hex: string): [number, number, number] {
  const n = parseInt(hex.replace('#', ''), 16)
  return [(n >> 16 & 255) / 255, (n >> 8 & 255) / 255, (n & 255) / 255]
}

function compile(gl: WebGLRenderingContext, type: number, src: string) {
  const s = gl.createShader(type)!
  gl.shaderSource(s, src)
  gl.compileShader(s)
  return s
}

/* ── Component ──────────────────────────────────────────────────────────── */

interface Props {
  darkColor?:  string   // hex — the "off" dither colour
  lightColor?: string   // hex — the "on"  dither colour
  gridSize?:   number   // pixel grid (2–8)
  animated?:   boolean
  className?:  string
}

export default function DitherShader({
  darkColor  = '#0C1E30',
  lightColor = '#EAF2FA',
  gridSize   = 4,
  animated   = true,
  className  = '',
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const rafRef    = useRef<number>(0)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const gl = canvas.getContext('webgl')
    if (!gl) return

    /* ── Compile program ── */
    const prog = gl.createProgram()!
    gl.attachShader(prog, compile(gl, gl.VERTEX_SHADER,   VERT))
    gl.attachShader(prog, compile(gl, gl.FRAGMENT_SHADER, FRAG))
    gl.linkProgram(prog)
    gl.useProgram(prog)

    /* ── Fullscreen quad ── */
    const buf = gl.createBuffer()
    gl.bindBuffer(gl.ARRAY_BUFFER, buf)
    gl.bufferData(gl.ARRAY_BUFFER,
      new Float32Array([-1,-1, 1,-1, -1,1, 1,1]), gl.STATIC_DRAW)
    const loc = gl.getAttribLocation(prog, 'a_pos')
    gl.enableVertexAttribArray(loc)
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0)

    /* ── Texture from scales canvas ── */
    const scalesCanvas = drawScales(512, 512)
    const tex = gl.createTexture()
    gl.bindTexture(gl.TEXTURE_2D, tex)
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, scalesCanvas)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR)

    /* ── Uniforms ── */
    const u = (n: string) => gl.getUniformLocation(prog, n)
    const darkRGB  = hex2rgb(darkColor)
    const lightRGB = hex2rgb(lightColor)

    /* ── Resize ── */
    const resize = () => {
      canvas.width  = canvas.offsetWidth
      canvas.height = canvas.offsetHeight
      gl.viewport(0, 0, canvas.width, canvas.height)
    }
    resize()
    const ro = new ResizeObserver(resize)
    ro.observe(canvas)

    /* ── Render loop ── */
    let start = performance.now()
    const render = () => {
      const t = animated ? (performance.now() - start) / 1000 : 0
      gl.uniform2f(u('u_res'),   canvas.width, canvas.height)
      gl.uniform1f(u('u_time'),  t)
      gl.uniform3fv(u('u_dark'), darkRGB)
      gl.uniform3fv(u('u_light'),lightRGB)
      gl.uniform1f(u('u_grid'),  gridSize)
      gl.uniform1i(u('u_tex'),   0)
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4)
      rafRef.current = requestAnimationFrame(render)
    }
    render()

    return () => {
      cancelAnimationFrame(rafRef.current)
      ro.disconnect()
      gl.deleteTexture(tex)
      gl.deleteBuffer(buf)
      gl.deleteProgram(prog)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [darkColor, lightColor, gridSize, animated])

  return <canvas ref={canvasRef} className={`w-full h-full ${className}`} />
}
