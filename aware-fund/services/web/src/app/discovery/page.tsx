'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import {
  Sparkles,
  TrendingUp,
  Star,
  Zap,
  Eye,
  ArrowUpRight,
  Filter,
  Rocket,
  Target,
  Shield,
  Loader2,
} from 'lucide-react'
import { cn, formatNumber, formatPercent, formatCurrency } from '@/lib/utils'
import { api, HiddenGem, DiscoveryResponse } from '@/lib/api'

const discoveryTypes = {
  HIDDEN_GEM: {
    icon: Sparkles,
    label: 'Hidden Gem',
    description: 'High skill, low visibility traders',
    color: 'text-purple-400',
    bg: 'bg-purple-500/10',
    border: 'border-purple-500/30',
  },
  RISING_STAR: {
    icon: Rocket,
    label: 'Rising Star',
    description: 'New traders showing exceptional performance',
    color: 'text-cyan-400',
    bg: 'bg-cyan-500/10',
    border: 'border-cyan-500/30',
  },
  NICHE_SPECIALIST: {
    icon: Target,
    label: 'Niche Specialist',
    description: 'Dominates a specific market category',
    color: 'text-green-400',
    bg: 'bg-green-500/10',
    border: 'border-green-500/30',
  },
  EMERGING: {
    icon: Rocket,
    label: 'Emerging Star',
    description: 'New traders showing exceptional performance',
    color: 'text-purple-400',
    bg: 'bg-purple-500/10',
    border: 'border-purple-500/30',
  },
  SPECIALIST: {
    icon: Target,
    label: 'Category Specialist',
    description: 'Dominates a specific market category',
    color: 'text-cyan-400',
    bg: 'bg-cyan-500/10',
    border: 'border-cyan-500/30',
  },
  CONSISTENT: {
    icon: Shield,
    label: 'Steady Performer',
    description: 'Low variance, reliable returns',
    color: 'text-green-400',
    bg: 'bg-green-500/10',
    border: 'border-green-500/30',
  },
  CONTRARIAN: {
    icon: Zap,
    label: 'Contrarian Alpha',
    description: 'Profits from against-the-crowd bets',
    color: 'text-yellow-400',
    bg: 'bg-yellow-500/10',
    border: 'border-yellow-500/30',
  },
}

interface Discovery {
  id: number
  username: string
  discovery_type: string
  score: number
  discovery_score: number
  reason: string
  recent_win_rate: number
  recent_sharpe: number
  total_trades: number
  days_active: number
  pnl_30d: number
  specialty: string
}

