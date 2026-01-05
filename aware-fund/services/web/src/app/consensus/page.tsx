'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import {
  Users,
  Filter,
  TrendingUp,
  Zap,
  Clock,
  ChevronRight,
  AlertCircle,
  CheckCircle,
  Loader2,
} from 'lucide-react'
import { cn, formatCurrency, getTimeAgo } from '@/lib/utils'
import { api, ConsensusSignal, ConsensusResponse } from '@/lib/api'

interface Signal {
  id: number
  market_slug: string
  title: string
  outcome: string
  consensus_level: number
  traders_count: number
  avg_score: number
  total_volume: number
  signal_strength: 'STRONG' | 'MODERATE' | 'WEAK'
  direction: 'BULLISH' | 'BEARISH'
}

const strengthConfig = {
  STRONG: {
    bg: 'bg-green-500/10',
    border: 'border-green-500/30',
    text: 'text-green-400',
    icon: CheckCircle,
    label: 'Strong Signal',
  },
  MODERATE: {
    bg: 'bg-yellow-500/10',
    border: 'border-yellow-500/30',
    text: 'text-yellow-400',
    icon: AlertCircle,
    label: 'Moderate Signal',
  },
  WEAK: {
    bg: 'bg-slate-500/10',
    border: 'border-slate-500/30',
    text: 'text-slate-400',
    icon: Clock,
    label: 'Weak Signal',
  },
}

