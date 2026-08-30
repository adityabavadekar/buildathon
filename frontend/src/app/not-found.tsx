'use client'

import Link from 'next/link'

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-canvas text-ink p-4">
      <h2 className="text-xl font-semibold font-mono">404 - Page Not Found</h2>
      <p className="mt-2 text-xs text-ink-muted">The requested page does not exist.</p>
      <Link
        href="/"
        className="mt-4 rounded-control bg-surface-sunken border border-border px-3 py-1.5 text-xs font-mono text-ink hover:bg-border/40"
      >
        Return to Dashboard
      </Link>
    </div>
  )
}
