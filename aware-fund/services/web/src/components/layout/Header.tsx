'use client'

import { useState } from 'react'
import { Search, Bell, User, ChevronDown, Database, Menu } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useDataFreshness } from '@/lib/hooks'

interface HeaderProps {
  onMenuClick?: () => void
}

export function Header({ onMenuClick }: HeaderProps) {
  const [searchQuery, setSearchQuery] = useState('')
  const [notifications] = useState(3) // Mock notification count
  const { freshness, isLoading: freshnessLoading } = useDataFreshness()

  // Get status-based styling
  const getStatusStyles = () => {
    if (freshnessLoading || !freshness) {
      return {
        bg: 'bg-slate-500/10',
        border: 'border-slate-500/20',
        dot: 'bg-slate-500',
        ping: 'bg-slate-400',
        text: 'text-slate-400',
        label: 'Loading...'
      }
    }

    switch (freshness.status) {
      case 'fresh':
        return {
          bg: 'bg-green-500/10',
          border: 'border-green-500/20',
          dot: 'bg-green-500',
          ping: 'bg-green-400',
          text: 'text-green-400',
          label: 'Live'
        }
      case 'stale':
        return {
          bg: 'bg-yellow-500/10',
          border: 'border-yellow-500/20',
          dot: 'bg-yellow-500',
          ping: 'bg-yellow-400',
          text: 'text-yellow-400',
          label: 'Delayed'
        }
      case 'outdated':
        return {
          bg: 'bg-red-500/10',
          border: 'border-red-500/20',
          dot: 'bg-red-500',
          ping: 'bg-red-400',
          text: 'text-red-400',
          label: 'Outdated'
        }
      default:
        return {
          bg: 'bg-slate-500/10',
          border: 'border-slate-500/20',
          dot: 'bg-slate-500',
          ping: 'bg-slate-400',
          text: 'text-slate-400',
          label: 'Unknown'
        }
    }
  }

  const statusStyles = getStatusStyles()

  return (
    <header className="sticky top-0 z-30 h-16 bg-slate-950/80 backdrop-blur-xl border-b border-slate-800">
      <div className="flex h-full items-center justify-between px-4 md:px-6">
        {/* Mobile menu button */}
        {onMenuClick && (
          <button
            onClick={onMenuClick}
            className="md:hidden p-2 mr-2 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition-colors"
            aria-label="Open menu"
          >
            <Menu className="w-6 h-6" />
          </button>
        )}

        {/* Search */}
        <div className="flex-1 max-w-xl">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-500" />
            <input
              type="text"
              placeholder="Search traders, markets, or indices..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full h-10 pl-10 pr-4 bg-slate-900 border border-slate-800 rounded-lg text-sm text-white placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-aware-500/50 focus:border-aware-500 transition-all"
            />
            <kbd className="absolute right-3 top-1/2 -translate-y-1/2 hidden sm:inline-flex items-center gap-1 px-2 py-0.5 bg-slate-800 text-slate-500 text-xs rounded">
              ⌘K
            </kbd>
          </div>
        </div>

        {/* Right side */}
        <div className="flex items-center gap-4 ml-4">
          {/* Data freshness indicator */}
          <div className="group relative">
            <div className={cn(
              "flex items-center gap-2 px-3 py-1.5 rounded-full cursor-help",
              statusStyles.bg,
              `border ${statusStyles.border}`
            )}>
              <span className="relative flex h-2 w-2">
                {freshness?.status === 'fresh' && (
                  <span className={cn(
                    "animate-ping absolute inline-flex h-full w-full rounded-full opacity-75",
                    statusStyles.ping
                  )} />
                )}
                <span className={cn(
                  "relative inline-flex rounded-full h-2 w-2",
                  statusStyles.dot
                )} />
              </span>
              <span className={cn("text-xs font-medium", statusStyles.text)}>
                {statusStyles.label}
              </span>
            </div>

            {/* Tooltip on hover */}
            {freshness && (
              <div className="absolute right-0 top-full mt-2 w-64 p-3 bg-slate-900 border border-slate-700 rounded-lg shadow-xl opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-50">
                <div className="flex items-center gap-2 mb-2">
                  <Database className="w-4 h-4 text-aware-400" />
                  <span className="text-sm font-medium text-white">Data Freshness</span>
                </div>
                <div className="space-y-1.5 text-xs">
                  <div className="flex justify-between">
                    <span className="text-slate-400">Latest trade:</span>
                    <span className="text-slate-200">{freshness.latest_trade_age_human}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Last scoring:</span>
                    <span className="text-slate-200">{freshness.last_scoring_age_human}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Data coverage:</span>
                    <span className="text-slate-200">{freshness.data_coverage_days} days</span>
                  </div>
                </div>
                <div className="mt-2 pt-2 border-t border-slate-700">
                  <p className="text-xs text-slate-400">{freshness.recommendation}</p>
                </div>
              </div>
            )}
          </div>

          {/* Notifications */}
          <button className="relative p-2 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition-colors">
            <Bell className="w-5 h-5" />
            {notifications > 0 && (
              <span className="absolute -top-0.5 -right-0.5 w-4 h-4 bg-red-500 text-white text-xs font-bold rounded-full flex items-center justify-center">
                {notifications}
              </span>
            )}
          </button>

          {/* Profile */}
          <button className="flex items-center gap-2 p-1.5 hover:bg-slate-800 rounded-lg transition-colors">
            <div className="w-8 h-8 rounded-full bg-gradient-to-br from-aware-400 to-aware-600 flex items-center justify-center">
              <User className="w-4 h-4 text-white" />
            </div>
            <ChevronDown className="w-4 h-4 text-slate-400" />
          </button>
        </div>
      </div>
    </header>
  )
}
