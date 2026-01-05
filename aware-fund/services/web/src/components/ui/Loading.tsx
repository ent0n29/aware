'use client'

import { cn } from '@/lib/utils'

interface LoadingProps {
  size?: 'sm' | 'md' | 'lg'
  className?: string
}

export function Loading({ size = 'md', className }: LoadingProps) {
  const sizeClasses = {
    sm: 'h-4 w-4',
    md: 'h-8 w-8',
    lg: 'h-12 w-12',
  }

  return (
    <div className={cn('flex items-center justify-center', className)}>
      <div
        className={cn(
          'animate-spin rounded-full border-2 border-slate-700 border-t-aware-500',
          sizeClasses[size]
        )}
      />
    </div>
  )
}

export function LoadingCard() {
  return (
    <div className="rounded-xl bg-slate-900/50 border border-slate-800 p-6 animate-pulse">
      <div className="flex items-center gap-4">
        <div className="w-12 h-12 rounded-full bg-slate-800" />
        <div className="flex-1 space-y-2">
          <div className="h-4 bg-slate-800 rounded w-3/4" />
          <div className="h-3 bg-slate-800 rounded w-1/2" />
        </div>
      </div>
      <div className="mt-4 space-y-2">
        <div className="h-3 bg-slate-800 rounded" />
        <div className="h-3 bg-slate-800 rounded w-5/6" />
      </div>
    </div>
  )
}

export function LoadingTable({ rows = 5 }: { rows?: number }) {
  return (
    <div className="rounded-xl bg-slate-900/50 border border-slate-800 overflow-hidden">
      <div className="p-4 border-b border-slate-800">
        <div className="h-5 bg-slate-800 rounded w-1/4 animate-pulse" />
      </div>
      <div className="divide-y divide-slate-800">
        {Array.from({ length: rows }).map((_, i) => (
          <div key={i} className="p-4 flex items-center gap-4 animate-pulse">
            <div className="w-8 h-8 rounded-full bg-slate-800" />
            <div className="flex-1 space-y-2">
              <div className="h-4 bg-slate-800 rounded w-1/3" />
              <div className="h-3 bg-slate-800 rounded w-1/4" />
            </div>
            <div className="h-4 bg-slate-800 rounded w-16" />
            <div className="h-4 bg-slate-800 rounded w-20" />
          </div>
        ))}
      </div>
    </div>
  )
}

export function LoadingPage() {
  return (
    <div className="space-y-6">
      {/* Header skeleton */}
      <div className="animate-pulse">
        <div className="h-8 bg-slate-800 rounded w-1/4 mb-2" />
        <div className="h-4 bg-slate-800 rounded w-1/3" />
      </div>

      {/* Stats grid skeleton */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="rounded-xl bg-slate-900/50 border border-slate-800 p-5 animate-pulse">
            <div className="h-4 bg-slate-800 rounded w-1/2 mb-3" />
            <div className="h-8 bg-slate-800 rounded w-3/4" />
          </div>
        ))}
      </div>

      {/* Main content skeleton */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <LoadingCard />
        <LoadingCard />
      </div>
    </div>
  )
}
