'use client'

import React, { ReactNode } from 'react'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'

interface StatCardProps {
  title: ReactNode
  value: ReactNode
  subtitle?: ReactNode
  icon?: ReactNode
  variant?: 'default' | 'recovered' | 'escalated' | 'failed' | 'accent'
  className?: string
}

export function StatCard({
  title,
  value,
  subtitle,
  icon,
  variant = 'default',
  className = '',
}: StatCardProps) {
  const variantStyles = {
    default: 'hover:border-border-strong',
    recovered: 'border-recovered/30 bg-recovered/5 hover:border-recovered/60',
    escalated:
      'border-escalated/50 bg-escalated-subtle/20 hover:border-escalated/70',
    failed: 'border-failed/30 bg-failed/5 hover:border-failed/60',
    accent: 'border-accent/30 bg-accent/5 hover:border-accent/60',
  }

  const textStyles = {
    default: 'text-ink',
    recovered: 'text-recovered',
    escalated: 'text-escalated',
    failed: 'text-failed',
    accent: 'text-accent',
  }

  return (
    <Card
      className={`${variantStyles[variant]} transition-colors ${className}`}
    >
      <CardHeader className="border-none p-5 pb-2">
        <div className="flex items-center justify-between">
          <CardDescription className="text-sm font-semibold text-ink">
            {title}
          </CardDescription>
          {icon && (
            <div className="rounded-control bg-surface-sunken p-2">{icon}</div>
          )}
        </div>
        <CardTitle
          className={`mt-1 font-mono text-3xl font-bold tracking-tight tabular-nums sm:text-4xl ${textStyles[variant]}`}
        >
          {value}
        </CardTitle>
      </CardHeader>
      {subtitle && (
        <CardContent className="p-5 pt-0 text-xs leading-relaxed text-ink-muted sm:text-sm">
          {subtitle}
        </CardContent>
      )}
    </Card>
  )
}
