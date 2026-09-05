'use client'

import React, { useCallback, useEffect, useState } from 'react'
import {
  AlertTriangle,
  CheckCircle2,
  ExternalLink,
  Link2,
  RefreshCw,
  Unplug,
} from 'lucide-react'
import {
  disconnectOAuth,
  getOAuthStatus,
  refreshOAuthConnection,
  startOAuthConnect,
  type OAuthConnectionStatus,
} from '@/lib/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { CopyButton } from '@/components/ui/CopyButton'

interface OAuthConnectPanelProps {
  onChanged: () => void
}

const MS_PER_DAY = 86_400_000

function daysUntil(iso: string | null): number | null {
  if (iso === null) {
    return null
  }
  const delta = new Date(iso).getTime() - Date.now()
  return Math.floor(delta / MS_PER_DAY)
}

function expiryLabel(iso: string | null, expired: boolean): string {
  if (iso === null) {
    return 'Not connected'
  }
  if (expired) {
    return 'Expired'
  }
  const days = daysUntil(iso)
  if (days === null) {
    return 'Unknown'
  }
  return days <= 0 ? 'Expires today' : `${days.toString()} days left`
}

export function OAuthConnectPanel({ onChanged }: OAuthConnectPanelProps) {
  const [status, setStatus] = useState<OAuthConnectionStatus | null>(null)
  const [busy, setBusy] = useState<boolean>(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const refresh = useCallback((): void => {
    getOAuthStatus()
      .then(setStatus)
      .catch((err: unknown) => {
        setError(
          err instanceof Error ? err.message : 'Could not read OAuth status',
        )
      })
  }, [])

  useEffect(refresh, [refresh])

  // The backend exchange redirects here with an outcome. Read once and strip the
  // params so a reload does not replay the banner.
  const [callbackOutcome] = useState<{ ok: boolean; detail: string } | null>(
    () => {
      if (typeof window === 'undefined') {
        return null
      }
      const params = new URLSearchParams(window.location.search)
      const outcome = params.get('oauth')
      if (outcome === null) {
        return null
      }
      window.history.replaceState(
        null,
        '',
        `${window.location.pathname}${window.location.hash}`,
      )
      return outcome === 'connected'
        ? { ok: true, detail: 'Razorpay account connected.' }
        : {
            ok: false,
            detail:
              params.get('oauth_detail') ?? 'Authorization did not complete.',
          }
    },
  )

  const handleConnect = useCallback(async (): Promise<void> => {
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      window.location.assign(await startOAuthConnect())
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : 'Could not start authorization',
      )
      setBusy(false)
    }
  }, [])

  const handleRefresh = useCallback(async (): Promise<void> => {
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      setStatus(await refreshOAuthConnection())
      setNotice('Access token rotated.')
      onChanged()
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : 'Could not refresh the token',
      )
    } finally {
      setBusy(false)
    }
  }, [onChanged])

  const handleDisconnect = useCallback(async (): Promise<void> => {
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      setStatus(await disconnectOAuth())
      setNotice('Disconnected. Reverted to API key authentication.')
      onChanged()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Could not disconnect')
    } finally {
      setBusy(false)
    }
  }, [onChanged])

  const connected = status?.connected === true
  const configured = status?.configured === true
  const shownError =
    error ??
    (callbackOutcome && !callbackOutcome.ok ? callbackOutcome.detail : null)
  const shownNotice =
    notice ?? (callbackOutcome?.ok === true ? callbackOutcome.detail : null)

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <CardTitle className="flex items-center gap-2">
              <Link2 className="h-4 w-4" aria-hidden="true" />
              Partner OAuth Connection
            </CardTitle>
            <CardDescription>
              Connect a sub-merchant account with Razorpay OAuth instead of
              pasting API keys. When connected, recovery actions authenticate as
              that merchant.
            </CardDescription>
          </div>
          <Badge
            variant={connected ? 'recovered' : 'outline'}
            className="shrink-0 text-[10px]"
          >
            {connected
              ? 'Connected'
              : configured
                ? 'Not connected'
                : 'Unconfigured'}
          </Badge>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {!configured && (
          <div className="space-y-2 rounded-control border border-border bg-surface-sunken p-3 text-xs">
            <p className="font-semibold text-ink">
              Requires Technology Partner onboarding
            </p>
            <ol className="ml-4 list-decimal space-y-1 text-ink-muted">
              <li>Sign up as a Razorpay Technology Partner via support.</li>
              <li>Register an application on the Partner Dashboard.</li>
              <li>
                Whitelist this redirect URI on the application, then set
                <span className="font-mono"> RAZORPAY_OAUTH_CLIENT_ID </span>
                and
                <span className="font-mono"> RAZORPAY_OAUTH_CLIENT_SECRET</span>
                .
              </li>
            </ol>
            <div className="flex items-center gap-2 pt-1">
              <span className="truncate font-mono text-[11px] text-ink select-all">
                {status?.redirect_uri ?? ''}
              </span>
              <CopyButton
                value={status?.redirect_uri ?? ''}
                subject="redirect URI"
                variant="outline"
              />
            </div>
          </div>
        )}

        <dl className="grid gap-3 text-xs md:grid-cols-4">
          <div className="space-y-1 rounded-control border border-border bg-surface-sunken p-3">
            <dt className="text-[11px] text-ink-muted">Sub-merchant</dt>
            <dd className="font-mono font-semibold text-ink">
              {status?.account_id_masked ?? 'None'}
            </dd>
          </div>
          <div className="space-y-1 rounded-control border border-border bg-surface-sunken p-3">
            <dt className="text-[11px] text-ink-muted">Scope</dt>
            <dd className="font-semibold text-ink">
              {status?.scope ?? status?.required_scope ?? '-'}
            </dd>
          </div>
          <div className="space-y-1 rounded-control border border-border bg-surface-sunken p-3">
            <dt className="text-[11px] text-ink-muted">Mode</dt>
            <dd className="font-semibold text-ink uppercase">
              {status?.mode ?? '-'}
            </dd>
          </div>
          <div className="space-y-1 rounded-control border border-border bg-surface-sunken p-3">
            <dt className="text-[11px] text-ink-muted">Access token</dt>
            <dd className="font-semibold text-ink">
              {expiryLabel(
                status?.token_expires_at ?? null,
                status?.access_token_expired === true,
              )}
            </dd>
          </div>
        </dl>

        {shownError !== null && (
          <p
            role="alert"
            className="border-status-failed/40 bg-status-failed/10 flex items-start gap-2 rounded-control border p-3 text-xs text-ink"
          >
            <AlertTriangle
              className="mt-0.5 h-3.5 w-3.5 shrink-0"
              aria-hidden="true"
            />
            {shownError}
          </p>
        )}

        {shownNotice !== null && (
          <p
            role="status"
            className="border-status-recovered/40 bg-status-recovered/10 flex items-start gap-2 rounded-control border p-3 text-xs text-ink"
          >
            <CheckCircle2
              className="mt-0.5 h-3.5 w-3.5 shrink-0"
              aria-hidden="true"
            />
            {shownNotice}
          </p>
        )}

        <div className="flex flex-wrap items-center gap-3">
          <Button
            variant="primary"
            size="sm"
            disabled={busy || !configured}
            onClick={() => {
              void handleConnect()
            }}
            className="cursor-pointer gap-2 font-mono text-xs"
          >
            <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
            {connected ? 'Reconnect account' : 'Connect Razorpay account'}
          </Button>

          {connected && (
            <>
              <Button
                variant="outline"
                size="sm"
                disabled={busy}
                onClick={() => {
                  void handleRefresh()
                }}
                className="cursor-pointer gap-2 font-mono text-xs"
              >
                <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
                Refresh token
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={busy}
                onClick={() => {
                  void handleDisconnect()
                }}
                className="cursor-pointer gap-2 font-mono text-xs"
              >
                <Unplug className="h-3.5 w-3.5" aria-hidden="true" />
                Disconnect
              </Button>
            </>
          )}
        </div>

        <p className="text-[11px] text-ink-muted">
          Tokens are held server-side and never displayed. An OAuth connection
          takes precedence over imported API keys. Access tokens last 90 days
          and refresh tokens 180; FORTX rotates them automatically before
          expiry.
        </p>
      </CardContent>
    </Card>
  )
}
