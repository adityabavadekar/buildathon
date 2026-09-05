'use client'

import React, { useCallback, useEffect, useRef, useState } from 'react'
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  KeyRound,
  Upload,
} from 'lucide-react'
import {
  clearGatewayCredentials,
  getGatewayCredentials,
  importGatewayCredentials,
  type GatewayCredentialStatus,
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

interface CredentialImportPanelProps {
  onImported: () => void
}

export function CredentialImportPanel({
  onImported,
}: CredentialImportPanelProps) {
  const [status, setStatus] = useState<GatewayCredentialStatus | null>(null)
  const [busy, setBusy] = useState<boolean>(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<boolean>(false)
  const [userToggled, setUserToggled] = useState<boolean>(false)
  const fileInput = useRef<HTMLInputElement | null>(null)

  const refresh = useCallback((): void => {
    getGatewayCredentials()
      .then(setStatus)
      .catch((err: unknown) => {
        setError(
          err instanceof Error ? err.message : 'Could not read credentials',
        )
      })
  }, [])

  useEffect(refresh, [refresh])

  const handleFile = useCallback(
    async (file: File): Promise<void> => {
      setBusy(true)
      setError(null)
      setNotice(null)
      try {
        const next = await importGatewayCredentials(file)
        setStatus(next)
        setNotice(
          `Imported ${next.key_id_masked ?? 'credentials'}${
            next.webhook_secret_configured ? ' with webhook secret' : ''
          }.`,
        )
        onImported()
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : 'Import failed')
      } finally {
        setBusy(false)
        if (fileInput.current) {
          // Clear the input so re-selecting the same file fires onChange again.
          fileInput.current.value = ''
        }
      }
    },
    [onImported],
  )

  const handleClear = useCallback(async (): Promise<void> => {
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      setStatus(await clearGatewayCredentials())
      setNotice('Reverted to environment credentials.')
      onImported()
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : 'Could not clear credentials',
      )
    } finally {
      setBusy(false)
    }
  }, [onImported])

  const isImported = status?.source === 'csv_import'
  const configured = status?.configured === true

  // Nothing to act on when unconfigured -- default to collapsed. An error, a
  // notice, being busy, or the user's own toggle always wins over that default.
  const isExpanded =
    userToggled || configured || error !== null || notice !== null || busy
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
              <KeyRound className="h-4 w-4" aria-hidden="true" />
              Gateway Credentials
            </CardTitle>
            <CardDescription>
              Import the API key CSV that Razorpay provides when you generate a
              key pair. The secret is stored server-side and never displayed.
            </CardDescription>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Badge
              variant={status?.configured ? 'recovered' : 'outline'}
              className="text-[10px]"
            >
              {status?.configured ? 'Active' : 'Not configured'}
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
          <div className="flex flex-wrap items-center gap-4 rounded-panel border border-border bg-surface-sunken p-4">
            <div
              className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full ${
                configured
                  ? 'bg-recovered/15 text-recovered'
                  : 'bg-border/60 text-ink-muted'
              }`}
            >
              <KeyRound className="h-5 w-5" aria-hidden="true" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold text-ink">
                {configured
                  ? (status.key_id_masked ?? 'Key configured')
                  : 'No API key configured'}
              </p>
              <p className="text-xs text-ink-muted">
                {status?.webhook_secret_configured
                  ? 'Payment updates from Razorpay are checked to confirm they are genuine.'
                  : 'Payment updates are accepted without confirming they came from Razorpay.'}
              </p>
            </div>
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

          {notice !== null && (
            <p
              role="status"
              className="border-status-recovered/40 bg-status-recovered/10 flex items-start gap-2 rounded-control border p-3 text-xs text-ink"
            >
              <CheckCircle2
                className="mt-0.5 h-3.5 w-3.5 shrink-0"
                aria-hidden="true"
              />
              {notice}
            </p>
          )}

          <div className="flex flex-wrap items-center gap-3">
            <input
              ref={fileInput}
              id="credential-csv"
              type="file"
              accept=".csv,text/csv"
              className="sr-only"
              onChange={(event) => {
                const file = event.target.files?.[0]
                if (file) {
                  void handleFile(file)
                }
              }}
            />
            <Button
              variant="primary"
              size="sm"
              disabled={busy}
              onClick={() => {
                fileInput.current?.click()
              }}
              className="cursor-pointer gap-2 text-xs"
            >
              <Upload className="h-3.5 w-3.5" aria-hidden="true" />
              {busy ? 'Importing...' : 'Import key CSV'}
            </Button>

            {isImported && (
              <Button
                variant="outline"
                size="sm"
                disabled={busy}
                onClick={() => {
                  void handleClear()
                }}
                className="cursor-pointer text-xs"
              >
                Revert to environment
              </Button>
            )}
          </div>
        </CardContent>
      )}
    </Card>
  )
}