export default function ConsensusPage() {
  const [signals, setSignals] = useState<Signal[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<'all' | 'STRONG' | 'MODERATE' | 'WEAK'>('all')
  const [sortBy, setSortBy] = useState<'consensus' | 'volume' | 'recency'>('consensus')

  useEffect(() => {
    async function fetchConsensus() {
      try {
        setIsLoading(true)
        setError(null)
        const response = await api.getConsensusSignals(3, 5000, 48)

        // Transform API response to our Signal format
        const transformedSignals: Signal[] = response.signals.map((s, idx) => ({
          id: idx + 1,
          market_slug: s.market_slug,
          title: s.title,
          outcome: s.favored_outcome,
          consensus_level: Math.round(s.avg_price * 100),
          traders_count: s.trader_count,
          avg_score: 80, // Placeholder - could be added to API
          total_volume: s.total_volume,
          signal_strength: s.consensus_strength,
          direction: s.favored_outcome.toLowerCase() === 'yes' ? 'BULLISH' : 'BEARISH',
        }))

        setSignals(transformedSignals)
      } catch (err) {
        setError('Failed to load consensus signals. Make sure the API server is running.')
        console.error('Consensus fetch error:', err)
      } finally {
        setIsLoading(false)
      }
    }
    fetchConsensus()
  }, [])

  const filteredSignals = signals
    .filter((s) => filter === 'all' || s.signal_strength === filter)
    .sort((a, b) => {
      if (sortBy === 'consensus') return b.consensus_level - a.consensus_level
      if (sortBy === 'volume') return b.total_volume - a.total_volume
      return 0
    })

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-3">
            <Users className="h-7 w-7 text-purple-400" />
            Consensus Signals
          </h1>
          <p className="text-slate-400 mt-1">
            When smart money aligns on a market outcome
          </p>
        </div>

        {/* Stats */}
        <div className="flex gap-4">
          <div className="px-4 py-2 rounded-lg bg-green-500/10 border border-green-500/20">
            <p className="text-2xl font-bold text-green-400">
              {signals.filter((s) => s.signal_strength === 'STRONG').length}
            </p>
            <p className="text-xs text-slate-500">Strong Signals</p>
          </div>
          <div className="px-4 py-2 rounded-lg bg-yellow-500/10 border border-yellow-500/20">
            <p className="text-2xl font-bold text-yellow-400">
              {signals.filter((s) => s.signal_strength === 'MODERATE').length}
            </p>
            <p className="text-xs text-slate-500">Moderate</p>
          </div>
        </div>
      </div>

      {/* Explainer */}
      <div className="rounded-xl bg-gradient-to-r from-purple-500/10 to-aware-500/10 border border-purple-500/20 p-5">
        <div className="flex items-start gap-4">
          <div className="p-2 rounded-lg bg-purple-500/20">
            <Zap className="h-5 w-5 text-purple-400" />
          </div>
          <div>
            <h3 className="font-semibold text-white mb-1">What are Consensus Signals?</h3>
            <p className="text-sm text-slate-400">
              When multiple high-scoring traders take similar positions on a market,
              it creates a "consensus signal." The stronger the signal, the more aligned
              smart money is on the expected outcome. Use these signals to identify
              high-conviction opportunities.
            </p>
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-4">
        <div className="flex gap-1 p-1 bg-slate-800/50 rounded-lg">
          {['all', 'STRONG', 'MODERATE', 'WEAK'].map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f as any)}
              className={cn(
                'px-3 py-1.5 text-xs font-medium rounded-md transition-all capitalize',
                filter === f
                  ? 'bg-aware-500 text-white'
                  : 'text-slate-400 hover:text-white'
              )}
            >
              {f === 'all' ? 'All Signals' : f.toLowerCase()}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2 text-sm text-slate-500">
          <span>Sort by:</span>
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as any)}
            className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-white text-sm focus:outline-none focus:ring-2 focus:ring-aware-500"
          >
            <option value="consensus">Consensus Level</option>
            <option value="volume">Volume</option>
            <option value="recency">Most Recent</option>
          </select>
        </div>
      </div>

      {/* Loading State */}
      {isLoading && (
        <div className="rounded-xl bg-slate-900/50 border border-slate-800 p-12 flex items-center justify-center">
          <Loader2 className="h-8 w-8 text-aware-400 animate-spin" />
          <span className="ml-3 text-slate-400">Loading consensus signals...</span>
        </div>
      )}

      {/* Error State */}
      {error && !isLoading && (
        <div className="rounded-xl bg-red-500/10 border border-red-500/30 p-6">
          <p className="text-red-400 font-medium">{error}</p>
          <p className="text-sm text-slate-400 mt-2">
            Start the API server: <code className="bg-slate-800 px-2 py-0.5 rounded">cd aware-fund/services/api && uvicorn main:app --reload</code>
          </p>
        </div>
      )}

      {/* Empty State */}
      {!isLoading && !error && filteredSignals.length === 0 && (
        <div className="rounded-xl bg-slate-900/50 border border-slate-800 p-12 text-center">
          <Users className="h-12 w-12 text-slate-600 mx-auto mb-4" />
          <p className="text-slate-400">No consensus signals found</p>
          <p className="text-sm text-slate-500 mt-1">
            Signals are generated when multiple smart traders align on a market
          </p>
        </div>
      )}

      {/* Signals List */}
      {!isLoading && !error && filteredSignals.length > 0 && (
        <div className="space-y-4">
          {filteredSignals.map((signal) => {
            const config = strengthConfig[signal.signal_strength]
            const Icon = config.icon

            return (
              <div
                key={signal.id}
                className={cn(
                  'rounded-xl border p-5 transition-all hover:shadow-lg',
                  config.bg,
                  config.border
                )}
              >
                <div className="flex flex-col lg:flex-row lg:items-center gap-4">
                  {/* Left: Market Info */}
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-2">
                      <span className={cn('inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium', config.bg, config.text)}>
                        <Icon className="h-3 w-3" />
                        {config.label}
                      </span>
                    </div>
                    <h3 className="text-lg font-semibold text-white mb-2">
                      {signal.title}
                    </h3>
                    <div className="flex items-center gap-4 text-sm">
                      <div className="flex items-center gap-1">
                        <span className="text-slate-500">Consensus:</span>
                        <span className={cn('font-semibold', signal.direction === 'BULLISH' ? 'text-green-400' : 'text-red-400')}>
                          {signal.outcome}
                        </span>
                      </div>
                      <div className="flex items-center gap-1">
                        <Users className="h-4 w-4 text-slate-500" />
                        <span className="text-slate-300">{signal.traders_count} traders</span>
                      </div>
                    </div>
                  </div>

                  {/* Right: Metrics */}
                  <div className="flex items-center gap-6">
                    {/* Consensus Bar */}
                    <div className="w-32">
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs text-slate-500">Avg Price</span>
                        <span className="text-sm font-bold text-white">{signal.consensus_level}¢</span>
                      </div>
                      <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
                        <div
                          className={cn(
                            'h-full rounded-full transition-all',
                            signal.consensus_level >= 80 ? 'bg-green-500' :
                            signal.consensus_level >= 60 ? 'bg-yellow-500' : 'bg-slate-500'
                          )}
                          style={{ width: `${signal.consensus_level}%` }}
                        />
                      </div>
                    </div>

                    {/* Volume */}
                    <div className="text-right">
                      <p className="text-lg font-bold text-white">{formatCurrency(signal.total_volume)}</p>
                      <p className="text-xs text-slate-500">Combined Volume</p>
                    </div>

                    <ChevronRight className="h-5 w-5 text-slate-600" />
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
