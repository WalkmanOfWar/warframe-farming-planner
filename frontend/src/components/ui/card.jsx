import * as React from 'react'
import { cn } from '@/lib/utils'

function Card({ className, accent = false, ...props }) {
  return (
    <div
      className={cn(
        'rounded-xl border bg-[var(--color-surface)] shadow-lg',
        accent
          ? 'border-[var(--color-gold)]/40 border-t-2 border-t-[var(--color-gold)]'
          : 'border-[var(--color-border)]',
        className
      )}
      {...props}
    />
  )
}

function CardHeader({ className, ...props }) {
  return <div className={cn('flex flex-col gap-1 px-6 pt-6 pb-4', className)} {...props} />
}

function CardTitle({ className, ...props }) {
  return (
    <h2
      className={cn('text-base font-semibold text-[var(--color-gold)] flex items-center gap-2', className)}
      {...props}
    />
  )
}

function CardDescription({ className, ...props }) {
  return <p className={cn('text-sm text-[var(--color-muted)]', className)} {...props} />
}

function CardContent({ className, ...props }) {
  return <div className={cn('px-6 pb-6', className)} {...props} />
}

function CardFooter({ className, ...props }) {
  return <div className={cn('flex items-center px-6 pb-6', className)} {...props} />
}

export { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter }
