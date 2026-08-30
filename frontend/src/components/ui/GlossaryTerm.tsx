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
      className={`relative inline-flex items-center gap-1 cursor-help group ${className}`}
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
        <HelpCircle className="h-3 w-3 text-ink-muted transition-colors group-hover:text-ink shrink-0" />
      )}

      {open && (
        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 z-50 w-72 p-3 rounded-panel bg-surface border border-border shadow-xl text-left font-sans animate-in fade-in-0 zoom-in-95 pointer-events-none">
          <div className="flex items-center justify-between pb-1 mb-1.5 border-b border-border/60">
            <span className="font-mono text-xs font-bold text-ink">
              {item.title}
            </span>
          </div>
          <p className="text-[11px] leading-relaxed text-ink mb-2">
            {item.definition}
          </p>
          <div className="pt-1.5 border-t border-border/40 text-[10px] leading-tight text-accent font-medium">
            <span className="font-semibold text-ink-subtle">Why it matters: </span>
            {item.whyItMatters}
          </div>
          {/* Subtle triangle arrow */}
          <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-border" />
        </div>
      )}
    </span>
  )
}
