'use client'

import React, { useState } from 'react'
import { HelpCircle } from 'lucide-react'
import { GLOSSARY, type GlossaryDefinition } from '@/lib/glossary'

interface GlossaryTermProps {
  termKey: keyof typeof GLOSSARY
  children?: React.ReactNode
  showIcon?: boolean
  className?: string
}

export function GlossaryTerm({
  termKey,
  children,
  showIcon = true,
  className = '',
}: GlossaryTermProps) {
  const [open, setOpen] = useState(false)
  const item: GlossaryDefinition | undefined = GLOSSARY[termKey]

  if (!item) {
    return <span className={className}>{children ?? termKey}</span>
  }

  return (
    <span
      className={`group relative inline-flex cursor-help items-center gap-1 ${className}`}
      onMouseEnter={() => {
        setOpen(true)
      }}
      onMouseLeave={() => {
        setOpen(false)
      }}
      onFocus={() => {
        setOpen(true)
      }}
      onBlur={() => {
        setOpen(false)
      }}
      tabIndex={0}
      aria-label={`${item.title}: ${item.definition}`}
    >
      <span className="border-b border-dotted border-ink-muted/60 transition-colors group-hover:border-ink">
        {children ?? item.term}
      </span>
      {showIcon && (
        <HelpCircle className="h-3 w-3 shrink-0 text-ink-muted transition-colors group-hover:text-ink" />
      )}

      {open && (
        <div className="animate-in fade-in-0 zoom-in-95 pointer-events-none absolute bottom-full left-1/2 z-50 mb-2 w-72 -translate-x-1/2 rounded-panel border border-border bg-surface p-3 text-left font-sans shadow-xl">
          <div className="mb-1.5 flex items-center justify-between border-b border-border/60 pb-1">
            <span className="font-mono text-xs font-bold text-ink">
              {item.title}
            </span>
          </div>
          <p className="mb-2 text-[11px] leading-relaxed text-ink">
            {item.definition}
          </p>
          <div className="border-t border-border/40 pt-1.5 text-[10px] leading-tight font-medium text-accent">
            <span className="font-semibold text-ink-subtle">
              Why it matters:{' '}
            </span>
            {item.whyItMatters}
          </div>
          {/* Subtle triangle arrow */}
          <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-border" />
        </div>
      )}
    </span>
  )
}
