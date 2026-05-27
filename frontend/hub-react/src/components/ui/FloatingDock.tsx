import { useRef, useState } from 'react'
import { motion, useMotionValue, useSpring, useTransform } from 'framer-motion'
import type { MotionValue } from 'framer-motion'

export interface DockItem {
  title:   string
  icon:    React.ReactNode
  id:      string
  active:  boolean
  onClick: () => void
}

/* ── Ícone individual com magnification ── */
function DockIcon({ item, mouseX }: { item: DockItem; mouseX: MotionValue<number> }) {
  const ref     = useRef<HTMLDivElement>(null)
  const [tip, setTip] = useState(false)

  const distance = useTransform(mouseX, (val) => {
    const b = ref.current?.getBoundingClientRect()
    return val - (b ? b.x + b.width / 2 : 0)
  })

  const sizeMV = useTransform(distance, [-150, 0, 150], [42, 76, 42])
  const size   = useSpring(sizeMV, { mass: 0.1, stiffness: 200, damping: 16 })

  return (
    <div className="relative flex flex-col items-center">

      {/* Tooltip */}
      <motion.div
        initial={false}
        animate={{ opacity: tip ? 1 : 0, y: tip ? 0 : 5 }}
        transition={{ duration: 0.15 }}
        className="absolute bottom-full mb-2.5 px-2.5 py-1 rounded-lg
                   text-[10px] font-semibold tracking-wide whitespace-nowrap
                   pointer-events-none select-none"
        style={{
          background: 'rgba(12,30,48,0.88)',
          color: '#EAF2FA',
          backdropFilter: 'blur(6px)',
        }}
      >
        {item.title}
        {/* Arrow */}
        <span
          className="absolute left-1/2 -translate-x-1/2 top-full"
          style={{
            width: 0, height: 0,
            borderLeft: '4px solid transparent',
            borderRight: '4px solid transparent',
            borderTop: '4px solid rgba(12,30,48,0.88)',
          }}
        />
      </motion.div>

      {/* Icon button */}
      <motion.button
        ref={ref}
        style={{ width: size, height: size }}
        onHoverStart={() => setTip(true)}
        onHoverEnd={() => setTip(false)}
        onFocus={() => setTip(true)}
        onBlur={() => setTip(false)}
        onClick={item.onClick}
        aria-label={item.title}
        aria-current={item.active ? 'page' : undefined}
        className="flex items-center justify-center rounded-xl cursor-pointer flex-shrink-0"
        animate={{
          background: item.active ? '#1248BE' : 'rgba(12,30,48,0.07)',
          color:      item.active ? '#EAF2FA'  : 'rgba(12,30,48,0.50)',
          boxShadow:  item.active
            ? '0 4px 16px rgba(18,72,190,0.30)'
            : '0 0 0 transparent',
        }}
        transition={{ duration: 0.18 }}
        whileTap={{ scale: 0.90 }}
      >
        {item.icon}
      </motion.button>
    </div>
  )
}

/* ── Dock container ── */
export function FloatingDock({ items }: { items: DockItem[] }) {
  const mouseX = useMotionValue(Infinity)

  return (
    <motion.div
      onMouseMove={(e) => mouseX.set(e.clientX)}
      onMouseLeave={() => mouseX.set(Infinity)}
      className="fixed bottom-5 left-1/2 -translate-x-1/2 z-50
                 flex items-end gap-2 px-4 py-3 rounded-2xl"
      style={{
        background:     'rgba(255,255,255,0.80)',
        backdropFilter: 'blur(20px)',
        border:         '1px solid rgba(12,30,48,0.10)',
        boxShadow:      '0 8px 40px rgba(12,30,48,0.12), 0 2px 8px rgba(12,30,48,0.06)',
      }}
      initial={{ y: 80, opacity: 0 }}
      animate={{ y: 0,  opacity: 1 }}
      transition={{ type: 'spring', stiffness: 260, damping: 22, delay: 0.1 }}
    >
      {items.map((item) => (
        <DockIcon key={item.id} item={item} mouseX={mouseX} />
      ))}
    </motion.div>
  )
}
