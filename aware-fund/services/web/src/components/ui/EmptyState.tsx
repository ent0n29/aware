'use client'

import { cn } from '@/lib/utils'
import { LucideIcon, Inbox, Search, AlertCircle } from 'lucide-react'

interface EmptyStateProps {
  icon?: LucideIcon
  title: string
  description?: string
  action?: {
    label: string
    onClick: () => void
  }
  className?: string
}

export function EmptyState({
  icon: Icon = Inbox,
  title,
  description,
  action,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center py-12 px-4 text-center',
        className
      )}
    >
      <div className="rounded-full bg-slate-800 p-4 mb-4">
        <Icon className="h-8 w-8 text-slate-500" />
      </div>
      <h3 className="text-lg font-semibold text-white mb-1">{title}</h3>
      {description && (
        <p className="text-sm text-slate-400 max-w-sm">{description}</p>
      )}
      {action && (
        <button
          onClick={action.onClick}
          className="mt-4 px-4 py-2 bg-aware-500 text-white text-sm font-medium rounded-lg hover:bg-aware-600 transition-colors"
        >
          {action.label}
        </button>
      )}
    </div>
  )
}

export function NoResults({ query }: { query: string }) {
  return (
    <EmptyState
      icon={Search}
      title="No results found"
      description={`We couldn't find anything matching "${query}". Try a different search term.`}
    />
  )
}

export function ErrorState({
  message = 'Something went wrong',
  retry,
}: {
  message?: string
  retry?: () => void
}) {
  return (
    <EmptyState
      icon={AlertCircle}
      title="Error"
      description={message}
      action={retry ? { label: 'Try again', onClick: retry } : undefined}
    />
  )
}
