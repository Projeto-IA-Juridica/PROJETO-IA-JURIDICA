import { useState, useEffect } from 'react'

const CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789@#$%&'

interface Props {
  text: string
  encryptedClassName?: string
  revealedClassName?:  string
  revealDelayMs?:      number
  startDelay?:         number
  className?:          string
}

export function EncryptedText({
  text,
  encryptedClassName = '',
  revealedClassName  = '',
  revealDelayMs      = 60,
  startDelay         = 500,
  className          = '',
}: Props) {
  const [revealed,  setRevealed]  = useState(0)
  const [scrambled, setScrambled] = useState<string[]>(() =>
    text.split('').map(() => CHARS[Math.floor(Math.random() * CHARS.length)]),
  )

  /* Scramble loop — cycling unrevealed chars */
  useEffect(() => {
    const id = setInterval(() => {
      setScrambled(prev =>
        prev.map((_, i) =>
          i < revealed
            ? text[i]
            : CHARS[Math.floor(Math.random() * CHARS.length)],
        ),
      )
    }, 45)
    return () => clearInterval(id)
  }, [revealed, text])

  /* Reveal one char at a time */
  useEffect(() => {
    if (revealed >= text.length) return
    const delay = revealed === 0 ? startDelay : revealDelayMs
    const id = setTimeout(() => setRevealed(r => r + 1), delay)
    return () => clearTimeout(id)
  }, [revealed, text.length, revealDelayMs, startDelay])

  return (
    <span className={className}>
      {text.split('').map((char, i) =>
        char === ' ' ? (
          <span key={i}>&nbsp;</span>
        ) : (
          <span key={i} className={i < revealed ? revealedClassName : encryptedClassName}>
            {i < revealed ? char : (scrambled[i] ?? char)}
          </span>
        ),
      )}
    </span>
  )
}
