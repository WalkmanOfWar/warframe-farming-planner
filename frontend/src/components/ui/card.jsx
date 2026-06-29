import * as React from 'react'
import { cn } from '@/lib/utils'

function Card({ className, ...props }) {
  return (
    <div
      className={cn(
        'rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-sm',
        className
      )}
      {...props}
    />
  )
}

function CardHeader({ className, ...props }) {
  return <div className={cn('flex flex-col gap-1.5 p-5 pb-3', className)} {...props} />
}

function CardTitle({ className, ...props }) {
  return (
    <h2
      className={cn('text-lg font-semibold text-[var(--color-gold)] leading-none', className)}
      {...props}
    />
  )
}

function CardDescription({ className, ...props }) {
  return <p className={cn('text-sm text-[var(--color-muted)]', className)} {...props} />
}

function CardContent({ className, ...props }) {
  return <div className={cn('p-5 pt-2', className)} {...props} />
}

function CardFooter({ className, ...props }) {
  return <div className={cn('flex items-center p-5 pt-2', className)} {...props} />
}

export { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter }
