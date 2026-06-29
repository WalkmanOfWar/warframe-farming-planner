import * as React from 'react'
import { cn } from '@/lib/utils'

function Input({ className, type, ...props }) {
  return (
    <input
      type={type}
      className={cn(
        'flex h-10 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2',
        'text-sm text-[var(--color-text)] placeholder:text-[var(--color-muted)]',
        'outline-none focus:border-[var(--color-accent)] focus:ring-1 focus:ring-[var(--color-accent)]',
        'disabled:cursor-not-allowed disabled:opacity-50',
        'transition-colors',
        className
      )}
      {...props}
    />
  )
}

export { Input }