export default function DiscoveryPage() {
  const [discoveries, setDiscoveries] = useState<Discovery[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedType, setSelectedType] = useState<string | null>(null)

  useEffect(() => {
    async function fetchDiscoveries() {
      try {
        setIsLoading(true)
        setError(null)

        // Fetch all discovery types in parallel
        const [hiddenGems, risingStars, nicheSpecialists] = await Promise.allSettled([
          api.getHiddenGems(10),
          api.getRisingStars(10, 30),
          api.getNicheSpecialists(10),
        ])

        const allDiscoveries: Discovery[] = []
        let id = 1

        // Process hidden gems
        if (hiddenGems.status === 'fulfilled') {
          hiddenGems.value.discoveries.forEach((gem) => {
            allDiscoveries.push({
              id: id++,
              username: gem.username,
              discovery_type: 'HIDDEN_GEM',
              score: gem.smart_money_score,
              discovery_score: Math.round(gem.discovery_score * 100),
              reason: gem.reason,
              recent_win_rate: gem.win_rate * 100,
              recent_sharpe: gem.sharpe_ratio,
              total_trades: gem.total_trades,
              days_active: 0,
              pnl_30d: gem.total_pnl,
              specialty: 'Multi-category',
            })
          })
        }

        // Process rising stars
        if (risingStars.status === 'fulfilled') {
          risingStars.value.discoveries.forEach((star) => {
            allDiscoveries.push({
              id: id++,
              username: star.username,
              discovery_type: 'RISING_STAR',
              score: star.smart_money_score,
              discovery_score: Math.round(star.discovery_score * 100),
              reason: star.reason,
              recent_win_rate: star.win_rate * 100,
              recent_sharpe: star.sharpe_ratio,
              total_trades: star.total_trades,
              days_active: 0,
              pnl_30d: star.total_pnl,
              specialty: 'New trader',
            })
          })
        }

        // Process niche specialists
        if (nicheSpecialists.status === 'fulfilled') {
          nicheSpecialists.value.discoveries.forEach((spec) => {
            allDiscoveries.push({
              id: id++,
              username: spec.username,
              discovery_type: 'NICHE_SPECIALIST',
              score: spec.smart_money_score,
              discovery_score: Math.round(spec.discovery_score * 100),
              reason: spec.reason,
              recent_win_rate: spec.win_rate * 100,
              recent_sharpe: spec.sharpe_ratio,
              total_trades: spec.total_trades,
              days_active: 0,
              pnl_30d: spec.total_pnl,
              specialty: 'Specialist',
            })
          })
        }

        setDiscoveries(allDiscoveries)
      } catch (err) {
        setError('Failed to load discoveries. Make sure the API server is running.')
        console.error('Discovery fetch error:', err)
      } finally {
        setIsLoading(false)
      }
    }
    fetchDiscoveries()
  }, [])

  const filteredDiscoveries = selectedType
    ? discoveries.filter((d) => d.discovery_type === selectedType)
    : discoveries

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white flex items-center gap-3">
          <Sparkles className="h-7 w-7 text-purple-400" />
          Discovery
        </h1>
        <p className="text-slate-400 mt-1">
          Hidden gems and rising stars our algorithms have identified
        </p>
      </div>

      {/* Explainer */}
      <div className="rounded-xl bg-gradient-to-r from-purple-500/10 via-aware-500/10 to-cyan-500/10 border border-purple-500/20 p-6">
        <div className="flex items-start gap-4">
          <div className="p-3 rounded-xl bg-purple-500/20">
            <Eye className="h-6 w-6 text-purple-400" />
          </div>
          <div>
            <h3 className="font-semibold text-white text-lg mb-2">Finding Alpha Before Others</h3>
            <p className="text-sm text-slate-400 mb-4">
              Our algorithms continuously scan for traders who show exceptional characteristics
              but haven't yet made it to the top of the leaderboard. These "hidden gems" often
              represent the best alpha opportunities before they become crowded.
            </p>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {Object.entries(discoveryTypes).map(([key, type]) => (
                <div key={key} className={cn('p-3 rounded-lg', type.bg, type.border, 'border')}>
                  <type.icon className={cn('h-5 w-5 mb-2', type.color)} />
                  <p className="text-sm font-medium text-white">{type.label}</p>
                  <p className="text-xs text-slate-500 mt-1">{type.description}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Filter */}
      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => setSelectedType(null)}
          className={cn(
            'px-4 py-2 text-sm font-medium rounded-lg transition-all',
            !selectedType
              ? 'bg-aware-500/20 text-aware-400 ring-1 ring-aware-500/50'
              : 'bg-slate-800/50 text-slate-400 hover:bg-slate-800'
          )}
        >
          All Types
        </button>
        {Object.entries(discoveryTypes).map(([key, type]) => (
          <button
            key={key}
            onClick={() => setSelectedType(key)}
            className={cn(
              'px-4 py-2 text-sm font-medium rounded-lg transition-all flex items-center gap-2',
              selectedType === key
                ? `${type.bg} ${type.color} ring-1 ${type.border}`
                : 'bg-slate-800/50 text-slate-400 hover:bg-slate-800'
            )}
          >
            <type.icon className="h-4 w-4" />
            {type.label}
          </button>
        ))}
      </div>

      {/* Loading State */}
      {isLoading && (
        <div className="rounded-xl bg-slate-900/50 border border-slate-800 p-12 flex items-center justify-center">
          <Loader2 className="h-8 w-8 text-aware-400 animate-spin" />
          <span className="ml-3 text-slate-400">Discovering hidden gems...</span>
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
      {!isLoading && !error && filteredDiscoveries.length === 0 && (
        <div className="rounded-xl bg-slate-900/50 border border-slate-800 p-12 text-center">
          <Sparkles className="h-12 w-12 text-slate-600 mx-auto mb-4" />
          <p className="text-slate-400">No discoveries found</p>
          <p className="text-sm text-slate-500 mt-1">
            Run the scoring job to discover hidden gems in the trader pool
          </p>
        </div>
      )}

      {/* Discoveries Grid */}
      {!isLoading && !error && filteredDiscoveries.length > 0 && (
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {filteredDiscoveries.map((discovery) => {
          const type = discoveryTypes[discovery.discovery_type as keyof typeof discoveryTypes] || discoveryTypes.HIDDEN_GEM
          const Icon = type.icon

          return (
            <Link
              key={discovery.id}
              href={`/traders/${discovery.username}`}
              className={cn(
                'rounded-xl border p-5 transition-all hover:shadow-lg hover:-translate-y-1',
                type.bg,
                type.border
              )}
            >
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-aware-400 to-aware-600 flex items-center justify-center text-xl font-bold text-white">
                    {discovery.username.charAt(0).toUpperCase()}
                  </div>
                  <div>
                    <p className="font-semibold text-white">{discovery.username}</p>
                    <div className="flex items-center gap-1 mt-0.5">
                      <Icon className={cn('h-4 w-4', type.color)} />
                      <span className={cn('text-xs font-medium', type.color)}>{type.label}</span>
                    </div>
                  </div>
                </div>
                <div className="text-right">
                  <div className="flex items-center gap-1">
                    <Star className="h-4 w-4 text-yellow-400 fill-yellow-400" />
                    <span className="text-lg font-bold text-white">{discovery.discovery_score}</span>
                  </div>
                  <p className="text-xs text-slate-500">Discovery Score</p>
                </div>
              </div>

              <p className="text-sm text-slate-300 mb-4 line-clamp-2">
                {discovery.reason}
              </p>

              <div className="grid grid-cols-3 gap-3 mb-4">
                <div className="text-center p-2 bg-slate-800/30 rounded-lg">
                  <p className="text-lg font-bold text-green-400">{discovery.recent_win_rate}%</p>
                  <p className="text-xs text-slate-500">Win Rate</p>
                </div>
                <div className="text-center p-2 bg-slate-800/30 rounded-lg">
                  <p className="text-lg font-bold text-aware-400">{discovery.recent_sharpe}</p>
                  <p className="text-xs text-slate-500">Sharpe</p>
                </div>
                <div className="text-center p-2 bg-slate-800/30 rounded-lg">
                  <p className="text-lg font-bold text-white">{discovery.total_trades}</p>
                  <p className="text-xs text-slate-500">Trades</p>
                </div>
              </div>

              <div className="flex items-center justify-between pt-3 border-t border-slate-800/50">
                <div className="flex items-center gap-4 text-xs text-slate-500">
                  <span>{discovery.days_active} days active</span>
                  <span>•</span>
                  <span>{discovery.specialty}</span>
                </div>
                <div className="flex items-center gap-1 text-green-400">
                  <TrendingUp className="h-4 w-4" />
                  <span className="text-sm font-medium">+${formatNumber(discovery.pnl_30d, 0)}</span>
                </div>
              </div>
            </Link>
          )
        })}
      </div>
      )}

      {/* CTA */}
      <div className="rounded-xl bg-slate-800/50 border border-slate-700 p-6 text-center">
        <Sparkles className="h-8 w-8 text-purple-400 mx-auto mb-3" />
        <h3 className="text-lg font-semibold text-white mb-2">Want More Discoveries?</h3>
        <p className="text-sm text-slate-400 mb-4 max-w-md mx-auto">
          Our algorithm finds new hidden gems daily. Subscribe to get alerts
          when we discover high-potential traders matching your interests.
        </p>
        <button className="px-6 py-2.5 bg-gradient-to-r from-purple-500 to-aware-500 text-white font-medium rounded-lg hover:opacity-90 transition-opacity">
          Enable Discovery Alerts
        </button>
      </div>
    </div>
  )
}
