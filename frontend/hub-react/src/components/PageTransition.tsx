import { useState, useEffect, useRef } from 'react'

interface Props {
  id: string
  children: React.ReactNode
  className?: string
}

export default function PageTransition({ id, children, className = '' }: Props) {
  const [phase, setPhase]       = useState<'enter' | 'exit' | 'idle'>('enter')
  const [displayed, setDisplayed] = useState(id)
  const [content, setContent]   = useState(children)
  const prevId                  = useRef(id)
  const timer                   = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (id === prevId.current) return
    prevId.current = id

    if (timer.current) clearTimeout(timer.current)

    // fase de saída
    setPhase('exit')

    // após animação de saída (220ms), troca o conteúdo e entra
    timer.current = setTimeout(() => {
      setContent(children)
      setDisplayed(id)
      setPhase('enter')

      // volta para idle para não re-animar se o mesmo id for recebido novamente
      timer.current = setTimeout(() => setPhase('idle'), 350)
    }, 200)

    return () => { if (timer.current) clearTimeout(timer.current) }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  // atualiza conteúdo quando está idle (sem trocar de página)
  useEffect(() => {
    if (phase === 'idle' || phase === 'enter') {
      setContent(children)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [children])

  const cls =
    phase === 'enter' ? 'page-enter' :
    phase === 'exit'  ? 'page-exit'  : ''

  return (
    <div key={displayed} className={`${cls} ${className} flex flex-col h-full overflow-hidden`}>
      {content}
    </div>
  )
}
