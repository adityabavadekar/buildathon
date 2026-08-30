'use client'

import React from 'react'
import { Clock } from 'lucide-react'
import type { TTRBucket } from '@/lib/api'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'

interface LatencyDistributionChartProps {
  ttrBuckets: TTRBucket[]
}

export function LatencyDistributionChart({ ttrBuckets }: LatencyDistributionChartProps) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Clock className="h-4 w-4 text-accent" />
          <CardTitle>Time-to-Recovery (TTR) Latency</CardTitle>
        </div>
        <CardDescription>
          Distribution of resolution speed across instant drop-off links and banking cooldown windows
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 font-mono text-xs">
        {ttrBuckets.length === 0 ? (
          <div className="py-8 text-center text-ink-muted">
            No resolution latency telemetry available.
          </div>
        ) : (
          ttrBuckets.map((bucket) => (
            <div key={bucket.bucket} className="space-y-1">
              <div className="flex justify-between">
                <span className="text-ink">{bucket.bucket}</span>
                <span className="text-ink-muted font-semibold">
                  {bucket.percentage.toFixed(0)}% ({bucket.count.toString()} cases)
                </span>
              </div>
              <div className="h-2 w-full rounded-full bg-surface-sunken overflow-hidden">
                <div
                  className="h-full bg-accent transition-all duration-500"
                  style={{ width: `${Math.min(100, bucket.percentage).toString()}%` }}
                />
              </div>
            </div>
          ))
        )}
      </CardContent>
    </Card>
  )
}
