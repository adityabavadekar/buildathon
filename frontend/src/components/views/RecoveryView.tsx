'use client'

import React, { useEffect, useState, useCallback } from 'react'
import {
  ArrowUpDown,
  CheckCircle2,
  RefreshCw,
  Search,
  SlidersHorizontal,
  UserCheck,
  X,
} from 'lucide-react'
import {
  approveCase,
  getAnalytics,
  getPolicies,
  listCases,
  type AnalyticsSummaryResponse,
  type CaseFilterParams,
  type PolicyResponse,
  type RecoveryCase,
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
import { RailBadge } from '@/components/ui/BrandIcons'
import { StatCard } from '@/components/ui/StatCard'
import { SkeletonRow } from '@/components/ui/skeleton'
import { EscalationsQueuePanel } from '@/components/recovery/EscalationsQueuePanel'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

interface RecoveryViewProps {
  onSelectCase: (c: RecoveryCase) => void
  initialSubTab?: string
}

function formatINR(paise: number): string {
  const rupees = paise / 100
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(rupees)
}

function stateToVariant(state: string): 'default' | 'recovered' | 'escalated' | 'failed' | 'pending' | 'outline' {
  switch (state) {
    case 'RECOVERED':
      return 'recovered'
    case 'ESCALATED':
      return 'escalated'
    case 'FAILED':
      return 'failed'
    case 'IN_DUNNING':
    case 'OUTREACH_PENDING':
    case 'RETRY_SCHEDULED':
      return 'pending'
    default:
      return 'outline'
  }
}

const RAILS = ['UPI', 'CARDS', 'MANDATES', 'NETBANKING', 'INVOICES']

export function RecoveryView({
  onSelectCase,
  initialSubTab = 'ALL',
}: RecoveryViewProps) {
  const [activeTab, setActiveTab] = useState<string>(initialSubTab)
  const [searchQuery, setSearchQuery] = useState<string>('')
  const [selectedRails, setSelectedRails] = useState<string[]>([])
  const [selectedArm, setSelectedArm] = useState<string>('')
  const [minAmount, setMinAmount] = useState<string>('')
  const [maxAmount, setMaxAmount] = useState<string>('')
  const [errorCode, setErrorCode] = useState<string>('')
  const [modelFilter, setModelFilter] = useState<string>('')
  const [onlyRecovered, setOnlyRecovered] = useState<boolean>(false)
  const [onlyEscalated, setOnlyEscalated] = useState<boolean>(false)
  const [sortBy, setSortBy] = useState<string>('created_at')
  const [sortDir, setSortDir] = useState<string>('desc')
  const [showAdvanced, setShowAdvanced] = useState<boolean>(false)

  // Server state
  const [cases, setCases] = useState<RecoveryCase[]>([])
  const [totalCount, setTotalCount] = useState<number>(0)
  const [page, setPage] = useState<number>(0)
  const [pageSize, setPageSize] = useState<number>(25)
  const [loading, setLoading] = useState<boolean>(true)
  const [approvingId, setApprovingId] = useState<string | null>(null)
  const [policy, setPolicy] = useState<PolicyResponse | null>(null)
  const [analytics, setAnalytics] = useState<AnalyticsSummaryResponse | null>(null)

  useEffect(() => {
    getPolicies()
      .then(setPolicy)
      .catch(() => null)
  }, [])

  useEffect(() => {
    getAnalytics()
      .then(setAnalytics)
      .catch(() => null)
  }, [])

  const fetchCases = useCallback(async () => {
    setLoading(true)
    try {
      const params: CaseFilterParams = {
        limit: pageSize,
        offset: page * pageSize,
        sort_by: sortBy,
        sort_dir: sortDir,
      }

      if (searchQuery.trim()) {
        params.q = searchQuery.trim()
      }

      if (selectedRails.length > 0) {
        params.payment_rails = selectedRails.join(',')
      }

      if (selectedArm) {
        params.experiment_arm = selectedArm
      }

      if (errorCode.trim()) {
        params.error_code = errorCode.trim()
      }

      if (modelFilter.trim()) {
        params.model_used = modelFilter.trim()
      }

      if (minAmount.trim() && !isNaN(Number(minAmount))) {
        params.amount_min_paise = Math.round(Number(minAmount) * 100)
      }

      if (maxAmount.trim() && !isNaN(Number(maxAmount))) {
        params.amount_max_paise = Math.round(Number(maxAmount) * 100)
      }

      if (onlyRecovered) {
        params.recovered = true
      }

      if (onlyEscalated) {
        params.has_escalation = true
      }

      // Handle sub-tab filtering
      switch (activeTab) {
        case 'ACTIVE':
          params.states = 'IN_DUNNING,OUTREACH_PENDING,RETRY_SCHEDULED'
          break
        case 'AT_RISK':
          params.states = 'ANALYSIS_QUEUED,IN_DUNNING,ESCALATED,FAILED'
          break
        case 'RECOVERED':
          params.state = 'RECOVERED'
          break
        case 'ESCALATED':
          params.state = 'ESCALATED'
          break
        default:
          break
      }

      const res = await listCases(params)
      setCases(res.items)
      setTotalCount(res.total)
    } catch {
      setCases([])
      setTotalCount(0)
    } finally {
      setLoading(false)
    }
  }, [
    activeTab,
    searchQuery,
    selectedRails,
    selectedArm,
    errorCode,
    modelFilter,
    minAmount,
    maxAmount,
    onlyRecovered,
    onlyEscalated,
    sortBy,
    sortDir,
    page,
    pageSize,
  ])

  useEffect(() => {
    let active = true
    const timer = setTimeout(() => {
      if (active) void fetchCases()
    }, 0)
    return () => {
      active = false
      clearTimeout(timer)
    }
  }, [fetchCases])

  const handleTabSelect = (tab: string) => {
    setActiveTab(tab)
    setPage(0)
  }

  const toggleRail = (rail: string) => {
    setSelectedRails((prev) =>
      prev.includes(rail) ? prev.filter((r) => r !== rail) : [...prev, rail]
    )
    setPage(0)
  }

  const clearAllFilters = () => {
    setSearchQuery('')
    setSelectedRails([])
    setSelectedArm('')
    setMinAmount('')
    setMaxAmount('')
    setErrorCode('')
    setModelFilter('')
    setOnlyRecovered(false)
    setOnlyEscalated(false)
    setPage(0)
  }

  const hasActiveFilters =
    searchQuery.trim() !== '' ||
    selectedRails.length > 0 ||
    selectedArm !== '' ||
    minAmount !== '' ||
    maxAmount !== '' ||
    errorCode !== '' ||
    modelFilter !== '' ||
    onlyRecovered ||
    onlyEscalated

  const handleApprove = async (e: React.MouseEvent, c: RecoveryCase) => {
    e.stopPropagation()
    setApprovingId(c.case_id)
    try {
      await approveCase(c.case_id, 'Operator sign-off via Recovery View')
      await fetchCases()
    } finally {
      setApprovingId(null)
    }
  }

  const maxTouches = policy?.max_touches ?? 3
  const totalPages = Math.ceil(totalCount / pageSize)

  return (
    <div className="space-y-6">
      {/* Top Stat Summary Cards */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard
          title="Revenue at Risk"
          value={formatINR(analytics?.total_at_risk_paise ?? 0)}
          variant="failed"
          subtitle="Outstanding payments being recovered"
        />
        <StatCard
          title="Net Recovered"
          value={formatINR(analytics?.net_recovered_value_paise ?? 0)}
          variant="recovered"
          subtitle="Value recovered net of intervention cost"
        />
        <StatCard
          title="Active Cases"
          value={analytics?.active_cases?.toString() ?? '0'}
          variant="accent"
          subtitle="Recovery lifecycles in progress"
        />
        <StatCard
          title="Recovery Rate"
          value={`${(analytics?.overall_recovery_rate_pct ?? 0).toFixed(1)}%`}
          variant="default"
          subtitle="Share of at-risk value recovered"
        />
      </div>

      {/* Dedicated EV-Prioritized Escalations Queue Panel */}
      {activeTab === 'ESCALATED' && (
        <EscalationsQueuePanel
          onSelectCase={(caseId) => {
            const found = cases.find((item) => item.case_id === caseId)
            if (found) onSelectCase(found)
          }}
          onActionComplete={() => {
            void fetchCases()
          }}
        />
      )}

      {/* Directory Management Card */}
      <Card>
        <CardHeader className="pb-3 border-b border-border/40">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div>
              <CardTitle className="text-base font-semibold">
                Recovery Case Directory
              </CardTitle>
              <CardDescription className="text-xs">
                Filter, inspect, and approve stateful transaction recovery lifecycles
              </CardDescription>
            </div>

            {/* State Tabs */}
            <div className="flex items-center rounded-control bg-surface-sunken p-1 border border-border text-xs font-mono">
              {['ALL', 'ACTIVE', 'AT_RISK', 'RECOVERED', 'ESCALATED'].map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => {
                    handleTabSelect(t)
                  }}
                  className={`px-3 py-1 rounded-control transition-all cursor-pointer ${
                    activeTab === t
                      ? 'bg-surface text-ink font-bold shadow-xs'
                      : 'text-ink-muted hover:text-ink'
                  }`}
                >
                  {t.replace('_', ' ')}
                </button>
              ))}
            </div>
          </div>

          {/* Primary Filter Bar */}
          <div className="mt-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            {/* Search Input */}
            <div className="relative flex-1">
              <Search className="absolute left-3 top-2.5 h-4 w-4 text-ink-subtle" />
              <input
                type="text"
                placeholder="Search payment ID, customer, error code, reason, or model..."
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value)
                  setPage(0)
                }}
                className="w-full rounded-control border border-border bg-surface-sunken pl-9 pr-4 py-2 text-xs font-mono text-ink placeholder:text-ink-subtle focus:border-accent focus:outline-hidden"
              />
              {searchQuery && (
                <button
                  type="button"
                  onClick={() => {
                    setSearchQuery('')
                    setPage(0)
                  }}
                  className="absolute right-3 top-2.5 text-ink-muted hover:text-ink cursor-pointer"
                >
                  <X className="h-4 w-4" />
                </button>
              )}
            </div>

            {/* Sort & Advanced Toggle Controls */}
            <div className="flex items-center gap-2">
              <div className="flex items-center gap-1 bg-surface-sunken border border-border rounded-control px-2 py-1 text-xs font-mono">
                <ArrowUpDown className="h-3 w-3 text-ink-subtle" />
                <select
                  value={sortBy}
                  onChange={(e) => {
                    setSortBy(e.target.value)
                    setPage(0)
                  }}
                  aria-label="Sort by field"
                  className="bg-transparent text-ink border-none focus:outline-hidden text-xs cursor-pointer"
                >
                  <option value="created_at">Created Time</option>
                  <option value="amount_paise">Amount</option>
                  <option value="recovered_amount_paise">Recovered NRV</option>
                  <option value="touches_count">Touch Count</option>
                </select>
                <select
                  value={sortDir}
                  onChange={(e) => {
                    setSortDir(e.target.value)
                    setPage(0)
                  }}
                  aria-label="Sort direction"
                  className="bg-transparent text-ink border-none focus:outline-hidden text-xs cursor-pointer font-bold"
                >
                  <option value="desc">DESC</option>
                  <option value="asc">ASC</option>
                </select>
              </div>

              <Button
                variant={showAdvanced ? 'primary' : 'outline'}
                size="sm"
                onClick={() => {
                  setShowAdvanced(!showAdvanced)
                }}
                className="gap-1.5 text-xs font-mono cursor-pointer"
              >
                <SlidersHorizontal className="h-3.5 w-3.5" />
                <span>Filters</span>
                {hasActiveFilters && (
                  <span className="h-2 w-2 rounded-full bg-accent animate-pulse" />
                )}
              </Button>

              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  void fetchCases()
                }}
                disabled={loading}
                className="gap-1.5 text-xs font-mono cursor-pointer"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
                <span className="hidden sm:inline">Refresh</span>
              </Button>
            </div>
          </div>

          {/* Collapsible Advanced Filters Drawer */}
          {showAdvanced && (
            <div className="mt-3 p-3 rounded-control bg-surface-sunken border border-border space-y-3">
              {/* Payment Rail Filter Chips */}
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[11px] font-mono text-ink-muted uppercase">Payment Rails:</span>
                {RAILS.map((rail) => {
                  const isSelected = selectedRails.includes(rail)
                  return (
                    <button
                      key={rail}
                      type="button"
                      onClick={() => {
                        toggleRail(rail)
                      }}
                      className={`px-2 py-0.5 rounded-control text-xs font-mono border transition-colors cursor-pointer ${
                        isSelected
                          ? 'bg-ink text-surface font-bold border-ink'
                          : 'bg-surface text-ink-muted border-border hover:border-ink-muted'
                      }`}
                    >
                      {rail}
                    </button>
                  )
                })}
              </div>

              {/* Amount and Model Specific Filters */}
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <div>
                  <label className="text-[10px] font-mono text-ink-muted block mb-1">
                    MIN AMOUNT (INR)
                  </label>
                  <input
                    type="number"
                    placeholder="Min Rs."
                    value={minAmount}
                    onChange={(e) => {
                      setMinAmount(e.target.value)
                      setPage(0)
                    }}
                    className="w-full rounded-control border border-border bg-surface px-2 py-1 text-xs font-mono text-ink"
                  />
                </div>

                <div>
                  <label className="text-[10px] font-mono text-ink-muted block mb-1">
                    MAX AMOUNT (INR)
                  </label>
                  <input
                    type="number"
                    placeholder="Max Rs."
                    value={maxAmount}
                    onChange={(e) => {
                      setMaxAmount(e.target.value)
                      setPage(0)
                    }}
                    className="w-full rounded-control border border-border bg-surface px-2 py-1 text-xs font-mono text-ink"
                  />
                </div>

                <div>
                  <label className="text-[10px] font-mono text-ink-muted block mb-1">
                    ERROR CODE
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. AP15, VA, XT"
                    value={errorCode}
                    onChange={(e) => {
                      setErrorCode(e.target.value)
                      setPage(0)
                    }}
                    className="w-full rounded-control border border-border bg-surface px-2 py-1 text-xs font-mono text-ink uppercase"
                  />
                </div>

                <div>
                  <label className="text-[10px] font-mono text-ink-muted block mb-1">
                    MODEL IDENTIFIER
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. model filter"
                    value={modelFilter}
                    onChange={(e) => {
                      setModelFilter(e.target.value)
                      setPage(0)
                    }}
                    className="w-full rounded-control border border-border bg-surface px-2 py-1 text-xs font-mono text-ink"
                  />
                </div>
              </div>

              {/* Experiment Arm & Flags */}
              <div className="flex flex-wrap items-center justify-between gap-3 pt-1 border-t border-border/40">
                <div className="flex items-center gap-4 text-xs font-mono">
                  <label className="flex items-center gap-1.5 cursor-pointer text-ink">
                    <input
                      type="radio"
                      name="arm"
                      checked={selectedArm === ''}
                      onChange={() => {
                        setSelectedArm('')
                        setPage(0)
                      }}
                      className="accent-accent"
                    />
                    <span>All Arms</span>
                  </label>
                  <label className="flex items-center gap-1.5 cursor-pointer text-ink">
                    <input
                      type="radio"
                      name="arm"
                      checked={selectedArm === 'TREATMENT'}
                      onChange={() => {
                        setSelectedArm('TREATMENT')
                        setPage(0)
                      }}
                      className="accent-accent"
                    />
                    <span>Treatment Only</span>
                  </label>
                  <label className="flex items-center gap-1.5 cursor-pointer text-ink">
                    <input
                      type="radio"
                      name="arm"
                      checked={selectedArm === 'HOLDOUT_CONTROL'}
                      onChange={() => {
                        setSelectedArm('HOLDOUT_CONTROL')
                        setPage(0)
                      }}
                      className="accent-accent"
                    />
                    <span>Holdout Control (10%)</span>
                  </label>
                </div>

                {hasActiveFilters && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={clearAllFilters}
                    className="text-xs text-failed hover:bg-failed/10 cursor-pointer h-7"
                  >
                    <X className="h-3 w-3 mr-1" />
                    Clear All Filters
                  </Button>
                )}
              </div>
            </div>
          )}
        </CardHeader>

        {/* Directory Table */}
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[180px]">Case / Payment ID</TableHead>
                <TableHead>Rail & Error</TableHead>
                <TableHead>Customer</TableHead>
                <TableHead className="text-right">At-Risk Amount</TableHead>
                <TableHead className="text-right">Net Recovered</TableHead>
                <TableHead>Lifecycle Stage</TableHead>
                <TableHead className="text-center">Touches</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? (
                Array.from({ length: 6 }).map((_, i) => (
                  <TableRow key={i}>
                    <TableCell colSpan={8} className="p-0">
                      <SkeletonRow />
                    </TableCell>
                  </TableRow>
                ))
              ) : cases.length === 0 ? (
                <TableRow>
                  <TableCell
                    colSpan={8}
                    className="h-32 text-center text-sm font-mono text-ink-muted"
                  >
                    No recovery cases matched the current search filters.
                  </TableCell>
                </TableRow>
              ) : (
                cases.map((c) => {
                  const isRecovered = c.state === 'RECOVERED'
                  const isEscalated = c.state === 'ESCALATED'
                  const isHoldout = c.experiment_arm === 'HOLDOUT_CONTROL'

                  return (
                    <TableRow
                      key={c.case_id}
                      onClick={() => {
                        onSelectCase(c)
                      }}
                      className="cursor-pointer hover:bg-surface-sunken/60 transition-colors"
                    >
                      {/* Case ID */}
                      <TableCell className="font-mono text-xs">
                        <div className="font-bold text-ink flex items-center gap-1.5">
                          <span>{c.case_id.slice(0, 8)}...</span>
                          {isHoldout && (
                            <Badge variant="outline" className="text-[9px] px-1 py-0 border-ink-muted text-ink-muted">
                              Holdout
                            </Badge>
                          )}
                        </div>
                        <div className="text-[11px] text-ink-subtle">
                          {c.failure_event.payment_id}
                        </div>
                      </TableCell>

                      {/* Rail & Reason */}
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <RailBadge rail={c.failure_event.payment_rail} />
                          <span className="font-mono text-xs text-ink font-semibold">
                            {c.failure_event.error_code}
                          </span>
                        </div>
                        <div className="text-[11px] text-ink-muted line-clamp-1 max-w-[200px]">
                          {c.failure_event.error_description || c.failure_event.error_reason}
                        </div>
                      </TableCell>

                      {/* Customer */}
                      <TableCell className="font-mono text-xs text-ink-muted">
                        {c.failure_event.customer_id}
                      </TableCell>

                      {/* Amount */}
                      <TableCell className="text-right font-mono text-xs font-semibold text-ink">
                        {formatINR(c.amount_paise)}
                      </TableCell>

                      {/* Net Recovered Value */}
                      <TableCell className="text-right font-mono text-xs">
                        {isRecovered ? (
                          <span className="font-bold text-recovered">
                            +{formatINR(c.net_recovered_value_paise || c.recovered_amount_paise)}
                          </span>
                        ) : (
                          <span className="text-ink-subtle">INR 0</span>
                        )}
                      </TableCell>

                      {/* Lifecycle Stage Badge */}
                      <TableCell>
                        <Badge variant={stateToVariant(c.state)} className="font-mono text-xs">
                          {c.state.replace('_', ' ')}
                        </Badge>
                      </TableCell>

                      {/* Touches */}
                      <TableCell className="text-center font-mono text-xs text-ink">
                        <span
                          className={
                            c.touches_count >= maxTouches
                              ? 'font-bold text-failed'
                              : 'text-ink-muted'
                          }
                        >
                          {c.touches_count} / {maxTouches}
                        </span>
                      </TableCell>

                      {/* Actions */}
                      <TableCell className="text-right">
                        {isEscalated ? (
                          <Button
                            size="sm"
                            variant="primary"
                            disabled={approvingId === c.case_id}
                            onClick={(e) => {
                              void handleApprove(e, c)
                            }}
                            className="bg-accent text-white hover:bg-accent/90 text-xs font-mono h-7 gap-1"
                          >
                            <UserCheck className="h-3 w-3" />
                            <span>{approvingId === c.case_id ? 'Approving...' : 'Sign Off'}</span>
                          </Button>
                        ) : isRecovered ? (
                          <span className="inline-flex items-center gap-1 text-[11px] font-mono text-recovered font-bold">
                            <CheckCircle2 className="h-3.5 w-3.5" />
                            Recovered
                          </span>
                        ) : (
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={(e) => {
                              e.stopPropagation()
                              onSelectCase(c)
                            }}
                            className="text-xs font-mono h-7 text-ink-muted hover:text-ink"
                          >
                            Details
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                  )
                })
              )}
            </TableBody>
          </Table>

          {/* Server-Side Pagination Bar */}
          <div className="flex items-center justify-between px-6 py-3 border-t border-border/40 bg-surface-sunken/40 text-xs font-mono text-ink-muted">
            <div className="flex items-center gap-2">
              <span>Rows per page:</span>
              <select
                value={pageSize}
                onChange={(e) => {
                  setPageSize(Number(e.target.value))
                  setPage(0)
                }}
                aria-label="Rows per page"
                className="bg-surface border border-border rounded-control px-2 py-0.5 text-xs text-ink cursor-pointer"
              >
                <option value={10}>10</option>
                <option value={25}>25</option>
                <option value={50}>50</option>
                <option value={100}>100</option>
              </select>
              <span className="ml-2">
                Showing {totalCount === 0 ? 0 : page * pageSize + 1} to{' '}
                {Math.min((page + 1) * pageSize, totalCount)} of {totalCount} total cases
              </span>
            </div>

            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page === 0 || loading}
                onClick={() => {
                  setPage((p) => Math.max(0, p - 1))
                }}
                className="h-7 px-3 text-xs font-mono cursor-pointer"
              >
                Previous
              </Button>
              <span>
                Page {totalPages === 0 ? 0 : page + 1} of {totalPages}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={page + 1 >= totalPages || loading}
                onClick={() => {
                  setPage((p) => p + 1)
                }}
                className="h-7 px-3 text-xs font-mono cursor-pointer"
              >
                Next
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
