'use client'

import React, { useId, useState } from 'react'

const PLOT_WIDTH = 520
const PLOT_HEIGHT = 132
const MARGIN = { top: 18, right: 60, bottom: 30, left: 104 }
const INNER_WIDTH = PLOT_WIDTH - MARGIN.left - MARGIN.right
const ROW_HEIGHT = 34
const MARKER_RADIUS = 7
const CONNECTOR_WIDTH = 2
const GRID_STEPS = 4

export interface ArmRow {
  key: string
  label: string
  /** Recovery rate as a percentage, 0-100. */
  ratePct: number
  caseCount: number
  color: string
  sublabel: string
}

interface ArmComparisonChartProps {
  arms: ArmRow[]
  liftPct: number
}

function niceCeiling(maxPct: number): number {
  if (maxPct <= 0) {
    return 100
  }
  return Math.min(100, Math.ceil(maxPct / 20) * 20 + 20)
}

export function ArmComparisonChart({ arms, liftPct }: ArmComparisonChartProps) {
  const [active, setActive] = useState<string | null>(null)
  const titleId = useId()

  if (arms.length === 0) {
    return (
      <p className="py-6 text-center text-xs text-ink-muted">
        No experiment arms recorded yet.
      </p>
    )
  }

  const ceiling = niceCeiling(Math.max(...arms.map((a) => a.ratePct)))
  const xFor = (pct: number): number =>
    MARGIN.left + (Math.max(0, Math.min(ceiling, pct)) / ceiling) * INNER_WIDTH
  const yFor = (index: number): number => MARGIN.top + index * ROW_HEIGHT + 8

  const treatment = arms.at(0)
  const holdout = arms.at(-1)
  const showConnector =
    arms.length === 2 && treatment !== undefined && holdout !== undefined

  return (
    <div className="space-y-2">
      <svg
        viewBox={`0 0 ${PLOT_WIDTH.toString()} ${PLOT_HEIGHT.toString()}`}
        className="w-full"
        role="img"
        aria-labelledby={titleId}
      >
        <title id={titleId}>
          {`Recovery rate by experiment arm; lift ${liftPct.toFixed(1)} percentage points`}
        </title>

        {Array.from({ length: GRID_STEPS + 1 }, (_, i) => {
          const pct = (ceiling / GRID_STEPS) * i
          const x = xFor(pct)
          return (
            <g key={`grid-${i.toString()}`}>
              <line
                x1={x}
                x2={x}
                y1={MARGIN.top - 6}
                y2={PLOT_HEIGHT - MARGIN.bottom}
                stroke="var(--color-border)"
                strokeWidth={1}
              />
              <text
                x={x}
                y={PLOT_HEIGHT - MARGIN.bottom + 14}
                textAnchor="middle"
                className="fill-ink-subtle text-[0.5625rem] [font-variant-numeric:tabular-nums]"
              >
                {pct.toFixed(0)}%
              </text>
            </g>
          )
        })}

        {/* The connector makes the gap between the arms the visible subject. */}
        {showConnector && (
          <line
            x1={xFor(holdout.ratePct)}
            x2={xFor(treatment.ratePct)}
            y1={yFor(0) + ROW_HEIGHT / 2}
            y2={yFor(0) + ROW_HEIGHT / 2}
            stroke="var(--color-border-strong)"
            strokeWidth={CONNECTOR_WIDTH}
            strokeLinecap="round"
          />
        )}

        {arms.map((arm, index) => {
          const cy = showConnector
            ? yFor(0) + ROW_HEIGHT / 2
            : yFor(index) + ROW_HEIGHT / 2
          const cx = xFor(arm.ratePct)
          const isActive = active === arm.key
          return (
            <g
              key={arm.key}
              onMouseEnter={() => {
                setActive(arm.key)
              }}
              onMouseLeave={() => {
                setActive(null)
              }}
            >
              <circle
                cx={cx}
                cy={cy}
                r={MARKER_RADIUS + 8}
                fill="transparent"
              />
              <circle
                cx={cx}
                cy={cy}
                r={isActive ? MARKER_RADIUS + 1.5 : MARKER_RADIUS}
                fill={arm.color}
                stroke="var(--color-surface)"
                strokeWidth={2}
              />
              <text
                x={cx}
                y={cy - MARKER_RADIUS - 6}
                textAnchor="middle"
                className="fill-ink text-[0.625rem] font-semibold [font-variant-numeric:tabular-nums]"
              >
                {arm.ratePct.toFixed(1)}%
              </text>
            </g>
          )
        })}

        {arms.map((arm, index) => (
          <text
            key={`label-${arm.key}`}
            x={MARGIN.left - 12}
            y={
              (showConnector
                ? yFor(0) + ROW_HEIGHT / 2
                : yFor(index) + ROW_HEIGHT / 2) + 3
            }
            textAnchor="end"
            className="fill-ink-muted text-[0.625rem]"
          >
            {showConnector && index > 0 ? '' : arm.label}
          </text>
        ))}
      </svg>

      <ul className="grid gap-2 text-xs sm:grid-cols-2">
        {arms.map((arm) => (
          <li
            key={arm.key}
            className={`flex items-start gap-2 rounded-control border p-2 ${
              active === arm.key ? 'border-border-strong' : 'border-border'
            }`}
            onMouseEnter={() => {
              setActive(arm.key)
            }}
            onMouseLeave={() => {
              setActive(null)
            }}
          >
            <span
              aria-hidden="true"
              className="mt-1 h-2.5 w-2.5 shrink-0 rounded-full"
              style={{ backgroundColor: arm.color }}
            />
            <span className="min-w-0">
              <span className="block text-ink">{arm.label}</span>
              <span className="block font-mono font-semibold text-ink">
                {arm.ratePct.toFixed(1)}%
                <span className="ml-1 font-normal text-ink-subtle">
                  {arm.caseCount.toString()} cases
                </span>
              </span>
              <span className="block text-[11px] text-ink-subtle">
                {arm.sublabel}
              </span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}
