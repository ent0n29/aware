'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import {
  Trophy,
  Search,
  TrendingUp,
  TrendingDown,
  ChevronDown,
  Crown,
  Loader2,
  AlertCircle,
} from 'lucide-react'
import { cn, formatCurrency, formatNumber } from '@/lib/utils'
import { api, Trader } from '@/lib/api'

const tiers = ['All', 'Diamond', 'Gold', 'Silver', 'Bronze']

const tierStyles: Record<string, { bg: string; text: string; glow: string }> = {
  Diamond: { bg: 'bg-gradient-to-r from-cyan-400 to-blue-400', text: 'text-slate-900', glow: 'shadow-cyan-500/30' },
  DIAMOND: { bg: 'bg-gradient-to-r from-cyan-400 to-blue-400', text: 'text-slate-900', glow: 'shadow-cyan-500/30' },
  Gold: { bg: 'bg-gradient-to-r from-yellow-400 to-amber-400', text: 'text-slate-900', glow: 'shadow-yellow-500/30' },
  GOLD: { bg: 'bg-gradient-to-r from-yellow-400 to-amber-400', text: 'text-slate-900', glow: 'shadow-yellow-500/30' },
  Silver: { bg: 'bg-gradient-to-r from-slate-300 to-slate-400', text: 'text-slate-900', glow: '' },
  SILVER: { bg: 'bg-gradient-to-r from-slate-300 to-slate-400', text: 'text-slate-900', glow: '' },
  Bronze: { bg: 'bg-gradient-to-r from-orange-400 to-amber-600', text: 'text-white', glow: '' },
  BRONZE: { bg: 'bg-gradient-to-r from-orange-400 to-amber-600', text: 'text-white', glow: '' },
}

// Helper to capitalize tier
const formatTier = (tier: string) => tier.charAt(0).toUpperCase() + tier.slice(1).toLowerCase()

