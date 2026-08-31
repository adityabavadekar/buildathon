'use client'

import Link from 'next/link'

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-canvas p-4 text-ink">
      <h2 className="font-mono text-xl font-semibold">404 - Page Not Found</h2>
      <p className="mt-2 text-xs text-ink-muted">
        The requested page does not exist.
      </p>
      <Link
        href="/"
        className="mt-4 rounded-control border border-border bg-surface-sunken px-3 py-1.5 font-mono text-xs text-ink hover:bg-border/40"
      >
        Return to Dashboard
      </Link>
    </div>
  )
}
