import React, { useEffect } from 'react'

interface DialogProps {
  open: boolean
  onClose: () => void
  children: React.ReactNode
  title: string
  description?: string
}

export function Dialog({
  open,
  onClose,
  children,
  title,
  description,
}: DialogProps) {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    if (open) {
      window.addEventListener('keydown', handleKeyDown)
      document.body.style.overflow = 'hidden'
    }
    return () => {
      window.removeEventListener('keydown', handleKeyDown)
      document.body.style.overflow = 'unset'
    }
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-ink/40 backdrop-blur-xs transition-opacity"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Modal Dialog */}
      <div className="relative z-50 w-full max-w-2xl max-h-[85vh] overflow-y-auto rounded-panel border border-border bg-surface text-ink shadow-lg p-6">
        <div className="flex items-start justify-between border-b border-border pb-4">
          <div>
            <h2 className="text-base font-semibold tracking-tight text-ink font-mono">
              {title}
            </h2>
            {description && (
              <p className="mt-0.5 text-xs text-ink-muted">{description}</p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-control p-1 text-ink-muted hover:text-ink hover:bg-surface-sunken transition-colors cursor-pointer text-xs font-mono"
          >
            Esc [X]
          </button>
        </div>

        <div className="mt-4">{children}</div>
      </div>
    </div>
  )
}
