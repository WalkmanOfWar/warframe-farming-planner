import * as React from 'react'
import { cva } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const badgeVariants = cva(
  'inline-flex items-center rounded-md px-2 py-0.5 text-xs font-semibold transition-colors',
  {
    variants: {
      variant: {
        default:  'bg-[var(--color-surface)] border border-[var(--color-border)] text-[var(--color-muted)]',
        gold:     'bg-[var(--color-gold)] text-[#1a1a1a]',
        accent:   'bg-[var(--color-accent)]/20 text-[var(--color-accent)] border border-[var(--color-accent)]/30',
        relic:    'bg-[var(--color-surface)] border border-[var(--color-border)] text-[var(--color-text)]',
        lith:     'bg-[var(--color-lith)] text-white',
        meso:     'bg-[var(--color-meso)] text-white',
        neo:      'bg-[var(--color-neo)] text-white',
        axi:      'bg-[var(--color-axi)] text-white',
        requiem:  'bg-[var(--color-requiem)] text-white',
      },
    },
    defaultVariants: { variant: 'default' },
  }
)

function Badge({ className, variant, ...props }) {
  return <span className={cn(badgeVariants({ variant, className }))} {...props} />
}

export { Badge, badgeVariants }
