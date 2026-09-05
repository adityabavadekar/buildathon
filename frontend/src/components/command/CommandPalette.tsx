'use client'

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { CornerDownLeft, Database, Hash, Search, Zap } from 'lucide-react'
import {
  suggestSearchTerms,
  type RecoveryCase,
  type SearchSuggestion,
} from '@/lib/api'
import type { NavSection } from '@/lib/navigation'
import { formatCustomerName } from '@/lib/format'
import {
  MAIN_NAV_ITEMS,
  NAV_SECTION_LABELS,
  OPERATIONS_NAV_ITEMS,
  SETTINGS_NAV_ITEMS,
} from '@/lib/navigation'

interface CommandPaletteProps {
  open: boolean
  onClose: () => void
  cases: RecoveryCase[]
  onSelectCase: (c: RecoveryCase) => void
  onNavigate: (section: NavSection) => void
  /** Push a term into the recovery table's server-side search. */
  onSearchTerm?: (term: string) => void
}

const NAV_DESCRIPTIONS: Partial<Record<NavSection, string>> = {
  overview: 'Executive KPI dashboard and opportunity matrix',
  analytics: 'Counterfactual proof and NRV accounting',
  transactions: 'Active recovery queue and operational table',
  audit: 'System-wide immutable chronology',
  'settings-policies': 'Guardrails, touch limits, and discount caps',
  'settings-general': 'LLM provider hierarchy and experiment evaluation',
  'settings-integrations': 'Razorpay gateway, webhooks, and subsystem health',
  pipeline: 'Ingestion queue, fleet control, and worker telemetry',
  workflows: 'Durable recovery workflows and decision history',
  recovery: 'Active dunning queue and operational table',
  agent: 'Live decision stream and model token metrics',
  policies: 'Guardrails, touch limits, and discount caps',
  status: 'Telemetry, gateway health, and active queues',
  settings: 'Razorpay webhook URLs and integration config',
}

const SUGGEST_DEBOUNCE_MS = 160
const MIN_SUGGEST_LENGTH = 2
const MAX_CASE_ROWS = 6
const MAX_NAV_ROWS = 5

type Row =
  | { kind: 'action'; id: string; label: string; tag: string; run: () => void }
  | {
      kind: 'nav'
      id: string
      label: string
      desc: string
      section: NavSection
    }
  | { kind: 'suggestion'; id: string; suggestion: SearchSuggestion }
  | { kind: 'case'; id: string; recoveryCase: RecoveryCase }

