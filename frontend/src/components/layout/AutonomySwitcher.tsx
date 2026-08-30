'use client'

import React, { useState } from 'react'
import { AlertOctagon, Bot, UserCheck } from 'lucide-react'

export type AutonomyMode = 'FULL_AUTONOMY' | 'HUMAN_IN_THE_LOOP' | 'MONITORING_ONLY'

interface AutonomySwitcherProps {
  mode?: AutonomyMode
  onChange?: (mode: AutonomyMode) => void
}

export function AutonomySwitcher({
  mode = 'FULL_AUTONOMY',
  onChange,
}: AutonomySwitcherProps) {
  const [currentMode, setCurrentMode] = useState<AutonomyMode>(mode)

  const handleSelect = (newMode: AutonomyMode) => {
    setCurrentMode(newMode)
    if (onChange) onChange(newMode)
  }

  return (
    <div className="flex items-center rounded-control bg-surface-sunken p-0.5 border border-border text-xs font-mono">
      <button
        type="button"
        onClick={() => {
          handleSelect('FULL_AUTONOMY')
        }}
        className={`flex items-center gap-1.5 px-2.5 py-1 rounded-control transition-all cursor-pointer ${
          currentMode === 'FULL_AUTONOMY'
            ? 'bg-recovered text-white font-bold shadow-xs'
            : 'text-ink-muted hover:text-ink'
        }`}
        title="Full autonomous dunning and smart retries active"
      >
        <Bot className="h-3 w-3" />
        <span className="hidden sm:inline">Autonomous</span>
      </button>

      <button
        type="button"
        onClick={() => {
          handleSelect('HUMAN_IN_THE_LOOP')
        }}
        className={`flex items-center gap-1.5 px-2.5 py-1 rounded-control transition-all cursor-pointer ${
          currentMode === 'HUMAN_IN_THE_LOOP'
            ? 'bg-accent text-white font-bold shadow-xs'
            : 'text-ink-muted hover:text-ink'
        }`}
        title="AI plans strategy; operator approval required"
      >
        <UserCheck className="h-3 w-3" />
        <span className="hidden sm:inline">HITL Mode</span>
      </button>

      <button
        type="button"
        onClick={() => {
          handleSelect('MONITORING_ONLY')
        }}
        className={`flex items-center gap-1.5 px-2.5 py-1 rounded-control transition-all cursor-pointer ${
          currentMode === 'MONITORING_ONLY'
            ? 'bg-failed text-white font-bold shadow-xs'
            : 'text-ink-muted hover:text-ink'
        }`}
        title="Global Circuit Breaker: Outbound interventions paused"
      >
        <AlertOctagon className="h-3 w-3" />
        <span className="hidden sm:inline">Paused</span>
      </button>
    </div>
  )
}
