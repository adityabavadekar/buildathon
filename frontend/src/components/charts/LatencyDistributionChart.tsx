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
import { HistogramChart } from '@/components/charts/HistogramChart'

interface LatencyDistributionChartProps {
  ttrBuckets: TTRBucket[]
}

export function LatencyDistributionChart({
  ttrBuckets,
}: LatencyDistributionChartProps) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Clock className="h-4 w-4 text-accent" />
          <CardTitle>Time-to-Recovery (TTR) Latency</CardTitle>
        </div>
        <CardDescription>
          Distribution of resolution speed across instant drop-off links and
          banking cooldown windows
        </CardDescription>
      </CardHeader>
      <CardContent>
        <HistogramChart
          bars={ttrBuckets.map((bucket) => ({
            key: bucket.bucket,
            label: bucket.bucket,
            value: bucket.count,
            detail: `${bucket.percentage.toFixed(1)}% of resolved cases`,
          }))}
          valueSuffix=" cases"
          valueLabel="Cases by time to recovery"
          emptyMessage="No resolution latency telemetry available."
        />
      </CardContent>
    </Card>
  )
}
