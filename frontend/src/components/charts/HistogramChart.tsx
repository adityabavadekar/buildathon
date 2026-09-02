'use client'

import React, { useId, useState } from 'react'

const PLOT_WIDTH = 560
const PLOT_HEIGHT = 200
const MARGIN = { top: 12, right: 12, bottom: 44, left: 44 }
const INNER_WIDTH = PLOT_WIDTH - MARGIN.left - MARGIN.right
const INNER_HEIGHT = PLOT_HEIGHT - MARGIN.top - MARGIN.bottom
const BAR_GAP = 2
const GRID_LINES = 4
const BAR_RADIUS = 4

export interface HistogramBar {
  key: string
  label: string
  value: number
  detail?: string
}

interface HistogramChartProps {
  bars: HistogramBar[]
  valueSuffix?: string
  emptyMessage?: string
  valueLabel?: string
}

function niceCeiling(maxValue: number): number {
  if (maxValue <= 0) {
    return 1
  }
  const magnitude = 10 ** Math.floor(Math.log10(maxValue))
  return Math.ceil(maxValue / magnitude) * magnitude
}

export function HistogramChart({
  bars,
  valueSuffix = '',
  emptyMessage = 'No data available.',
  valueLabel,
}: HistogramChartProps) {
  const [active, setActive] = useState<string | null>(null)
  const titleId = useId()

  if (bars.length === 0) {
    return (
      <p className="py-8 text-center text-xs text-ink-muted">{emptyMessage}</p>
    )
  }

  const ceiling = niceCeiling(Math.max(...bars.map((b) => b.value)))
  const bandWidth = INNER_WIDTH / bars.length
  const barWidth = Math.max(4, bandWidth - BAR_GAP * 2)
  const activeBar = bars.find((b) => b.key === active) ?? null

  return (
    <div className="relative">
      <svg
        viewBox={`0 0 ${PLOT_WIDTH.toString()} ${PLOT_HEIGHT.toString()}`}
        className="w-full"
        role="img"
        aria-labelledby={titleId}
      >
        <title id={titleId}>
          {valueLabel ?? 'Distribution'} across {bars.length.toString()} buckets
        </title>

        {Array.from({ length: GRID_LINES + 1 }, (_, i) => {
          const fraction = i / GRID_LINES
          const y = MARGIN.top + INNER_HEIGHT * (1 - fraction)
          return (
            <g key={`grid-${i.toString()}`}>
              <line
                x1={MARGIN.left}
                x2={MARGIN.left + INNER_WIDTH}
                y1={y}
                y2={y}
                stroke="var(--color-border)"
                strokeWidth={1}
              />
              <text
                x={MARGIN.left - 8}
                y={y + 3}
                textAnchor="end"
                className="fill-ink-subtle text-[0.5625rem] [font-variant-numeric:tabular-nums]"
              >
                {Math.round(ceiling * fraction).toString()}
              </text>
            </g>
          )
        })}

        {bars.map((bar, index) => {
          const height = ceiling > 0 ? (bar.value / ceiling) * INNER_HEIGHT : 0
          const x = MARGIN.left + index * bandWidth + BAR_GAP
          const y = MARGIN.top + INNER_HEIGHT - height
          const isActive = active === bar.key
          return (
            <g key={bar.key}>
              {/* Full-height hit target so the hover works on short bars too. */}
              <rect
                x={MARGIN.left + index * bandWidth}
                y={MARGIN.top}
                width={bandWidth}
                height={INNER_HEIGHT}
                fill="transparent"
                onMouseEnter={() => {
                  setActive(bar.key)
                }}
                onMouseLeave={() => {
                  setActive(null)
                }}
              />
              {height > 0 && (
                <rect
                  x={x}
                  y={y}
                  width={barWidth}
                  height={height}
                  rx={BAR_RADIUS}
                  fill="var(--color-accent)"
                  opacity={isActive || active === null ? 1 : 0.45}
                  pointerEvents="none"
                />
              )}
              <text
                x={MARGIN.left + index * bandWidth + bandWidth / 2}
                y={PLOT_HEIGHT - MARGIN.bottom + 16}
                textAnchor="middle"
                className="fill-ink-muted text-[0.5625rem]"
                pointerEvents="none"
              >
                {bar.label}
              </text>
            </g>
          )
        })}

        <line
          x1={MARGIN.left}
          x2={MARGIN.left + INNER_WIDTH}
          y1={MARGIN.top + INNER_HEIGHT}
          y2={MARGIN.top + INNER_HEIGHT}
          stroke="var(--color-border-strong)"
          strokeWidth={1}
        />
      </svg>

      {activeBar !== null && (
        <div
          role="status"
          className="pointer-events-none absolute top-2 right-2 rounded-control border border-border bg-surface px-2.5 py-1.5 text-[11px] shadow-sm"
        >
          <span className="block font-medium text-ink">{activeBar.label}</span>
          <span className="block font-mono text-ink-muted">
            {activeBar.value.toString()}
            {valueSuffix}
            {activeBar.detail !== undefined ? ` · ${activeBar.detail}` : ''}
          </span>
        </div>
      )}
    </div>
  )
}
