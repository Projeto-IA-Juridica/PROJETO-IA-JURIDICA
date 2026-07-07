/**
 * Tempo real do Agendamento Inteligente via SSE (GET /agendamentos/stream).
 *
 * Cada transição de estado no backend publica um evento; aqui invalidamos as
 * queries e o react-query re-busca — o card de aprovação some em milissegundos
 * quando o advogado responde "1" no WhatsApp.
 *
 * Usa fetch + ReadableStream (não EventSource) para poder enviar o header
 * Authorization. O polling das páginas continua como fallback: com o stream
 * conectado elas reduzem a frequência (ver AgendamentoStreamContext).
 */
import { createContext, useContext, useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { getAccessToken } from '../api/auth'

export const AgendamentoStreamContext = createContext<boolean>(false)

/** true quando o stream SSE está conectado — usado para relaxar o polling */
export function useStreamConectado(): boolean {
  return useContext(AgendamentoStreamContext)
}

const QUERY_KEYS = ['agendamentos-pendentes', 'agendamentos-eventos', 'agendamentos-proximas']
const RECONNECT_BASE_MS = 4_000
const RECONNECT_MAX_MS = 30_000

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    const t = setTimeout(resolve, ms)
    signal?.addEventListener('abort', () => { clearTimeout(t); resolve() }, { once: true })
  })
}

/** Monta a conexão SSE (uma por app — usar apenas no Shell). */
export function useAgendamentoStream(enabled: boolean = true): boolean {
  const qc = useQueryClient()
  const [connected, setConnected] = useState(false)

  useEffect(() => {
    if (!enabled) return
    const ctrl = new AbortController()
    let stopped = false
    let tentativa = 0

    async function loop() {
      while (!stopped) {
        const token = getAccessToken()
        if (!token) {
          await sleep(RECONNECT_BASE_MS, ctrl.signal)
          continue
        }
        try {
          const resp = await fetch('/api/agendamentos/stream', {
            headers: { Authorization: `Bearer ${token}`, Accept: 'text/event-stream' },
            signal: ctrl.signal,
          })
          if (!resp.ok || !resp.body) throw new Error(`stream http ${resp.status}`)

          setConnected(true)
          tentativa = 0
          const reader = resp.body.getReader()
          const decoder = new TextDecoder()
          let buffer = ''

          for (;;) {
            const { done, value } = await reader.read()
            if (done) break
            buffer += decoder.decode(value, { stream: true })
            if (buffer.includes('event: agendamentos')) {
              buffer = ''
              QUERY_KEYS.forEach((k) => qc.invalidateQueries({ queryKey: [k] }))
            }
            // heartbeats (": ping") só limpam o buffer para não crescer
            if (buffer.length > 8_192) buffer = ''
          }
        } catch {
          // rede caiu / 401 / abort — reconecta com backoff abaixo
        } finally {
          setConnected(false)
        }
        if (stopped) break
        tentativa += 1
        const espera = Math.min(RECONNECT_BASE_MS * tentativa, RECONNECT_MAX_MS)
        await sleep(espera + Math.random() * 1_000, ctrl.signal)
      }
    }

    loop()
    return () => {
      stopped = true
      ctrl.abort()
      setConnected(false)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled])

  return connected
}
