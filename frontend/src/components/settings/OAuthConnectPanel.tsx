'use client'

import React, { useCallback, useEffect, useState } from 'react'
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
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
import { RazorpaySymbol } from '@/components/ui/BrandIcons'

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
  const [expanded, setExpanded] = useState<boolean>(false)
  const [userToggled, setUserToggled] = useState<boolean>(false)

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

  // Nothing to act on once connected -- default to collapsed. An error, a
  // notice, or the user's own toggle always wins over that default.
  const isExpanded =
    userToggled || connected || shownError !== null || shownNotice !== null
      ? expanded
      : false

  return (
    <Card>
      <CardHeader>
        <button
          type="button"
          onClick={() => {
            setUserToggled(true)
            setExpanded((prev) => !prev)
          }}
          className="flex w-full cursor-pointer items-start justify-between gap-3 text-left"
        >
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
          <div className="flex shrink-0 items-center gap-2">
            <Badge
              variant={connected ? 'recovered' : 'outline'}
              className="text-[10px]"
            >
              {connected
                ? 'Connected'
                : configured
                  ? 'Not connected'
                  : 'Unconfigured'}
            </Badge>
            {isExpanded ? (
              <ChevronDown className="h-4 w-4 text-ink-muted" />
            ) : (
              <ChevronRight className="h-4 w-4 text-ink-muted" />
            )}
          </div>
        </button>
      </CardHeader>

      {isExpanded && (
        <CardContent className="space-y-4">
          <div className="flex items-center gap-3 rounded-panel border border-border bg-surface-sunken p-4">
            <div
              className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full ${
                connected
                  ? 'bg-recovered/15 text-recovered'
                  : 'bg-border/60 text-ink-muted'
              }`}
            >
              {connected ? (
                <Link2 className="h-5 w-5" aria-hidden="true" />
              ) : (
                <Unplug className="h-5 w-5" aria-hidden="true" />
              )}
            </div>

            <div className="h-px flex-1 border-t-2 border-dashed border-border" />

            <div
              className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full ${
                connected ? 'bg-recovered/15' : 'bg-border/60'
              }`}
            >
              <RazorpaySymbol className="h-5 w-5" />
            </div>

            <div className="min-w-0 flex-1 pl-1">
              <p className="text-sm font-semibold text-ink">
                {connected
                  ? (status.account_id_masked ?? 'Merchant account connected')
                  : 'No account connected'}
              </p>
              <p className="text-xs text-ink-muted">
                {connected
                  ? `Renews automatically, ${expiryLabel(
                      status.token_expires_at,
                      status.access_token_expired,
                    ).toLowerCase()}`
                  : 'Recovery actions use your API keys until an account is connected.'}
              </p>
            </div>
          </div>

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
              className="cursor-pointer gap-2 text-xs"
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
                  className="cursor-pointer gap-2 text-xs"
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
                  className="cursor-pointer gap-2 text-xs"
                >
                  <Unplug className="h-3.5 w-3.5" aria-hidden="true" />
                  Disconnect
                </Button>
              </>
            )}
          </div>
        </CardContent>
      )}
    </Card>
  )
}
