'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import {
  Layers,
  TrendingUp,
  TrendingDown,
  Users,
  Zap,
  DollarSign,
  Loader2,
  AlertCircle,
  Filter,
} from 'lucide-react'
import { cn, formatCurrency, formatNumber } from '@/lib/utils'
import { api, FundInfo } from '@/lib/api'

// Fund metadata
const fundMeta: Record<string, { icon: typeof Users; description: string; color: string }> = {
  'PSI-10': {
    icon: Users,
    description: 'Top 10 Smart Money traders',
    color: 'from-blue-500/20 to-cyan-500/20',
  },
  'PSI-25': {
    icon: Users,
    description: 'Top 25 Smart Money traders',
    color: 'from-blue-500/20 to-indigo-500/20',
  },
  'PSI-CRYPTO': {
    icon: Zap,
    description: 'Crypto market specialists',
    color: 'from-orange-500/20 to-yellow-500/20',
  },
  'PSI-POLITICS': {
    icon: Users,
    description: 'Political markets experts',
    color: 'from-red-500/20 to-pink-500/20',
  },
  'PSI-SPORTS': {
    icon: Users,
    description: 'Sports betting specialists',
    color: 'from-green-500/20 to-emerald-500/20',
  },
  'ALPHA-ARB': {
    icon: Zap,
    description: 'Complete-set arbitrage strategy',
    color: 'from-purple-500/20 to-violet-500/20',
  },
  'ALPHA-INSIDER': {
    icon: Zap,
    description: 'Insider activity signals',
    color: 'from-yellow-500/20 to-amber-500/20',
  },
  'ALPHA-EDGE': {
    icon: Zap,
    description: 'ML edge predictions',
    color: 'from-cyan-500/20 to-teal-500/20',
  },
}

