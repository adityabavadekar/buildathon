import React from 'react'

export type BadgeVariant =
  | 'recovered'
  | 'pending'
  | 'failed'
  | 'escalated'
  | 'outline'
  | 'default'

interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant
}

export function Badge({
  variant = 'default',
  className = '',
  children,
  ...props
}: BadgeProps) {
  const variantStyles: Record<BadgeVariant, string> = {
    recovered:
      'bg-recovered-subtle text-recovered border-recovered/20',
    pending:
      'bg-pending-subtle text-pending border-pending/20',
    failed:
      'bg-failed-subtle text-failed border-failed/20',
    escalated:
      'bg-escalated-subtle text-escalated border-escalated/20',
    outline:
      'border-border text-ink bg-transparent',
    default:
      'bg-surface-sunken text-ink-muted border-border',
  }

  return (
    <span
      className={`inline-flex items-center rounded-control border px-2 py-0.5 text-[11px] font-mono font-medium tracking-tight ${variantStyles[variant]} ${className}`}
      {...props}
    >
      {children}
    </span>
  )
}
