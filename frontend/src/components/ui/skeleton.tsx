import React from 'react'

export function Skeleton({
  className = '',
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={`animate-pulse rounded-control bg-surface-sunken ${className}`}
      aria-hidden="true"
      {...props}
    />
  )
}

export function SkeletonCard() {
  return (
    <div className="rounded-panel border border-border bg-surface p-4 shadow-xs">
      <Skeleton className="mb-2 h-3.5 w-24" />
      <Skeleton className="mb-2 h-7 w-36" />
      <Skeleton className="h-3 w-48" />
    </div>
  )
}

export function SkeletonRow() {
  return (
    <div className="flex items-center justify-between border-b border-border/50 py-3.5 px-4">
      <div className="flex items-center gap-3">
        <Skeleton className="h-4 w-28" />
        <Skeleton className="h-3.5 w-36" />
      </div>
      <div className="flex items-center gap-4">
        <Skeleton className="h-4 w-16" />
        <Skeleton className="h-5 w-20 rounded-full" />
      </div>
    </div>
  )
}