export default function LeaderboardPage() {
  const [traders, setTraders] = useState<Trader[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedTier, setSelectedTier] = useState('All')
  const [searchQuery, setSearchQuery] = useState('')
  const [sortBy, setSortBy] = useState<'smart_money_score' | 'total_pnl' | 'win_rate' | 'sharpe_ratio'>('smart_money_score')

  // Fetch data from API
  useEffect(() => {
    async function fetchLeaderboard() {
      try {
        setIsLoading(true)
        setError(null)
        const data = await api.getLeaderboard(100, selectedTier === 'All' ? undefined : selectedTier)
        setTraders(data)
      } catch (err) {
        setError('Failed to load leaderboard. Make sure the API server is running.')
        console.error('Leaderboard fetch error:', err)
      } finally {
        setIsLoading(false)
      }
    }
    fetchLeaderboard()
  }, [selectedTier])

  // Filter and sort locally
  const filteredTraders = traders
    .filter((t) => t.username.toLowerCase().includes(searchQuery.toLowerCase()))
    .sort((a, b) => (b[sortBy] || 0) - (a[sortBy] || 0))

  // Calculate stats
  const stats = {
    diamondCount: traders.filter((t) => t.tier.toUpperCase() === 'DIAMOND').length,
    totalPnl: traders.reduce((sum, t) => sum + (t.total_pnl || 0), 0),
    avgWinRate: traders.length > 0 ? traders.reduce((sum, t) => sum + (t.win_rate || 0), 0) / traders.length : 0,
    totalTrades: traders.reduce((sum, t) => sum + (t.total_trades || 0), 0),
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-3">
            <Trophy className="h-7 w-7 text-yellow-400" />
            Leaderboard
          </h1>
          <p className="text-slate-400 mt-1">
            Top traders ranked by Smart Money Score
          </p>
        </div>

        {/* Search */}
        <div className="relative max-w-xs w-full">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
          <input
            type="text"
            placeholder="Search traders..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full h-10 pl-9 pr-4 bg-slate-900 border border-slate-800 rounded-lg text-sm text-white placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-aware-500/50 focus:border-aware-500"
          />
        </div>
      </div>

      {/* Tier Filter */}
      <div className="flex flex-wrap items-center gap-2">
        {tiers.map((tier) => (
          <button
            key={tier}
            onClick={() => setSelectedTier(tier)}
            className={cn(
              'px-4 py-2 text-sm font-medium rounded-lg transition-all',
              selectedTier === tier
                ? 'bg-aware-500/20 text-aware-400 ring-1 ring-aware-500/50'
                : 'bg-slate-800/50 text-slate-400 hover:bg-slate-800 hover:text-white'
            )}
          >
            {tier}
            {tier !== 'All' && traders.length > 0 && (
              <span className="ml-2 text-xs text-slate-500">
                ({traders.filter((t) => t.tier.toUpperCase() === tier.toUpperCase()).length})
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Error State */}
      {error && (
        <div className="rounded-xl bg-red-500/10 border border-red-500/30 p-6 flex items-center gap-4">
          <AlertCircle className="h-6 w-6 text-red-400" />
          <div>
            <p className="text-red-400 font-medium">{error}</p>
            <p className="text-sm text-slate-400 mt-1">
              Start the API server: <code className="bg-slate-800 px-2 py-0.5 rounded">cd aware-fund/services/api && uvicorn main:app --reload</code>
            </p>
          </div>
        </div>
      )}

      {/* Loading State */}
      {isLoading && (
        <div className="rounded-xl bg-slate-900/50 border border-slate-800 p-12 flex items-center justify-center">
          <Loader2 className="h-8 w-8 text-aware-400 animate-spin" />
          <span className="ml-3 text-slate-400">Loading leaderboard...</span>
        </div>
      )}

      {/* Table */}
      {!isLoading && !error && (
        <div className="rounded-xl bg-slate-900/50 border border-slate-800 overflow-hidden">
          {/* Table Header */}
          <div className="grid grid-cols-12 gap-4 p-4 bg-slate-800/50 text-sm font-medium text-slate-400 border-b border-slate-800">
            <div className="col-span-1 text-center">#</div>
            <div className="col-span-3">Trader</div>
            <div
              className="col-span-2 text-right cursor-pointer hover:text-white flex items-center justify-end gap-1"
              onClick={() => setSortBy('smart_money_score')}
            >
              Score
              {sortBy === 'smart_money_score' && <ChevronDown className="h-4 w-4" />}
            </div>
            <div
              className="col-span-2 text-right cursor-pointer hover:text-white flex items-center justify-end gap-1"
              onClick={() => setSortBy('total_pnl')}
            >
              Total P&L
              {sortBy === 'total_pnl' && <ChevronDown className="h-4 w-4" />}
            </div>
            <div
              className="col-span-1 text-right cursor-pointer hover:text-white flex items-center justify-end gap-1"
              onClick={() => setSortBy('win_rate')}
            >
              Win %
              {sortBy === 'win_rate' && <ChevronDown className="h-4 w-4" />}
            </div>
            <div
              className="col-span-1 text-right cursor-pointer hover:text-white flex items-center justify-end gap-1"
              onClick={() => setSortBy('sharpe_ratio')}
            >
              Sharpe
              {sortBy === 'sharpe_ratio' && <ChevronDown className="h-4 w-4" />}
            </div>
            <div className="col-span-2 text-right">Trades</div>
          </div>

          {/* Empty State */}
          {filteredTraders.length === 0 && (
            <div className="p-12 text-center">
              <Trophy className="h-12 w-12 text-slate-600 mx-auto mb-4" />
              <p className="text-slate-400">No traders found</p>
              <p className="text-sm text-slate-500 mt-1">
                {traders.length === 0
                  ? 'Run the scoring job to populate the leaderboard'
                  : 'Try adjusting your filters'}
              </p>
            </div>
          )}

          {/* Table Body */}
          <div className="divide-y divide-slate-800">
            {filteredTraders.map((trader) => {
              const tierStyle = tierStyles[trader.tier] || tierStyles['BRONZE']
              return (
                <Link
                  key={trader.proxy_address || trader.username}
                  href={`/traders/${trader.username || trader.proxy_address}`}
                  className="grid grid-cols-12 gap-4 p-4 items-center hover:bg-slate-800/30 transition-colors"
                >
                  {/* Rank */}
                  <div className="col-span-1 text-center">
                    {trader.rank === 1 && (
                      <Crown className="w-6 h-6 text-yellow-400 mx-auto" />
                    )}
                    {trader.rank === 2 && (
                      <span className="inline-flex items-center justify-center w-7 h-7 rounded-full bg-slate-300/20 text-slate-300 font-bold">
                        2
                      </span>
                    )}
                    {trader.rank === 3 && (
                      <span className="inline-flex items-center justify-center w-7 h-7 rounded-full bg-orange-500/20 text-orange-400 font-bold">
                        3
                      </span>
                    )}
                    {trader.rank > 3 && (
                      <span className="text-slate-500 font-medium">{trader.rank}</span>
                    )}
                  </div>

                  {/* Trader */}
                  <div className="col-span-3 flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-gradient-to-br from-aware-400 to-aware-600 flex items-center justify-center text-white font-bold">
                      {(trader.username || trader.proxy_address || '?').charAt(0).toUpperCase()}
                    </div>
                    <div>
                      <p className="font-medium text-white">{trader.username || `${trader.proxy_address?.slice(0, 6)}...${trader.proxy_address?.slice(-4)}`}</p>
                      <span
                        className={cn(
                          'inline-flex px-2 py-0.5 text-xs font-medium rounded-full shadow-lg',
                          tierStyle.bg,
                          tierStyle.text,
                          tierStyle.glow
                        )}
                      >
                        {formatTier(trader.tier)}
                      </span>
                    </div>
                  </div>

                  {/* Score */}
                  <div className="col-span-2 text-right">
                    <span className="text-lg font-bold text-white">
                      {(trader.smart_money_score || 0).toFixed(1)}
                    </span>
                  </div>

                  {/* Total P&L */}
                  <div className="col-span-2 text-right">
                    <span className={cn(
                      'font-semibold',
                      (trader.total_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'
                    )}>
                      {formatCurrency(trader.total_pnl || 0)}
                    </span>
                  </div>

                  {/* Win Rate */}
                  <div className="col-span-1 text-right">
                    <span className="text-white">
                      {((trader.win_rate || 0) * 100).toFixed(1)}%
                    </span>
                  </div>

                  {/* Sharpe */}
                  <div className="col-span-1 text-right">
                    <span className="text-slate-300">
                      {(trader.sharpe_ratio || 0).toFixed(2)}
                    </span>
                  </div>

                  {/* Trades */}
                  <div className="col-span-2 text-right">
                    <span className="text-slate-400">
                      {formatNumber(trader.total_trades || 0, 0)}
                    </span>
                  </div>
                </Link>
              )
            })}
          </div>
        </div>
      )}

      {/* Stats Summary */}
      {!isLoading && !error && traders.length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="rounded-lg bg-slate-800/50 p-4 text-center">
            <p className="text-3xl font-bold text-white">{stats.diamondCount}</p>
            <p className="text-sm text-cyan-400">Diamond Traders</p>
          </div>
          <div className="rounded-lg bg-slate-800/50 p-4 text-center">
            <p className="text-3xl font-bold text-white">{formatCurrency(stats.totalPnl)}</p>
            <p className="text-sm text-green-400">Combined P&L</p>
          </div>
          <div className="rounded-lg bg-slate-800/50 p-4 text-center">
            <p className="text-3xl font-bold text-white">{(stats.avgWinRate * 100).toFixed(1)}%</p>
            <p className="text-sm text-aware-400">Avg Win Rate</p>
          </div>
          <div className="rounded-lg bg-slate-800/50 p-4 text-center">
            <p className="text-3xl font-bold text-white">{formatNumber(stats.totalTrades, 0)}</p>
            <p className="text-sm text-slate-400">Total Trades</p>
          </div>
        </div>
      )}
    </div>
  )
}
