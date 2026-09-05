'use client'

import React, { useCallback, useEffect, useState } from 'react'
import {
  AlertCircle,
  AlertTriangle,
  Eye,
  EyeOff,
  KeyRound,
  Loader2,
  Lock,
} from 'lucide-react'
import { getSessionStatus, login, onSessionExpired } from '@/lib/api'
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
  const [showPassword, setShowPassword] = useState<boolean>(false)
  const [capsLock, setCapsLock] = useState<boolean>(false)
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

  useEffect(
    () =>
      onSessionExpired(() => {
        setAllowed(false)
      }),
    [],
  )

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
      <div className="operator-auth-canvas flex min-h-screen items-center justify-center p-6 text-sidebar-ink">
        <div className="flex flex-col items-center gap-3 text-center">
          <div className="sidebar-brand-logo flex h-10 w-10 items-center justify-center rounded-control border border-sidebar-border bg-sidebar-elevated">
            <RazorpaySymbol className="h-5 w-5" />
          </div>
          <div className="space-y-1">
            <div className="font-mono text-xs font-semibold text-sidebar-ink">
              FORTX
            </div>
            <div className="font-mono text-[11px] text-sidebar-ink-muted">
              Initializing operator gateway...
            </div>
          </div>
        </div>
      </div>
    )
  }

  if (allowed) {
    return <>{children}</>
  }

  return (
    <div className="operator-auth-canvas relative flex min-h-screen items-center justify-center p-4 sm:p-6">
      <div className="relative w-full max-w-md">
        <form
          onSubmit={(event) => {
            void handleSubmit(event)
          }}
          className="space-y-5 rounded-panel border border-sidebar-border bg-sidebar p-6 shadow-sm sm:p-7"
        >
          {/* Brand header */}
          <div className="flex items-center gap-3">
            <div className="sidebar-brand-logo flex h-10 w-10 items-center justify-center rounded-control border border-sidebar-border bg-sidebar-elevated">
              <RazorpaySymbol className="h-5 w-5" />
            </div>
            <div>
              <span className="text-sm font-semibold text-sidebar-ink">
                FORTX
              </span>
              <p className="font-mono text-xs text-sidebar-ink-muted">
                Revenue Recovery Engine
              </p>
            </div>
          </div>

          {/* Operator sign in title and context */}
          <div className="space-y-1">
            <h1 className="text-base font-semibold text-sidebar-ink">
              Operator Sign In
            </h1>
            <p className="text-xs leading-relaxed text-sidebar-ink-muted">
              Authenticate this workstation to access recovery telemetry,
              autonomous policies, and audit trails.
            </p>
          </div>

          {/* Password field */}
          <div className="space-y-2">
            <label
              htmlFor="operator-password"
              className="block text-xs font-medium text-sidebar-ink"
            >
              Operator password
            </label>

            <div className="relative flex items-center rounded-control border border-sidebar-border bg-sidebar-elevated focus-within:border-accent">
              <KeyRound
                className="ml-3 h-4 w-4 shrink-0 text-sidebar-ink-subtle"
                aria-hidden="true"
              />
              <input
                id="operator-password"
                type={showPassword ? 'text' : 'password'}
                autoFocus
                autoComplete="current-password"
                value={password}
                placeholder="Enter system password..."
                onChange={(event) => {
                  setPassword(event.target.value)
                }}
                onKeyDown={(event) => {
                  setCapsLock(event.getModifierState('CapsLock'))
                }}
                onKeyUp={(event) => {
                  setCapsLock(event.getModifierState('CapsLock'))
                }}
                className="w-full bg-transparent px-2.5 py-2 font-mono text-sm text-sidebar-ink placeholder:text-sidebar-ink-subtle focus:outline-none"
              />
              <button
                type="button"
                onClick={() => {
                  setShowPassword((prev) => !prev)
                }}
                aria-label={showPassword ? 'Hide password' : 'Show password'}
                className="mr-2.5 cursor-pointer rounded p-1 text-sidebar-ink-subtle hover:text-sidebar-ink"
              >
                {showPassword ? (
                  <EyeOff className="h-4 w-4" aria-hidden="true" />
                ) : (
                  <Eye className="h-4 w-4" aria-hidden="true" />
                )}
              </button>
            </div>

            {capsLock && (
              <p
                role="status"
                className="flex items-center gap-1.5 font-mono text-[11px] text-pending"
              >
                <AlertCircle className="h-3.5 w-3.5 shrink-0" />
                Caps Lock is on
              </p>
            )}
          </div>

          {/* Error banner */}
          {error !== null && (
            <div
              role="alert"
              className="flex items-start gap-2.5 rounded-control border border-failed/50 bg-failed/10 p-3 text-xs text-sidebar-ink"
            >
              <AlertTriangle
                className="mt-0.5 h-4 w-4 shrink-0 text-failed"
                aria-hidden="true"
              />
              <span className="leading-snug">{error}</span>
            </div>
          )}

          {/* Submit button */}
          <button
            type="submit"
            disabled={busy || password === ''}
            className="flex w-full cursor-pointer items-center justify-center gap-2 rounded-control border border-sidebar-active-border bg-sidebar-active-bg px-4 py-2 text-xs font-semibold text-sidebar-active-ink transition-colors hover:opacity-90 active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-40"
          >
            {busy ? (
              <>
                <Loader2
                  className="h-3.5 w-3.5 animate-spin"
                  aria-hidden="true"
                />
                <span>Authenticating operator...</span>
              </>
            ) : (
              <>
                <Lock className="h-3.5 w-3.5" aria-hidden="true" />
                <span>Sign in</span>
              </>
            )}
          </button>
        </form>
      </div>
    </div>
  )
}
