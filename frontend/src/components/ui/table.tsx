import React from 'react'

export function Table({
  className = '',
  ...props
}: React.HTMLAttributes<HTMLTableElement>) {
  return (
    <div className="relative w-full overflow-auto">
      <table
        className={`w-full caption-bottom text-xs text-left ${className}`}
        {...props}
      />
    </div>
  )
}

export function TableHeader({
  className = '',
  ...props
}: React.HTMLAttributes<HTMLTableSectionElement>) {
  return (
    <thead
      className={`border-b border-border bg-surface-sunken/60 font-mono uppercase text-ink-muted text-[11px] ${className}`}
      {...props}
    />
  )
}

export function TableBody({
  className = '',
  ...props
}: React.HTMLAttributes<HTMLTableSectionElement>) {
  return (
    <tbody
      className={`divide-y divide-border/60 ${className}`}
      {...props}
    />
  )
}

export function TableRow({
  className = '',
  ...props
}: React.HTMLAttributes<HTMLTableRowElement>) {
  return (
    <tr
      className={`transition-colors hover:bg-surface-sunken/40 ${className}`}
      {...props}
    />
  )
}

export function TableHead({
  className = '',
  ...props
}: React.ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      className={`h-9 px-4 text-left font-medium text-ink-muted align-middle ${className}`}
      {...props}
    />
  )
}

export function TableCell({
  className = '',
  ...props
}: React.TdHTMLAttributes<HTMLTableCellElement>) {
  return (
    <td
      className={`p-4 align-middle text-ink ${className}`}
      {...props}
    />
  )
}