export default function AllFundsPage() {
  const [funds, setFunds] = useState<FundInfo[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filterType, setFilterType] = useState<'ALL' | 'MIRROR' | 'ACTIVE'>('ALL')

  // Fetch funds
  useEffect(() => {
    async function fetchFunds() {
      try {
        const data = await api.getFunds()
        setFunds(data.funds)
      } catch (err) {
        console.error('Failed to fetch funds:', err)
        setError('Failed to load funds')
      } finally {
        setIsLoading(false)
      }
    }
    fetchFunds()
  }, [])

  // Filter funds
  const filteredFunds = filterType === 'ALL'
    ? funds
    : funds.filter(f => f.fund_type === filterType)

  // Calculate totals
  const totalAUM = funds.reduce((sum, f) => sum + f.total_aum, 0)
  const avgPerformance = funds.length > 0
    ? funds.reduce((sum, f) => sum + f.performance_30d, 0) / funds.length
    : 0

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-3">
            <Layers className="h-7 w-7 text-aware-400" />
            All Funds
          </h1>
          <p className="text-slate-400 mt-1">
            Explore and compare all AWARE investment funds
          </p>
        </div>

        {/* Filter */}
        <div className="flex items-center gap-2 bg-slate-800/50 p-1 rounded-lg">
          {['ALL', 'MIRROR', 'ACTIVE'].map((type) => (
            <button
              key={type}
              onClick={() => setFilterType(type as typeof filterType)}
              className={cn(
                'px-4 py-2 text-sm font-medium rounded-md transition-all',
                filterType === type
                  ? 'bg-aware-500 text-white'
                  : 'text-slate-400 hover:text-white hover:bg-slate-700'
              )}
            >
              {type === 'ALL' ? 'All Funds' : `${type} Funds`}
            </button>
          ))}
        </div>
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="rounded-xl bg-slate-900/50 border border-slate-800 p-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-aware-500/20 flex items-center justify-center">
              <Layers className="w-5 h-5 text-aware-400" />
            </div>
            <div>
              <p className="text-2xl font-bold text-white">{funds.length}</p>
              <p className="text-sm text-slate-400">Total Funds</p>
            </div>
          </div>
        </div>

        <div className="rounded-xl bg-slate-900/50 border border-slate-800 p-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-green-500/20 flex items-center justify-center">
              <DollarSign className="w-5 h-5 text-green-400" />
            </div>
            <div>
              <p className="text-2xl font-bold text-white">{formatCurrency(totalAUM)}</p>
              <p className="text-sm text-slate-400">Total AUM</p>
            </div>
          </div>
        </div>

        <div className="rounded-xl bg-slate-900/50 border border-slate-800 p-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-blue-500/20 flex items-center justify-center">
              <Users className="w-5 h-5 text-blue-400" />
            </div>
            <div>
              <p className="text-2xl font-bold text-white">
                {funds.filter(f => f.fund_type === 'MIRROR').length}
              </p>
              <p className="text-sm text-slate-400">Mirror Funds</p>
            </div>
          </div>
        </div>

        <div className="rounded-xl bg-slate-900/50 border border-slate-800 p-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-purple-500/20 flex items-center justify-center">
              <Zap className="w-5 h-5 text-purple-400" />
            </div>
            <div>
              <p className="text-2xl font-bold text-white">
                {funds.filter(f => f.fund_type === 'ACTIVE').length}
              </p>
              <p className="text-sm text-slate-400">Active Funds</p>
            </div>
          </div>
        </div>
      </div>

      {/* Error State */}
      {error && (
        <div className="rounded-xl bg-red-500/10 border border-red-500/30 p-4 flex items-center gap-3">
          <AlertCircle className="h-5 w-5 text-red-400" />
          <p className="text-red-400">{error}</p>
        </div>
      )}

      {/* Loading State */}
      {isLoading && (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div key={i} className="rounded-xl bg-slate-900/50 border border-slate-800 p-6 animate-pulse">
              <div className="flex items-center gap-3 mb-4">
                <div className="w-12 h-12 rounded-xl bg-slate-700" />
                <div>
                  <div className="h-5 w-24 bg-slate-700 rounded mb-2" />
                  <div className="h-4 w-32 bg-slate-700 rounded" />
                </div>
              </div>
              <div className="space-y-3">
                <div className="h-4 w-full bg-slate-700 rounded" />
                <div className="h-4 w-3/4 bg-slate-700 rounded" />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Fund Cards */}
      {!isLoading && (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredFunds.map((fund) => {
            const meta = fundMeta[fund.fund_id] || {
              icon: Layers,
              description: fund.description,
              color: 'from-slate-500/20 to-slate-600/20',
            }
            const Icon = meta.icon

            return (
              <Link
                key={fund.fund_id}
                href={`/fund?type=${fund.fund_id}`}
                className={cn(
                  'rounded-xl border border-slate-800 p-6 transition-all',
                  'hover:border-slate-700 hover:shadow-lg hover:shadow-slate-900/50',
                  'bg-gradient-to-br',
                  meta.color
                )}
              >
                {/* Header */}
                <div className="flex items-start justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <div className="w-12 h-12 rounded-xl bg-slate-800/80 flex items-center justify-center">
                      <Icon className="w-6 h-6 text-white" />
                    </div>
                    <div>
                      <h3 className="font-semibold text-white">{fund.name}</h3>
                      <span className={cn(
                        'text-xs px-2 py-0.5 rounded-full',
                        fund.fund_type === 'MIRROR'
                          ? 'bg-blue-500/20 text-blue-400'
                          : 'bg-purple-500/20 text-purple-400'
                      )}>
                        {fund.fund_type}
                      </span>
                    </div>
                  </div>

                  {/* Performance Badge */}
                  <div className={cn(
                    'flex items-center gap-1 px-2 py-1 rounded-lg',
                    fund.performance_30d >= 0 ? 'bg-green-500/20' : 'bg-red-500/20'
                  )}>
                    {fund.performance_30d >= 0 ? (
                      <TrendingUp className="w-4 h-4 text-green-400" />
                    ) : (
                      <TrendingDown className="w-4 h-4 text-red-400" />
                    )}
                    <span className={cn(
                      'text-sm font-medium',
                      fund.performance_30d >= 0 ? 'text-green-400' : 'text-red-400'
                    )}>
                      {fund.performance_30d >= 0 ? '+' : ''}{fund.performance_30d.toFixed(1)}%
                    </span>
                  </div>
                </div>

                {/* Description */}
                <p className="text-sm text-slate-400 mb-4 line-clamp-2">
                  {meta.description}
                </p>

                {/* Stats */}
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-xs text-slate-500">NAV</p>
                    <p className="text-lg font-semibold text-white">
                      {formatCurrency(fund.nav_per_share)}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-slate-500">AUM</p>
                    <p className="text-lg font-semibold text-white">
                      {formatNumber(fund.total_aum)}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-slate-500">Sharpe</p>
                    <p className={cn(
                      'text-lg font-semibold',
                      fund.sharpe_ratio >= 1 ? 'text-green-400' :
                      fund.sharpe_ratio >= 0 ? 'text-yellow-400' : 'text-red-400'
                    )}>
                      {fund.sharpe_ratio.toFixed(2)}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-slate-500">Max DD</p>
                    <p className="text-lg font-semibold text-red-400">
                      {fund.max_drawdown.toFixed(1)}%
                    </p>
                  </div>
                </div>

                {/* Fees */}
                <div className="mt-4 pt-4 border-t border-slate-700/50 flex justify-between text-xs text-slate-500">
                  <span>Mgmt Fee: {fund.management_fee}%</span>
                  <span>Perf Fee: {fund.performance_fee}%</span>
                </div>
              </Link>
            )
          })}
        </div>
      )}

      {/* Empty State */}
      {!isLoading && filteredFunds.length === 0 && (
        <div className="rounded-xl bg-slate-900/50 border border-slate-800 p-12 text-center">
          <Layers className="w-12 h-12 text-slate-600 mx-auto mb-4" />
          <h3 className="text-lg font-semibold text-white mb-2">No Funds Found</h3>
          <p className="text-slate-400">
            {filterType !== 'ALL'
              ? `No ${filterType.toLowerCase()} funds are currently available.`
              : 'No funds are currently available.'}
          </p>
        </div>
      )}
    </div>
  )
}
