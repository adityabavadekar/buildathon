'use client'

import React, { useEffect, useState } from 'react'
import {
  Activity,
  AlertOctagon,
  CheckCircle2,
  Clock,
  Layers,
  Pause,
  Play,
  Radio,
  RefreshCw,
  Send,
  Square,
  Zap,
} from 'lucide-react'
import {
  getFleetStatus,
  getPipelineHeatmap,
  getPipelineOverview,
  getPipelineTimeseries,
  getQueuedJobs,
  ingestSingleEvent,
  pauseFleetSimulation,
  resumeFleetSimulation,
  startFleetSimulation,
  stopFleetSimulation,
  type FleetStatusResponse,
  type PipelineHeatmapCell,
  type PipelineOverviewResponse,
  type PipelineTimeseriesPoint,
  type ScheduledJobItem,
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
import { StatCard } from '@/components/ui/StatCard'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { SkeletonCard, SkeletonRow } from '@/components/ui/skeleton'

export function PipelineView() {
  const [overview, setOverview] = useState<PipelineOverviewResponse | null>(
    null,
  )
  const [timeseries, setTimeseries] = useState<PipelineTimeseriesPoint[]>([])
  const [heatmap, setHeatmap] = useState<PipelineHeatmapCell[]>([])
  const [jobs, setJobs] = useState<ScheduledJobItem[]>([])
  const [fleet, setFleet] = useState<FleetStatusResponse | null>(null)
  const [loading, setLoading] = useState<boolean>(true)
  const [fleetLoading, setFleetLoading] = useState<boolean>(false)

  // Fleet controls state
  const [fleetRate, setFleetRate] = useState<number>(30)
  const [fleetUseLlm, setFleetUseLlm] = useState<boolean>(false)

  // Single event manual ingest form state
  const [manualAmount, setManualAmount] = useState<number>(49900)
  const [manualRail, setManualRail] = useState<string>('UPI')
  const [manualErrorCode, setManualErrorCode] = useState<string>('U30')
  const [ingesting, setIngesting] = useState<boolean>(false)

  const fetchData = async () => {
    try {
      const [ov, ts, hm, jb, fl] = await Promise.all([
        getPipelineOverview(),
        getPipelineTimeseries(60, 24),
        getPipelineHeatmap(),
        getQueuedJobs(30),
        getFleetStatus(),
      ])
      setOverview(ov)
      setTimeseries(ts)
      setHeatmap(hm)
      setJobs(jb)
      setFleet(fl)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void fetchData()
    const interval = setInterval(() => {
      void fetchData()
    }, 3000)
    return () => {
      clearInterval(interval)
    }
  }, [])

  const handleStartFleet = async () => {
    try {
      setFleetLoading(true)
      const res = await startFleetSimulation({
        events_per_minute: fleetRate,
        use_llm: fleetUseLlm,
      })
      setFleet(res)
    } finally {
      setFleetLoading(false)
    }
  }

  const handleStopFleet = async () => {
    try {
      setFleetLoading(true)
      const res = await stopFleetSimulation()
      setFleet(res)
    } finally {
      setFleetLoading(false)
    }
  }

  const handlePauseFleet = async () => {
    try {
      setFleetLoading(true)
      const res = await pauseFleetSimulation()
      setFleet(res)
    } finally {
      setFleetLoading(false)
    }
  }

  const handleResumeFleet = async () => {
    try {
      setFleetLoading(true)
      const res = await resumeFleetSimulation()
      setFleet(res)
    } finally {
      setFleetLoading(false)
    }
  }

  const handleManualIngest = async () => {
    try {
      setIngesting(true)
      await ingestSingleEvent({
        amount_paise: manualAmount,
        payment_rail: manualRail,
        error_code: manualErrorCode,
        error_description: `Manual test failure for ${manualRail} ${manualErrorCode}`,
      })
      void fetchData()
    } finally {
      setIngesting(false)
    }
  }

  const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

  if (loading && !overview) {
    return (
      <div className="space-y-6">
        <SkeletonCard />
        <SkeletonCard />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col justify-between gap-3 border-b border-border pb-4 sm:flex-row sm:items-center">
        <div>
          <div className="flex items-center gap-2">
            <Radio className="h-5 w-5 animate-pulse text-accent" />
            <h1 className="font-mono text-2xl font-bold text-ink">
              Data Pipeline & Ingestion Engine
            </h1>
          </div>
          <p className="mt-0.5 text-sm text-ink-muted">
            Durable FIFO queue, fast non-blocking 202 webhook ingestion, and
            background fleet generator.
          </p>
        </div>
        <div className="flex items-center gap-2 font-mono text-xs text-ink-muted">
          <Clock className="h-3.5 w-3.5" />
          <span>
            Oldest Queue Age:{' '}
            {overview
              ? `${overview.oldest_queued_age_seconds.toString()}s`
              : '0s'}
          </span>
        </div>
      </div>

      {/* Fleet Simulator Remote Control Panel */}
      <Card className="border-accent/40 bg-accent/5">
        <CardHeader className="p-5 pb-3">
          <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
            <div className="flex items-center gap-2.5">
              <Zap className="h-5 w-5 text-accent" />
              <div>
                <CardTitle className="font-mono text-base">
                  Continuous Fleet Failure Simulator
                </CardTitle>
                <CardDescription className="text-xs">
                  Backend-owned failure generator simulating live merchant
                  traffic across payment rails
                </CardDescription>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Badge
                variant={
                  fleet?.is_running
                    ? fleet.is_paused
                      ? 'pending'
                      : 'recovered'
                    : 'outline'
                }
                className="font-mono"
              >
                {fleet?.is_running
                  ? fleet.is_paused
                    ? 'PAUSED'
                    : 'GENERATING'
                  : 'STOPPED'}
              </Badge>
              <span className="font-mono text-xs font-bold text-ink">
                {fleet?.events_emitted.toString() || '0'} Events Emitted
              </span>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4 p-5 pt-0">
          <div className="flex flex-wrap items-center justify-between gap-4 border-t border-border/60 pt-2">
            <div className="flex flex-wrap items-center gap-4 font-mono text-xs">
              <div className="flex items-center gap-2">
                <span className="text-ink-muted">Rate:</span>
                <input
                  type="range"
                  min="5"
                  max="120"
                  step="5"
                  value={fleetRate}
                  onChange={(e) => {
                    setFleetRate(Number(e.target.value))
                  }}
                  disabled={fleet?.is_running}
                  className="w-28 cursor-pointer accent-accent"
                />
                <span className="w-14 font-bold text-ink">
                  {fleetRate.toString()} / min
                </span>
              </div>

              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="use_llm"
                  checked={fleetUseLlm}
                  onChange={(e) => {
                    setFleetUseLlm(e.target.checked)
                  }}
                  disabled={fleet?.is_running}
                  className="accent-accent"
                />
                <label htmlFor="use_llm" className="cursor-pointer text-ink">
                  Enable LLM Reasoning
                </label>
              </div>
            </div>

            {/* Action Buttons */}
            <div className="flex items-center gap-2">
              {!fleet?.is_running ? (
                <Button
                  size="sm"
                  onClick={() => {
                    void handleStartFleet()
                  }}
                  disabled={fleetLoading}
                  className="flex items-center gap-1.5 font-mono text-xs"
                >
                  <Play className="h-3.5 w-3.5" />
                  Start Fleet
                </Button>
              ) : (
                <>
                  {fleet.is_paused ? (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        void handleResumeFleet()
                      }}
                      disabled={fleetLoading}
                      className="flex items-center gap-1.5 font-mono text-xs"
                    >
                      <Play className="h-3.5 w-3.5" />
                      Resume
                    </Button>
                  ) : (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        void handlePauseFleet()
                      }}
                      disabled={fleetLoading}
                      className="flex items-center gap-1.5 font-mono text-xs"
                    >
                      <Pause className="h-3.5 w-3.5" />
                      Pause
                    </Button>
                  )}
                  <Button
                    size="sm"
                    variant="danger"
                    onClick={() => {
                      void handleStopFleet()
                    }}
                    disabled={fleetLoading}
                    className="flex items-center gap-1.5 font-mono text-xs"
                  >
                    <Square className="h-3.5 w-3.5" />
                    Stop
                  </Button>
                </>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* 5 Observable Queue State Cards */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <StatCard
          title="Queued Inbox"
          value={(overview?.counts.QUEUED_DUE_NOW ?? 0).toString()}
          subtitle={`Due now (${(overview?.counts.QUEUED_FUTURE ?? 0).toString()} future-scheduled)`}
          icon={<Layers className="h-4 w-4 text-accent" />}
          variant="default"
        />

        <StatCard
          title="Processing"
          value={(overview?.counts.PROCESSING ?? 0).toString()}
          subtitle="Active in worker pipeline"
          icon={<RefreshCw className="h-4 w-4 animate-spin text-accent" />}
          variant="default"
        />

        <StatCard
          title="Done (Resolved)"
          value={(overview?.counts.DONE ?? 0).toString()}
          subtitle="Committed in single transaction"
          icon={<CheckCircle2 className="h-4 w-4 text-recovered" />}
          variant="recovered"
        />

        <StatCard
          title="Retrying (Failed)"
          value={(overview?.counts.FAILED ?? 0).toString()}
          subtitle="Exponential backoff active"
          icon={<Activity className="h-4 w-4 text-pending" />}
          variant="escalated"
        />

        <StatCard
          title="Dead Letter"
          value={(overview?.counts.DEAD ?? 0).toString()}
          subtitle="Exceeded retry bound"
          icon={<AlertOctagon className="h-4 w-4 text-failed" />}
          variant={overview && overview.counts.DEAD > 0 ? 'failed' : 'default'}
        />
      </div>

      {/* Timeseries & Heatmap Grid */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Timeseries Chart Summary */}
        <Card className="lg:col-span-2">
          <CardHeader className="p-5 pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="font-mono text-sm">
                Ingestion & Processing Velocity (24h)
              </CardTitle>
              <Badge variant="outline" className="font-mono text-[10px]">
                {overview
                  ? `${overview.events_processed_last_minute.toString()} evt/min`
                  : '0/min'}
              </Badge>
            </div>
            <CardDescription className="text-xs">
              Hourly comparison of total events ingested into durable queue vs.
              fully processed jobs
            </CardDescription>
          </CardHeader>
          <CardContent className="p-5 pt-2">
            <div className="flex h-48 items-end gap-1 border-b border-l border-border pt-4 pb-1 pl-2">
              {timeseries.slice(-24).map((pt, idx) => {
                const maxVal = Math.max(
                  1,
                  ...timeseries.map((t) => Math.max(t.ingested, t.processed)),
                )
                const ingestedHeight = Math.min(
                  100,
                  (pt.ingested / maxVal) * 100,
                )
                const processedHeight = Math.min(
                  100,
                  (pt.processed / maxVal) * 100,
                )
                return (
                  <div
                    key={idx}
                    className="group relative flex flex-1 flex-col items-center gap-0.5"
                  >
                    <div className="flex h-36 w-full items-end justify-center gap-0.5">
                      <div
                        style={{ height: `${ingestedHeight.toString()}%` }}
                        className="w-1.5 rounded-t-xs bg-accent/60 transition-all group-hover:bg-accent"
                        title={`Ingested: ${pt.ingested.toString()}`}
                      />
                      <div
                        style={{ height: `${processedHeight.toString()}%` }}
                        className="w-1.5 rounded-t-xs bg-recovered/60 transition-all group-hover:bg-recovered"
                        title={`Processed: ${pt.processed.toString()}`}
                      />
                    </div>
                    <span className="hidden font-mono text-[9px] text-ink-subtle sm:block">
                      {new Date(pt.timestamp).getHours().toString()}h
                    </span>
                  </div>
                )
              })}
            </div>
            <div className="mt-3 flex items-center justify-end gap-4 font-mono text-[11px]">
              <div className="flex items-center gap-1.5">
                <div className="h-2 w-2 rounded-xs bg-accent" />
                <span className="text-ink-muted">Ingested</span>
              </div>
              <div className="flex items-center gap-1.5">
                <div className="h-2 w-2 rounded-xs bg-recovered" />
                <span className="text-ink-muted">Processed (Done)</span>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* 7x24 Flood Heatmap */}
        <Card>
          <CardHeader className="p-5 pb-2">
            <CardTitle className="font-mono text-sm">
              Flood & Peak Traffic (7x24)
            </CardTitle>
            <CardDescription className="text-xs">
              Weekly distribution identifying systemic peak windows
            </CardDescription>
          </CardHeader>
          <CardContent className="p-5 pt-2">
            <div className="space-y-1">
              {days.map((dayName, dIdx) => (
                <div key={dayName} className="flex items-center gap-1">
                  <span className="w-7 font-mono text-[10px] text-ink-muted">
                    {dayName}
                  </span>
                  <div className="grid flex-1 grid-cols-24 gap-0.5">
                    {Array.from({ length: 24 }).map((_, hIdx) => {
                      const cell = heatmap.find(
                        (c) => c.day === dIdx && c.hour === hIdx,
                      )
                      const count = cell ? cell.count : 0
                      const bg =
                        count > 20
                          ? 'bg-failed'
                          : count > 10
                            ? 'bg-pending'
                            : count > 0
                              ? 'bg-accent/40'
                              : 'bg-surface-sunken'
                      return (
                        <div
                          key={hIdx}
                          className={`h-3 rounded-xs ${bg}`}
                          title={`${dayName} ${hIdx.toString()}:00 - ${count.toString()} events`}
                        />
                      )
                    })}
                  </div>
                </div>
              ))}
            </div>
            <div className="mt-3 flex items-center justify-between font-mono text-[10px] text-ink-subtle">
              <span>0h (Midnight)</span>
              <span>12h (Noon)</span>
              <span>23h (Night)</span>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Single Event Ingest Modal / Quick Trigger */}
      <Card>
        <CardHeader className="border-b border-border p-5 pb-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Send className="h-4 w-4 text-accent" />
              <CardTitle className="font-mono text-sm">
                Manual Single Event Ingress (202 Enqueue Test)
              </CardTitle>
            </div>
            <Badge variant="outline" className="font-mono text-[10px]">
              NON-BLOCKING 202
            </Badge>
          </div>
          <CardDescription className="text-xs">
            Push an individual transaction failure directly into the durable
            FIFO queue without blocking the HTTP request
          </CardDescription>
        </CardHeader>
        <CardContent className="p-5">
          <div className="flex flex-wrap items-center gap-3 font-mono text-xs">
            <div className="flex items-center gap-2">
              <span className="text-ink-muted">Amount (Paise):</span>
              <input
                type="number"
                value={manualAmount}
                onChange={(e) => {
                  setManualAmount(Number(e.target.value))
                }}
                className="w-28 rounded-control border border-border bg-surface px-2.5 py-1 text-xs text-ink"
              />
            </div>

            <div className="flex items-center gap-2">
              <span className="text-ink-muted">Rail:</span>
              <select
                value={manualRail}
                onChange={(e) => {
                  setManualRail(e.target.value)
                }}
                className="rounded-control border border-border bg-surface px-2.5 py-1 text-xs text-ink"
              >
                <option value="UPI">UPI</option>
                <option value="CARD">CARD</option>
                <option value="ENACH">eNACH / Mandate</option>
                <option value="NETBANKING">NetBanking</option>
                <option value="B2B_INVOICE">B2B Invoice</option>
              </select>
            </div>

            <div className="flex items-center gap-2">
              <span className="text-ink-muted">Error Code:</span>
              <input
                type="text"
                value={manualErrorCode}
                onChange={(e) => {
                  setManualErrorCode(e.target.value)
                }}
                className="w-24 rounded-control border border-border bg-surface px-2.5 py-1 text-xs text-ink"
              />
            </div>

            <Button
              size="sm"
              onClick={() => {
                void handleManualIngest()
              }}
              disabled={ingesting}
              className="ml-auto flex items-center gap-1.5 font-mono text-xs"
            >
              <Send className="h-3.5 w-3.5" />
              {ingesting ? 'Enqueueing...' : 'Enqueue 202 Event'}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Observable Queued Jobs Table */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between border-b border-border p-5">
          <div>
            <CardTitle>Durable Queue Registry</CardTitle>
            <CardDescription className="mt-0.5 text-xs">
              Live inspection of FIFO task state, attempts, idempotency keys,
              and scheduled execution times
            </CardDescription>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              void fetchData()
            }}
            className="flex items-center gap-1.5 font-mono text-xs"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Refresh Queue
          </Button>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Job ID</TableHead>
                <TableHead>Case ID</TableHead>
                <TableHead>Job Type</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Attempts</TableHead>
                <TableHead>Due At</TableHead>
                <TableHead className="text-right">Idempotency Key</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? (
                <>
                  <SkeletonRow variant="table" />
                  <SkeletonRow variant="table" />
                  <SkeletonRow variant="table" />
                </>
              ) : jobs.length === 0 ? (
                <TableRow>
                  <TableCell
                    colSpan={7}
                    className="h-24 text-center font-mono text-xs text-ink-muted"
                  >
                    No active or recent jobs found in the queue.
                  </TableCell>
                </TableRow>
              ) : (
                jobs.map((j) => (
                  <TableRow key={j.job_id} className="font-mono text-xs">
                    <TableCell className="font-semibold text-ink">
                      {j.job_id.slice(0, 12)}...
                    </TableCell>
                    <TableCell className="text-accent">{j.case_id}</TableCell>
                    <TableCell>{j.job_type}</TableCell>
                    <TableCell>
                      <Badge
                        variant={
                          j.status === 'DONE'
                            ? 'recovered'
                            : j.status === 'PROCESSING'
                              ? 'default'
                              : j.status === 'FAILED'
                                ? 'pending'
                                : j.status === 'DEAD'
                                  ? 'failed'
                                  : 'outline'
                        }
                        className="text-[10px]"
                      >
                        {j.status}
                      </Badge>
                    </TableCell>
                    <TableCell>{j.attempts.toString()}</TableCell>
                    <TableCell className="text-ink-muted">
                      {new Date(j.due_at).toLocaleTimeString()}
                    </TableCell>
                    <TableCell className="text-right text-[11px] text-ink-subtle">
                      {j.idempotency_key}
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}
