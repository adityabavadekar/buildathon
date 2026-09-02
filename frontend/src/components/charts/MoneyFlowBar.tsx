'use client'

import React, { useId, useState } from 'react'
import { formatINR } from '@/lib/format'

const BAR_HEIGHT = 34
const SEGMENT_GAP = 2
const TRACK_WIDTH = 100

export interface MoneySegment {
  key: string
  label: string
  amountPaise: number
  color: string
}

interface MoneyFlowBarProps {
  segments: MoneySegment[]
  totalPaise: number
  remainderLabel?: string
}

export function MoneyFlowBar({
  segments,
  totalPaise,
  remainderLabel = 'Still at risk',
}: MoneyFlowBarProps) {
  const [active, setActive] = useState<string | null>(null)
  const titleId = useId()

  const accounted = segments.reduce((sum, s) => sum + s.amountPaise, 0)
  const remainder = Math.max(0, totalPaise - accounted)
  const rows: MoneySegment[] =
    remainder > 0
      ? [
          ...segments,
          {
            key: 'remainder',
            label: remainderLabel,
            amountPaise: remainder,
            color: 'var(--color-border-strong)',
          },
        ]
      : segments

  if (totalPaise <= 0) {
    return (
      <p className="py-6 text-center text-xs text-ink-muted">
        No at-risk revenue recorded for this batch yet.
      </p>
    )
  }

  const placed = rows.reduce<{ row: MoneySegment; x: number; width: number }[]>(
    (acc, row) => {
      const previous = acc.at(-1)
      const x = previous ? previous.x + previous.width + SEGMENT_GAP : 0
      const share = (row.amountPaise / totalPaise) * TRACK_WIDTH
      acc.push({ row, x, width: Math.max(0, share - SEGMENT_GAP) })
      return acc
    },
    [],
  )

  return (
    <div className="space-y-3">
      <svg
        viewBox={`0 0 ${TRACK_WIDTH.toString()} ${BAR_HEIGHT.toString()}`}
        preserveAspectRatio="none"
        className="h-[2.125rem] w-full"
        role="img"
        aria-labelledby={titleId}
      >
        <title id={titleId}>
          {`Breakdown of ${formatINR(totalPaise)} at-risk revenue`}
        </title>
        {placed.map(({ row, x, width }) => {
          if (width <= 0) {
            return null
          }
          return (
            <rect
              key={row.key}
              x={x}
              y={0}
              width={width}
              height={BAR_HEIGHT}
              rx={1}
              fill={row.color}
              opacity={active === null || active === row.key ? 1 : 0.45}
              onMouseEnter={() => {
                setActive(row.key)
              }}
              onMouseLeave={() => {
                setActive(null)
              }}
            />
          )
        })}
      </svg>

      <ul className="grid gap-2 text-xs sm:grid-cols-2 lg:grid-cols-4">
        {rows.map((row) => {
          const pct = (row.amountPaise / totalPaise) * 100
          return (
            <li
              key={row.key}
              className={`flex items-center gap-2 rounded-control border p-2 transition-colors ${
                active === row.key ? 'border-border-strong' : 'border-border'
              }`}
              onMouseEnter={() => {
                setActive(row.key)
              }}
              onMouseLeave={() => {
                setActive(null)
              }}
            >
              <span
                aria-hidden="true"
                className="h-2.5 w-2.5 shrink-0 rounded-full"
                style={{ backgroundColor: row.color }}
              />
              <span className="min-w-0">
                <span className="block truncate text-ink-muted">
                  {row.label}
                </span>
                <span className="block money font-semibold text-ink">
                  {formatINR(row.amountPaise)}
                  <span className="ml-1 font-normal text-ink-subtle">
                    {pct.toFixed(1)}%
                  </span>
                </span>
              </span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
