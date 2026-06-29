import * as React from 'react'
import * as AccordionPrimitive from '@radix-ui/react-accordion'
import { ChevronDown } from 'lucide-react'
import { cn } from '@/lib/utils'

const Accordion = AccordionPrimitive.Root

function AccordionItem({ className, ...props }) {
  return (
    <AccordionPrimitive.Item
      className={cn('border-b border-[var(--color-border)] last:border-0', className)}
      {...props}
    />
  )
}

function AccordionTrigger({ className, children, ...props }) {
  return (
    <AccordionPrimitive.Header className="flex">
      <AccordionPrimitive.Trigger
        className={cn(
          'flex flex-1 items-center justify-between py-3 text-sm font-medium text-[var(--color-text)]',
          'transition-all hover:text-[var(--color-gold)] [&[data-state=open]>svg]:rotate-180',
          className
        )}
        {...props}
      >
        {children}
        <ChevronDown className="size-4 text-[var(--color-muted)] shrink-0 transition-transform duration-200" />
      </AccordionPrimitive.Trigger>
    </AccordionPrimitive.Header>
  )
}

function AccordionContent({ className, children, ...props }) {
  return (
    <AccordionPrimitive.Content
      className={cn(
        'overflow-hidden text-sm text-[var(--color-muted)]',
        'data-[state=closed]:animate-none data-[state=open]:animate-none',
        className
      )}
      {...props}
    >
      <div className="pb-3 pt-1">{children}</div>
    </AccordionPrimitive.Content>
  )
}

export { Accordion, AccordionItem, AccordionTrigger, AccordionContent }
