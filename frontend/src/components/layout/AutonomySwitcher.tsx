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
    <div className="relative hidden sm:block">
      <div className="autonomy-switcher">
        <button
          type="button"
          disabled={isUpdating}
          onClick={() => {
            void handleSelect('FULL_AUTONOMY')
          }}
          className={`autonomy-switcher-btn ${currentMode === 'FULL_AUTONOMY' ? 'autonomy-switcher-btn--active autonomy-switcher-btn--recovered' : ''}`}
          title="Full autonomous dunning and smart retries active"
        >
          {isUpdating && currentMode === 'FULL_AUTONOMY' ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Bot className="h-3.5 w-3.5" />
          )}
          <span className="hidden lg:inline">Autonomous</span>
        </button>

        <button
          type="button"
          disabled={isUpdating}
          onClick={() => {
            void handleSelect('HUMAN_IN_THE_LOOP')
          }}
          className={`autonomy-switcher-btn ${currentMode === 'HUMAN_IN_THE_LOOP' ? 'autonomy-switcher-btn--active autonomy-switcher-btn--accent' : ''}`}
          title="AI plans strategy; operator approval required"
        >
          {isUpdating && currentMode === 'HUMAN_IN_THE_LOOP' ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <UserCheck className="h-3.5 w-3.5" />
          )}
          <span className="hidden lg:inline">HITL</span>
        </button>

        <button
          type="button"
          disabled={isUpdating}
          onClick={() => {
            void handleSelect('MONITORING_ONLY')
          }}
          className={`autonomy-switcher-btn ${currentMode === 'MONITORING_ONLY' ? 'autonomy-switcher-btn--active autonomy-switcher-btn--failed' : ''}`}
          title="Global circuit breaker: outbound interventions paused"
        >
          {isUpdating && currentMode === 'MONITORING_ONLY' ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <AlertOctagon className="h-3.5 w-3.5" />
          )}
          <span className="hidden xl:inline">Paused</span>
        </button>
      </div>

      {errorMessage ? (
        <span className="absolute right-0 -bottom-5 text-[10px] whitespace-nowrap text-failed">
          {errorMessage}
        </span>
      ) : null}
    </div>
  )
}
