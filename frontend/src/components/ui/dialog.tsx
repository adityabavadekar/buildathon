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
      <div className="relative z-50 max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-panel border border-border bg-surface p-6 text-ink shadow-lg">
        <div className="flex items-start justify-between border-b border-border pb-4">
          <div>
            <h2 className="font-mono text-base font-semibold tracking-tight text-ink">
              {title}
            </h2>
            {description && (
              <p className="mt-0.5 text-xs text-ink-muted">{description}</p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="cursor-pointer rounded-control p-1 font-mono text-xs text-ink-muted transition-colors hover:bg-surface-sunken hover:text-ink"
          >
            Esc [X]
          </button>
        </div>

        <div className="mt-4">{children}</div>
      </div>
    </div>
  )
}
