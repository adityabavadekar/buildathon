'use client'

import React, { useCallback, useEffect, useRef, useState } from 'react'
import { Check, Copy } from 'lucide-react'
import { Button } from '@/components/ui/button'

const COPY_FEEDBACK_MS = 1600

interface CopyButtonProps {
  value: string
  label?: string
  subject?: string
  className?: string
  size?: 'sm' | 'md'
  variant?: 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger'
}

export function CopyButton({
  value,
  label,
  subject = 'value',
  className = '',
  size = 'sm',
  variant = 'ghost',
}: CopyButtonProps) {
  const [copied, setCopied] = useState<boolean>(false)
  const [failed, setFailed] = useState<boolean>(false)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(
    () => () => {
      if (timer.current !== null) {
        clearTimeout(timer.current)
      }
    },
    [],
  )

  const handleCopy = useCallback(async (): Promise<void> => {
    if (timer.current !== null) {
      clearTimeout(timer.current)
    }
    try {
      // Needs a secure context, so the catch reports failure to the operator.
      await navigator.clipboard.writeText(value)
      setCopied(true)
      setFailed(false)
    } catch {
      setCopied(false)
      setFailed(true)
    }
    timer.current = setTimeout(() => {
      setCopied(false)
      setFailed(false)
    }, COPY_FEEDBACK_MS)
  }, [value])

  const text = failed ? 'Copy failed' : copied ? 'Copied' : (label ?? 'Copy')

  return (
    <Button
      variant={variant}
      size={size}
      disabled={!value}
      aria-label={`Copy ${subject}`}
      onClick={() => {
        void handleCopy()
      }}
      className={`shrink-0 cursor-pointer gap-1.5 text-xs ${className}`}
    >
      {copied ? (
        <Check className="h-3.5 w-3.5" aria-hidden="true" />
      ) : (
        <Copy className="h-3.5 w-3.5" aria-hidden="true" />
      )}
      {text}
      <span className="sr-only" role="status" aria-live="polite">
        {copied ? `${subject} copied to clipboard` : ''}
      </span>
    </Button>
  )
}
