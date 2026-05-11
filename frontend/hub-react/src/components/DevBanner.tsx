import { useState } from 'react'
import { KeyRound, X } from 'lucide-react'
import { TOKEN_KEY } from '../api/client'

export default function DevBanner() {
  const [open, setOpen] = useState(!localStorage.getItem(TOKEN_KEY))
  const [token, setToken] = useState(localStorage.getItem(TOKEN_KEY) ?? '')
  const [saved, setSaved] = useState(false)

  function save() {
    localStorage.setItem(TOKEN_KEY, token.trim())
    setSaved(true)
    setTimeout(() => window.location.reload(), 600)
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="fixed bottom-4 right-4 z-50 flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium
          bg-am-ink text-white shadow-lg hover:bg-am-secondary transition-colors"
      >
        <KeyRound size={11} />
        Dev token
      </button>
    )
  }

  return (
    <div className="fixed bottom-4 right-4 z-50 w-80 bg-white rounded-xl shadow-2xl border border-am-border overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-am-border">
        <div className="flex items-center gap-2 text-xs font-semibold text-am-ink">
          <KeyRound size={12} className="text-am-blue" />
          Token de acesso (dev)
        </div>
        <button onClick={() => setOpen(false)} className="text-am-muted hover:text-am-ink transition-colors">
          <X size={14} />
        </button>
      </div>
      <div className="p-4">
        <p className="text-xs text-am-secondary mb-3">
          Cole aqui o Bearer JWT gerado pelo backend. Salvo em <code className="font-mono text-am-blue">localStorage</code>.
        </p>
        <textarea
          className="w-full text-xs font-mono border border-am-border rounded-lg p-2.5 resize-none outline-none
            focus:border-am-blue transition-colors text-am-ink bg-am-bg"
          rows={3}
          placeholder="eyJhbGciOiJIUzI1NiIsInR5..."
          value={token}
          onChange={(e) => setToken(e.target.value)}
        />
        <button
          onClick={save}
          className="mt-2 w-full py-2 rounded-lg text-xs font-semibold bg-am-blue text-white
            hover:bg-am-blue-hover transition-colors"
        >
          {saved ? 'Salvo ✓' : 'Salvar token'}
        </button>
      </div>
    </div>
  )
}