export function CommandPalette({
  open,
  onClose,
  cases,
  onSelectCase,
  onNavigate,
  onSearchTerm,
}: CommandPaletteProps) {
  const [query, setQuery] = useState<string>('')
  const [suggestions, setSuggestions] = useState<SearchSuggestion[]>([])
  const [cursor, setCursor] = useState<number>(0)
  const listRef = useRef<HTMLDivElement | null>(null)

  const [wasOpen, setWasOpen] = useState<boolean>(open)
  if (open !== wasOpen) {
    setWasOpen(open)
    if (!open) {
      setQuery('')
      setSuggestions([])
      setCursor(0)
    }
  }

  // Suggestions come from the server so they cover every stored case, not just
  // the page already loaded in the browser.
  useEffect(() => {
    const term = query.trim()
    if (!open || term.length < MIN_SUGGEST_LENGTH) {
      return undefined
    }
    let cancelled = false
    const timer = setTimeout(() => {
      suggestSearchTerms(term)
        .then((rows) => {
          if (!cancelled) {
            setSuggestions(rows)
          }
        })
        .catch(() => {
          if (!cancelled) {
            setSuggestions([])
          }
        })
    }, SUGGEST_DEBOUNCE_MS)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [query, open])

  const navOptions = useMemo(
    () =>
      [
        ...MAIN_NAV_ITEMS.map((i) => i.id),
        ...SETTINGS_NAV_ITEMS.map((i) => i.id),
        ...OPERATIONS_NAV_ITEMS.map((i) => i.id),
      ].map((id) => ({
        id,
        label: NAV_SECTION_LABELS[id],
        desc: NAV_DESCRIPTIONS[id] ?? '',
      })),
    [],
  )

  const rows = useMemo<Row[]>(() => {
    const needle = query.trim().toLowerCase()
    const out: Row[] = []

    const usableSuggestions =
      needle.length >= MIN_SUGGEST_LENGTH ? suggestions : []

    out.push(
      ...usableSuggestions.map<Row>((s) => ({
        kind: 'suggestion',
        id: `sug-${s.field}-${s.value}`,
        suggestion: s,
      })),
    )

    out.push(
      ...navOptions
        .filter(
          (n) =>
            needle === '' ||
            n.label.toLowerCase().includes(needle) ||
            n.desc.toLowerCase().includes(needle),
        )
        .slice(0, MAX_NAV_ROWS)
        .map<Row>((n) => ({
          kind: 'nav',
          id: `nav-${n.id}`,
          label: n.label,
          desc: n.desc,
          section: n.id,
        })),
    )

    if (needle !== '') {
      out.push(
        ...cases
          .filter(
            (c) =>
              c.case_id.toLowerCase().includes(needle) ||
              c.failure_event.payment_id.toLowerCase().includes(needle) ||
              c.failure_event.customer_id.toLowerCase().includes(needle),
          )
          .slice(0, MAX_CASE_ROWS)
          .map<Row>((c) => ({
            kind: 'case',
            id: `case-${c.case_id}`,
            recoveryCase: c,
          })),
      )
    }

    return out
  }, [query, suggestions, navOptions, cases])

  const activeIndex = cursor >= rows.length ? 0 : cursor

  const runRow = useCallback(
    (row: Row): void => {
      if (row.kind === 'action') {
        row.run()
      } else if (row.kind === 'nav') {
        onNavigate(row.section)
      } else if (row.kind === 'case') {
        onSelectCase(row.recoveryCase)
      } else {
        onSearchTerm?.(row.suggestion.value)
        onNavigate('recovery')
      }
      onClose()
    },
    [onNavigate, onSelectCase, onSearchTerm, onClose],
  )

  useEffect(() => {
    if (!open) {
      return undefined
    }
    const onKey = (e: KeyboardEvent): void => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        onClose()
        return
      }
      if (e.key === 'Escape') {
        onClose()
        return
      }
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault()
        setCursor((prev) => {
          if (rows.length === 0) {
            return 0
          }
          const step = e.key === 'ArrowDown' ? 1 : -1
          return (prev + step + rows.length) % rows.length
        })
        return
      }
      if (e.key === 'Enter') {
        const row = rows.at(activeIndex)
        if (row) {
          e.preventDefault()
          runRow(row)
        }
      }
    }
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
    }
  }, [open, onClose, rows, activeIndex, runRow])

  useEffect(() => {
    listRef.current
      ?.querySelector('[data-active="true"]')
      ?.scrollIntoView({ block: 'nearest' })
  }, [activeIndex])

  if (!open) {
    return null
  }

  let index = -1
  const nextIndex = (): number => {
    index += 1
    return index
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 p-4 pt-[8vh] backdrop-blur-xs"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-label="Command palette"
        onClick={(e) => {
          e.stopPropagation()
        }}
        className="animate-in fade-in zoom-in-95 flex max-h-[78vh] w-full max-w-3xl flex-col overflow-hidden rounded-panel border border-border bg-surface shadow-2xl duration-150"
      >
        <div className="flex items-center gap-2.5 border-b border-border bg-surface-sunken/40 px-4 py-2.5">
          <Search
            className="h-4 w-4 shrink-0 text-ink-subtle"
            aria-hidden="true"
          />
          <input
            type="text"
            autoFocus
            placeholder="Search cases, payments, customers, or jump to a screen..."
            value={query}
            onChange={(e) => {
              setQuery(e.target.value)
              setCursor(0)
            }}
            className="flex-1 bg-transparent text-sm text-ink placeholder:text-ink-subtle focus:outline-none"
          />
          <kbd className="rounded border border-border px-1.5 py-0.5 text-[10px] text-ink-subtle">
            Esc
          </kbd>
        </div>

        <div
          ref={listRef}
          className="min-h-0 flex-1 overflow-y-auto py-1 text-xs"
        >
          {rows.length === 0 && (
            <p className="px-4 py-6 text-center text-ink-muted">
              No matches for &ldquo;{query}&rdquo;.
            </p>
          )}

          {rows.map((row) => {
            const i = nextIndex()
            const isActive = i === activeIndex
            const base = `flex w-full cursor-pointer items-center gap-2.5 px-4 py-1.5 text-left transition-colors ${
              isActive ? 'bg-accent-subtle' : 'hover:bg-surface-sunken'
            }`
            return (
              <button
                key={row.id}
                type="button"
                data-active={isActive}
                onMouseEnter={() => {
                  setCursor(i)
                }}
                onClick={() => {
                  runRow(row)
                }}
                className={base}
              >
                {row.kind === 'action' && (
                  <>
                    <Zap
                      className="h-3.5 w-3.5 shrink-0 text-accent"
                      aria-hidden="true"
                    />
                    <span className="flex-1 truncate text-ink">
                      {row.label}
                    </span>
                    <span
                      className={`shrink-0 text-[10px] font-semibold ${
                        row.tag === 'Purge' ? 'text-failed' : 'text-accent'
                      }`}
                    >
                      {row.tag}
                    </span>
                  </>
                )}

                {row.kind === 'suggestion' && (
                  <>
                    <Database
                      className="h-3.5 w-3.5 shrink-0 text-ink-subtle"
                      aria-hidden="true"
                    />
                    <span className="flex-1 truncate text-ink">
                      {row.suggestion.value}
                    </span>
                    <span className="shrink-0 text-[10px] text-ink-muted">
                      {row.suggestion.kind}
                    </span>
                    <span className="shrink-0 text-[10px] text-ink-subtle">
                      {row.suggestion.case_count.toString()}
                    </span>
                  </>
                )}

                {row.kind === 'nav' && (
                  <>
                    <Hash
                      className="h-3.5 w-3.5 shrink-0 text-ink-subtle"
                      aria-hidden="true"
                    />
                    <span className="shrink-0 font-medium text-ink">
                      {row.label}
                    </span>
                    <span className="flex-1 truncate text-[11px] text-ink-subtle">
                      {row.desc}
                    </span>
                  </>
                )}

                {row.kind === 'case' && (
                  <>
                    <span
                      aria-hidden="true"
                      className="h-1.5 w-1.5 shrink-0 rounded-full bg-accent"
                    />
                    <span className="shrink-0 text-ink">
                      {row.recoveryCase.case_id.slice(0, 8)}
                    </span>
                    <span className="flex-1 truncate text-[11px] text-ink-muted">
                      {formatCustomerName(
                        row.recoveryCase.failure_event.customer_id,
                      )}{' '}
                      · {row.recoveryCase.failure_event.payment_rail} · INR{' '}
                      {(row.recoveryCase.amount_paise / 100).toFixed(0)}
                    </span>
                    <span className="shrink-0 text-[10px] text-ink-subtle">
                      {row.recoveryCase.state}
                    </span>
                  </>
                )}
              </button>
            )
          })}
        </div>

        <div className="flex items-center gap-3 border-t border-border bg-surface-sunken/40 px-4 py-1.5 text-[10px] text-ink-subtle">
          <span className="flex items-center gap-1">
            <kbd className="rounded border border-border px-1">up</kbd>
            <kbd className="rounded border border-border px-1">down</kbd>
            navigate
          </span>
          <span className="flex items-center gap-1">
            <CornerDownLeft className="h-3 w-3" aria-hidden="true" />
            open
          </span>
          <span className="ml-auto">{rows.length.toString()} results</span>
        </div>
      </div>
    </div>
  )
}
