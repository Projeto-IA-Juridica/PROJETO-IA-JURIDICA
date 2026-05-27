import { useState, useRef, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ChevronDown, Check } from 'lucide-react'

export interface SelectOption {
  value: string
  label: string
}

interface SelectProps {
  value: string
  onChange: (value: string) => void
  options: SelectOption[]
  placeholder?: string
  className?: string
}

export function Select({ value, onChange, options, placeholder, className = '' }: SelectProps) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  const selected = options.find((o) => o.value === value)

  useEffect(() => {
    function onDown(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [])

  return (
    <div ref={ref} className={`relative ${className}`}>

      {/* Trigger */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-3.5 py-[10px] text-[13px] bg-white rounded-xl transition-all"
        style={{
          fontFamily: 'var(--font-sans)',
          border: open
            ? '1.5px solid var(--color-am-blue)'
            : '1.5px solid rgba(168,200,232,0.55)',
          boxShadow: open
            ? '0 0 0 3.5px rgba(58,122,184,0.13)'
            : '0 1px 2px rgba(12,30,48,0.04)',
          color: selected ? 'var(--color-am-ink)' : 'var(--color-am-muted)',
        }}>
        <span className="truncate text-left">{selected?.label ?? placeholder ?? ''}</span>
        <ChevronDown
          size={13}
          className="flex-shrink-0 ml-2 text-am-muted transition-transform duration-200"
          style={{ transform: open ? 'rotate(180deg)' : 'rotate(0deg)' }}
        />
      </button>

      {/* Dropdown */}
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -6, scale: 0.98 }}
            animate={{ opacity: 1, y: 0,  scale: 1    }}
            exit={{   opacity: 0, y: -6, scale: 0.98 }}
            transition={{ duration: 0.14, ease: 'easeOut' }}
            className="absolute left-0 right-0 top-full mt-1.5 bg-white rounded-xl z-50"
            style={{
              border: '1px solid var(--color-am-border)',
              boxShadow: '0 8px 24px rgba(12,30,48,0.12)',
            }}>
            <div className="max-h-56 overflow-y-auto rounded-xl py-1">
              {options.map((opt) => {
                const active = opt.value === value
                return (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => { onChange(opt.value); setOpen(false) }}
                    className="w-full flex items-center justify-between px-3.5 py-2.5 text-[12.5px] text-left transition-colors hover:bg-am-bg"
                    style={{
                      color:      active ? 'var(--color-am-blue)' : 'var(--color-am-ink)',
                      fontWeight: active ? 600 : 400,
                      background: active ? 'rgba(58,122,184,0.05)' : undefined,
                      fontFamily: 'var(--font-sans)',
                    }}>
                    <span>{opt.label}</span>
                    {active && <Check size={11} style={{ color: 'var(--color-am-blue)', flexShrink: 0 }} />}
                  </button>
                )
              })}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

    </div>
  )
}
