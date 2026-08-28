import { useEffect, useState } from 'react'
import { ApiError, getHealth, type HealthResponse } from '@/lib/api'

type State =
  | { kind: 'loading' }
  | { kind: 'ready'; health: HealthResponse }
  | { kind: 'error'; message: string; requestId: string | null }

/**
 * Health-check page.
 *
 * Deliberately minimal, but it establishes the visual direction the dashboard
 * will inherit: mono tabular figures for anything numeric, a status dot driven
 * by semantic tokens, and a restrained panel treatment.
 */
export default function App() {
  const [state, setState] = useState<State>({ kind: 'loading' })

  useEffect(() => {
    let cancelled = false

    getHealth()
      .then((health) => {
        if (!cancelled) setState({ kind: 'ready', health })
      })
      .catch((error: unknown) => {
        if (cancelled) return
        setState({
          kind: 'error',
          message: error instanceof Error ? error.message : 'Unknown error',
          requestId: error instanceof ApiError ? error.requestId : null,
        })
      })

    return () => {
      cancelled = true
    }
  }, [])

  return (
    <main className="mx-auto flex min-h-dvh max-w-2xl flex-col justify-center px-4 py-10 sm:px-6">
      <header className="mb-6">
        <h1 className="text-xl font-semibold tracking-tight text-ink">
          Revenue Recovery
        </h1>
        <p className="mt-1 text-sm text-ink-muted">
          Detects at-risk revenue, runs bounded interventions, proves what it
          recovered.
        </p>
      </header>

      <section
        aria-labelledby="backend-status"
        className="rounded-panel border border-border bg-surface shadow-xs"
      >
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <h2
            id="backend-status"
            className="text-xs font-medium tracking-wider text-ink-muted uppercase"
          >
            Backend status
          </h2>
          <StatusIndicator state={state} />
        </div>

        <dl className="divide-y divide-border text-sm">
          {state.kind === 'loading' && (
            <Row label="Connecting" value="..." aria-busy="true" />
          )}

          {state.kind === 'error' && (
            <>
              <Row label="Error" value={state.message} tone="failed" />
              {state.requestId !== null && (
                <Row label="Request ID" value={state.requestId} mono />
              )}
            </>
          )}

          {state.kind === 'ready' && (
            <>
              <Row
                label="Status"
                value={state.health.status}
                tone="recovered"
              />
              <Row label="Version" value={state.health.version} mono />
              <Row label="Environment" value={state.health.env} mono />
              <Row
                label="LLM providers"
                value={
                  state.health.llm_providers.length > 0
                    ? state.health.llm_providers.join(', ')
                    : 'none configured'
                }
                tone={
                  state.health.llm_providers.length > 0 ? undefined : 'pending'
                }
              />
            </>
          )}
        </dl>
      </section>

      <p className="mt-4 text-xs text-ink-subtle">
        Scaffold only - no detection, intervention, or recovery logic yet.
      </p>
    </main>
  )
}

function StatusIndicator({ state }: { state: State }) {
  const config = {
    loading: { color: 'bg-pending', label: 'Checking' },
    ready: { color: 'bg-recovered', label: 'Online' },
    error: { color: 'bg-failed', label: 'Unreachable' },
  }[state.kind]

  return (
    <span className="flex items-center gap-2">
      <span
        className={`size-2 rounded-full ${config.color}`}
        aria-hidden="true"
      />
      <span className="text-xs font-medium text-ink">{config.label}</span>
    </span>
  )
}

function Row({
  label,
  value,
  mono = false,
  tone,
  ...rest
}: {
  label: string
  value: string
  mono?: boolean
  tone?: 'recovered' | 'pending' | 'failed'
} & React.HTMLAttributes<HTMLDivElement>) {
  const toneClass = tone
    ? {
        recovered: 'text-recovered',
        pending: 'text-pending',
        failed: 'text-failed',
      }[tone]
    : 'text-ink'

  return (
    <div
      className="flex items-baseline justify-between gap-4 px-4 py-2.5"
      {...rest}
    >
      <dt className="shrink-0 text-ink-muted">{label}</dt>
      <dd
        className={`${toneClass} ${mono ? 'font-mono text-xs' : ''} text-right break-all`}
      >
        {value}
      </dd>
    </div>
  )
}
