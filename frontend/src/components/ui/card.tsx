import React from 'react'

export function Card({
  className = '',
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={`rounded-panel border border-border bg-surface text-ink shadow-xs ${className}`}
      {...props}
    />
  )
}

export function CardHeader({
  className = '',
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={`flex flex-col space-y-1.5 p-4 sm:p-5 border-b border-border ${className}`}
      {...props}
    />
  )
}

export function CardTitle({
  className = '',
  ...props
}: React.HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h3
      className={`text-sm font-semibold tracking-tight text-ink ${className}`}
      {...props}
    />
  )
}

export function CardDescription({
  className = '',
  ...props
}: React.HTMLAttributes<HTMLParagraphElement>) {
  return (
    <p className={`text-xs text-ink-muted ${className}`} {...props} />
  )
}

export function CardContent({
  className = '',
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={`p-4 sm:p-5 ${className}`} {...props} />
}

export function CardFooter({
  className = '',
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={`flex items-center p-4 sm:p-5 pt-0 border-t border-border mt-4 ${className}`}
      {...props}
    />
  )
}
