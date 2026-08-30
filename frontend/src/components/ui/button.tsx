import React from 'react'

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger'
  size?: 'sm' | 'md' | 'lg'
}

export function Button({
  variant = 'secondary',
  size = 'md',
  className = '',
  ...props
}: ButtonProps) {
  const variantStyles = {
    primary:
      'bg-ink text-surface hover:opacity-90 active:scale-[0.99] border-transparent',
    secondary:
      'bg-surface-sunken text-ink hover:bg-border/50 border-border active:scale-[0.99]',
    outline:
      'bg-surface text-ink hover:bg-surface-sunken border-border active:scale-[0.99]',
    ghost:
      'bg-transparent text-ink-muted hover:text-ink hover:bg-surface-sunken border-transparent',
    danger:
      'bg-failed-subtle text-failed hover:bg-failed/20 border-failed/30',
  }[variant]

  const sizeStyles = {
    sm: 'h-7 px-2.5 text-xs',
    md: 'h-8 px-3.5 text-xs',
    lg: 'h-9 px-4 text-sm',
  }[size]

  return (
    <button
      className={`inline-flex items-center justify-center gap-1.5 rounded-control border font-medium transition-all focus-visible:outline-2 focus-visible:outline-accent disabled:opacity-50 disabled:pointer-events-none cursor-pointer ${variantStyles} ${sizeStyles} ${className}`}
      {...props}
    />
  )
}
