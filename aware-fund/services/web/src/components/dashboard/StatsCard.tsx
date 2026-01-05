'use client'

import { LucideIcon } from 'lucide-react'
import { cn } from '@/lib/utils'
import { ArrowUpRight, ArrowDownRight } from 'lucide-react'

interface StatsCardProps {
  title: string
  value: string
  icon: LucideIcon
  trend?: {
    value: number
    isPositive: boolean
  }
  description?: string
  className?: string
}

export function StatsCard({
  title,
  value,
  icon: Icon,
  trend,
  description,
  className,
}: StatsCardProps) {
  return (
    <div
      className={cn(
        'relative overflow-hidden rounded-xl bg-slate-900/50 border border-slate-800 p-5 transition-all duration-300 hover:border-slate-700 hover:shadow-lg hover:shadow-aware-500/5',
        className
      )}
    >
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm font-medium text-slate-400">{title}</p>
          <p className="mt-2 text-2xl font-bold text-white">{value}</p>
          {description && (
            <p className="mt-1 text-xs text-slate-500">{description}</p>
          )}
        </div>
        <div className="rounded-lg bg-aware-500/10 p-2.5">
          <Icon className="h-5 w-5 text-aware-400" />
        </div>
      </div>

      {trend && (
        <div className="mt-3 flex items-center gap-1">
          {trend.isPositive ? (
            <ArrowUpRight className="h-4 w-4 text-green-400" />
          ) : (
            <ArrowDownRight className="h-4 w-4 text-red-400" />
          )}
          <span
            className={cn(
              'text-sm font-medium',
              trend.isPositive ? 'text-green-400' : 'text-red-400'
            )}
          >
            {trend.isPositive ? '+' : ''}{trend.value}%
          </span>
          <span className="text-xs text-slate-500">vs last period</span>
        </div>
      )}

      {/* Decorative gradient */}
      <div className="absolute -right-6 -top-6 h-24 w-24 rounded-full bg-aware-500/5 blur-2xl" />
    </div>
  )
}
