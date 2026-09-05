'use client'

import React, { useCallback, useEffect, useState } from 'react'
import { AlertTriangle, Lock } from 'lucide-react'
import { getSessionStatus, login } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { RazorpaySymbol } from '@/components/ui/BrandIcons'

interface LoginGateProps {
  children: React.ReactNode
}

/**
 * Children mount only once the session is known good, so the dashboard's first
 * fetch does not fire a wall of 401s. A no-op when no password is configured.
 */
export function LoginGate({ children }: LoginGateProps) {
  const [checked, setChecked] = useState<boolean>(false)
  const [allowed, setAllowed] = useState<boolean>(false)
  const [password, setPassword] = useState<string>('')
  const [busy, setBusy] = useState<boolean>(false)
  const [error, setError] = useState<string | null>(null)

  const check = useCallback((): void => {
    getSessionStatus()
      .then((status) => {
        setAllowed(status.authenticated)
        setChecked(true)
      })
      .catch(() => {
        // If the status call itself fails the backend is unreachable; showing the
        // dashboard is more useful than a login form that cannot succeed.
        setAllowed(true)
        setChecked(true)
      })
  }, [])

  useEffect(check, [check])

  const handleSubmit = useCallback(
    async (event: React.SyntheticEvent<HTMLFormElement>): Promise<void> => {
      event.preventDefault()
      setBusy(true)
      setError(null)
      try {
        const status = await login(password)
        setAllowed(status.authenticated)
        setPassword('')
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : 'Sign in failed')
      } finally {
        setBusy(false)
      }
    },
    [password],
  )

  if (!checked) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-canvas">
        <span className="font-mono text-xs text-ink-muted">Loading...</span>
      </div>
    )
  }

  if (allowed) {
    return <>{children}</>
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-canvas p-6">
      <form
        onSubmit={(event) => {
          void handleSubmit(event)
        }}
        className="w-full max-w-sm space-y-4 rounded-panel border border-border bg-surface p-6 shadow-sm"
      >
        <div className="flex items-center gap-3">
          <div className="sidebar-brand-logo flex h-9 w-9 items-center justify-center rounded-control border">
            <RazorpaySymbol className="h-5 w-5" />
          </div>
          <div>
            <h1 className="font-mono text-sm font-semibold text-ink">FORTX</h1>
            <p className="text-xs text-ink-muted">Operator sign in</p>
          </div>
        </div>

        <div className="space-y-1.5">
          <label
            htmlFor="operator-password"
            className="block text-xs font-medium text-ink"
          >
            Operator password
          </label>
          <input
            id="operator-password"
            type="password"
            autoFocus
            autoComplete="current-password"
            value={password}
            onChange={(event) => {
              setPassword(event.target.value)
            }}
            className="w-full rounded-control border border-border bg-surface-sunken px-3 py-2 font-mono text-sm text-ink focus:outline-none"
          />
        </div>

        {error !== null && (
          <p
            role="alert"
            className="border-status-failed/40 bg-status-failed/10 flex items-start gap-2 rounded-control border p-3 text-xs text-ink"
          >
            <AlertTriangle
              className="mt-0.5 h-3.5 w-3.5 shrink-0"
              aria-hidden="true"
            />
            {error}
          </p>
        )}

        <Button
          type="submit"
          variant="primary"
          size="sm"
          disabled={busy || password === ''}
          className="w-full cursor-pointer gap-2 font-mono text-xs"
        >
          <Lock className="h-3.5 w-3.5" aria-hidden="true" />
          {busy ? 'Signing in...' : 'Sign in'}
        </Button>
      </form>
    </div>
  )
}
