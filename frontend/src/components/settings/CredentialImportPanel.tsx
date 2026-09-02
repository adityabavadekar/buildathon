'use client'

import React, { useCallback, useEffect, useRef, useState } from 'react'
import { AlertTriangle, CheckCircle2, KeyRound, Upload } from 'lucide-react'
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

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
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
          <Badge
            variant={status?.configured ? 'recovered' : 'outline'}
            className="shrink-0 text-[10px]"
          >
            {status?.configured ? 'Active' : 'Not configured'}
          </Badge>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        <dl className="grid gap-3 text-xs md:grid-cols-3">
          <div className="space-y-1 rounded-control border border-border bg-surface-sunken p-3">
            <dt className="text-[11px] text-ink-muted">Active key</dt>
            <dd className="font-mono font-semibold text-ink">
              {status?.key_id_masked ?? 'None'}
            </dd>
          </div>
          <div className="space-y-1 rounded-control border border-border bg-surface-sunken p-3">
            <dt className="text-[11px] text-ink-muted">Source</dt>
            <dd className="font-semibold text-ink">
              {isImported ? 'Imported CSV' : 'Environment'}
            </dd>
          </div>
          <div className="space-y-1 rounded-control border border-border bg-surface-sunken p-3">
            <dt className="text-[11px] text-ink-muted">Webhook secret</dt>
            <dd className="font-semibold text-ink">
              {status?.webhook_secret_configured ? 'Configured' : 'Missing'}
            </dd>
          </div>
        </dl>

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
            className="cursor-pointer gap-2 font-mono text-xs"
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
              className="cursor-pointer font-mono text-xs"
            >
              Revert to environment
            </Button>
          )}
        </div>

        <p className="text-[11px] text-ink-muted">
          Accepts the CSV as downloaded. Expected columns are the key id and key
          secret; a webhook signing secret column is used when present.
        </p>
      </CardContent>
    </Card>
  )
}
