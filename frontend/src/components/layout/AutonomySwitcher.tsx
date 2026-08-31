'use client'

import React, { useEffect, useState } from 'react'
import { AlertOctagon, Bot, Loader2, UserCheck } from 'lucide-react'
import {
  getOperatorMode,
  updateOperatorMode,
  type OperatorAutonomyMode,
} from '@/lib/api'

interface AutonomySwitcherProps {
  onModeChange?: (mode: OperatorAutonomyMode) => void
}

export function AutonomySwitcher({ onModeChange }: AutonomySwitcherProps) {
  const [currentMode, setCurrentMode] =
    useState<OperatorAutonomyMode>('FULL_AUTONOMY')
  const [isUpdating, setIsUpdating] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  useEffect(() => {
    let mounted = true
    getOperatorMode()
      .then((state) => {
        if (mounted) {
          setCurrentMode(state.mode)
          if (onModeChange) onModeChange(state.mode)
        }
      })
      .catch((err: unknown) => {
        const error = err instanceof Error ? err.message : String(err)
        setErrorMessage(error)
      })
    return () => {
      mounted = false
    }
  }, [onModeChange])

  const handleSelect = async (newMode: OperatorAutonomyMode) => {
    if (newMode === currentMode || isUpdating) return

    const previousMode = currentMode
    setIsUpdating(true)
    setErrorMessage(null)

    try {
      const reason = `Operator switched mode to ${newMode}`
      const updated = await updateOperatorMode(newMode, reason)
      setCurrentMode(updated.mode)
      if (onModeChange) onModeChange(updated.mode)
    } catch (err: unknown) {
      setCurrentMode(previousMode)
      const error = err instanceof Error ? err.message : String(err)
      setErrorMessage(error)
    } finally {
      setIsUpdating(false)
    }
  }

  return (
    <div className="relative flex items-center">
      <div className="flex items-center rounded-control border border-border bg-surface-sunken p-0.5 font-mono text-xs">
        <button
          type="button"
          disabled={isUpdating}
          onClick={() => {
            void handleSelect('FULL_AUTONOMY')
          }}
          className={`flex cursor-pointer items-center gap-1.5 rounded-control px-2.5 py-1 transition-all ${
            currentMode === 'FULL_AUTONOMY'
              ? 'bg-recovered font-bold text-white shadow-xs'
              : 'text-ink-muted hover:text-ink disabled:opacity-50'
          }`}
          title="Full autonomous dunning and smart retries active"
        >
          {isUpdating && currentMode === 'FULL_AUTONOMY' ? (
            <Loader2 className="h-3 w-3 animate-spin" />
          ) : (
            <Bot className="h-3 w-3" />
          )}
          <span className="hidden sm:inline">Autonomous</span>
        </button>

        <button
          type="button"
          disabled={isUpdating}
          onClick={() => {
            void handleSelect('HUMAN_IN_THE_LOOP')
          }}
          className={`flex cursor-pointer items-center gap-1.5 rounded-control px-2.5 py-1 transition-all ${
            currentMode === 'HUMAN_IN_THE_LOOP'
              ? 'bg-accent font-bold text-white shadow-xs'
              : 'text-ink-muted hover:text-ink disabled:opacity-50'
          }`}
          title="AI plans strategy; operator approval required"
        >
          {isUpdating && currentMode === 'HUMAN_IN_THE_LOOP' ? (
            <Loader2 className="h-3 w-3 animate-spin" />
          ) : (
            <UserCheck className="h-3 w-3" />
          )}
          <span className="hidden sm:inline">HITL Mode</span>
        </button>

        <button
          type="button"
          disabled={isUpdating}
          onClick={() => {
            void handleSelect('MONITORING_ONLY')
          }}
          className={`flex cursor-pointer items-center gap-1.5 rounded-control px-2.5 py-1 transition-all ${
            currentMode === 'MONITORING_ONLY'
              ? 'bg-failed font-bold text-white shadow-xs'
              : 'text-ink-muted hover:text-ink disabled:opacity-50'
          }`}
          title="Global Circuit Breaker: Outbound interventions paused"
        >
          {isUpdating && currentMode === 'MONITORING_ONLY' ? (
            <Loader2 className="h-3 w-3 animate-spin" />
          ) : (
            <AlertOctagon className="h-3 w-3" />
          )}
          <span className="hidden sm:inline">Paused (Circuit Breaker)</span>
        </button>
      </div>

      {errorMessage && (
        <span className="absolute right-0 -bottom-5 font-mono text-[10px] whitespace-nowrap text-failed">
          {errorMessage}
        </span>
      )}
    </div>
  )
}
