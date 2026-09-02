'use client'

import React, { useId } from 'react'

const ARC_START_DEG = 135
const ARC_SWEEP_DEG = 270
const VIEWBOX = 120
const CENTER = VIEWBOX / 2
const RADIUS = 46
const TRACK_WIDTH = 10

export type GaugeTone = 'accent' | 'recovered' | 'pending' | 'failed'

interface GaugeMeterProps {
  label: string
  /** Fraction of `max`, clamped to the track. */
  value: number
  max?: number
  hint?: string
  /** Fractions below which the fill turns warning / critical. */
  warnBelow?: number
  criticalBelow?: number
  displayValue?: string
}

function polarPoint(fraction: number): { x: number; y: number } {
  const angle = ((ARC_START_DEG + fraction * ARC_SWEEP_DEG) * Math.PI) / 180
  return {
    x: CENTER + RADIUS * Math.cos(angle),
    y: CENTER + RADIUS * Math.sin(angle),
  }
}

function arcPath(fromFraction: number, toFraction: number): string {
  const start = polarPoint(fromFraction)
  const end = polarPoint(toFraction)
  const largeArc = (toFraction - fromFraction) * ARC_SWEEP_DEG > 180 ? 1 : 0
  return `M ${start.x.toFixed(2)} ${start.y.toFixed(2)} A ${RADIUS.toString()} ${RADIUS.toString()} 0 ${largeArc.toString()} 1 ${end.x.toFixed(2)} ${end.y.toFixed(2)}`
}

function toneFor(
  fraction: number,
  warnBelow: number,
  criticalBelow: number,
): GaugeTone {
  if (fraction < criticalBelow) {
    return 'failed'
  }
  if (fraction < warnBelow) {
    return 'pending'
  }
  return 'recovered'
}

const TONE_STROKE: Record<GaugeTone, string> = {
  accent: 'var(--color-accent)',
  recovered: 'var(--color-recovered)',
  pending: 'var(--color-pending)',
  failed: 'var(--color-failed)',
}

const TONE_TRACK: Record<GaugeTone, string> = {
  accent: 'var(--color-accent-subtle)',
  recovered: 'var(--color-recovered-subtle)',
  pending: 'var(--color-pending-subtle)',
  failed: 'var(--color-failed-subtle)',
}

export function GaugeMeter({
  label,
  value,
  max = 1,
  hint,
  warnBelow = 0.7,
  criticalBelow = 0.5,
  displayValue,
}: GaugeMeterProps) {
  const titleId = useId()
  const fraction = max > 0 ? Math.max(0, Math.min(1, value / max)) : 0
  const tone = toneFor(fraction, warnBelow, criticalBelow)
  const readout = displayValue ?? `${(fraction * 100).toFixed(1)}%`

  return (
    <figure className="flex flex-col items-center gap-1">
      <svg
        viewBox={`0 0 ${VIEWBOX.toString()} ${VIEWBOX.toString()}`}
        className="h-[7.5rem] w-[7.5rem]"
        role="img"
        aria-labelledby={titleId}
      >
        <title id={titleId}>{`${label}: ${readout}`}</title>
        <path
          d={arcPath(0, 1)}
          fill="none"
          stroke={TONE_TRACK[tone]}
          strokeWidth={TRACK_WIDTH}
          strokeLinecap="round"
        />
        {fraction > 0 && (
          <path
            d={arcPath(0, fraction)}
            fill="none"
            stroke={TONE_STROKE[tone]}
            strokeWidth={TRACK_WIDTH}
            strokeLinecap="round"
          />
        )}
        <text
          x={CENTER}
          y={CENTER + 2}
          textAnchor="middle"
          className="fill-ink text-[1.15rem] font-semibold"
        >
          {readout}
        </text>
        <text
          x={CENTER}
          y={CENTER + 18}
          textAnchor="middle"
          className="fill-ink-subtle text-[0.5rem] tracking-wide uppercase"
        >
          {max === 1 ? 'of 100%' : `of ${max.toString()}`}
        </text>
      </svg>
      <figcaption className="text-center">
        <span className="block text-xs font-medium text-ink">{label}</span>
        {hint !== undefined && (
          <span className="mt-0.5 block max-w-[14rem] text-[11px] text-ink-subtle">
            {hint}
          </span>
        )}
      </figcaption>
    </figure>
  )
}
