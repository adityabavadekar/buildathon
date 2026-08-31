import React from 'react'

export function Table({
  className = '',
  ...props
}: React.HTMLAttributes<HTMLTableElement>) {
  return (
    <div className="data-table-shell relative w-full overflow-auto">
      <table
        className={`data-table w-full caption-bottom text-left text-xs ${className}`}
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
      className={`font-sans text-[11px] font-semibold uppercase tracking-wide ${className}`}
      {...props}
    />
  )
}

export function TableBody({
  className = '',
  ...props
}: React.HTMLAttributes<HTMLTableSectionElement>) {
  return (
    <tbody className={`divide-y divide-border/50 bg-surface ${className}`} {...props} />
  )
}

export function TableRow({
  className = '',
  ...props
}: React.HTMLAttributes<HTMLTableRowElement>) {
  return (
    <tr
      className={`transition-colors ${className}`}
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
      className={`h-10 px-4 text-left align-middle font-semibold ${className}`}
      {...props}
    />
  )
}

export function TableCell({
  className = '',
  ...props
}: React.TdHTMLAttributes<HTMLTableCellElement>) {
  return <td className={`p-4 align-middle text-ink ${className}`} {...props} />
}
