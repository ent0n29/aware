'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { Trophy, ExternalLink, TrendingUp, TrendingDown, Loader2 } from 'lucide-react'
import { cn, formatCurrency, formatNumber } from '@/lib/utils'
import { api, Trader } from '@/lib/api'

const tierColors: Record<string, string> = {
  Diamond: 'bg-gradient-to-r from-cyan-400 to-blue-400 text-slate-900',
  DIAMOND: 'bg-gradient-to-r from-cyan-400 to-blue-400 text-slate-900',
  Gold: 'bg-gradient-to-r from-yellow-400 to-amber-400 text-slate-900',
  GOLD: 'bg-gradient-to-r from-yellow-400 to-amber-400 text-slate-900',
  Silver: 'bg-gradient-to-r from-slate-300 to-slate-400 text-slate-900',
  SILVER: 'bg-gradient-to-r from-slate-300 to-slate-400 text-slate-900',
  Bronze: 'bg-gradient-to-r from-orange-400 to-amber-600 text-white',
  BRONZE: 'bg-gradient-to-r from-orange-400 to-amber-600 text-white',
}

const formatTier = (tier: string) => tier.charAt(0).toUpperCase() + tier.slice(1).toLowerCase()

export function TopTraders() {
  const [traders, setTraders] = useState<Trader[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function fetchTopTraders() {
      try {
        setIsLoading(true)
        const data = await api.getLeaderboard(5)
        setTraders(data)
        setError(null)
      } catch (err) {
        setError('Failed to load traders')
        console.error('TopTraders fetch error:', err)
      } finally {
        setIsLoading(false)
      }
    }
    fetchTopTraders()
  }, [])

  return (
    <div className="rounded-xl bg-slate-900/50 border border-slate-800 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between p-5 border-b border-slate-800">
        <div className="flex items-center gap-3">
          <div className="rounded-lg bg-yellow-500/10 p-2">
            <Trophy className="h-5 w-5 text-yellow-400" />
          </div>
          <div>
            <h3 className="font-semibold text-white">Top Traders</h3>
            <p className="text-xs text-slate-500">By Smart Money Score</p>
          </div>
        </div>
        <Link
          href="/leaderboard"
          className="flex items-center gap-1 text-sm text-aware-400 hover:text-aware-300 transition-colors"
        >
          View all
          <ExternalLink className="h-3.5 w-3.5" />
        </Link>
      </div>

      {/* Loading State */}
      {isLoading && (
        <div className="p-8 flex items-center justify-center">
          <Loader2 className="h-6 w-6 text-aware-400 animate-spin" />
          <span className="ml-2 text-slate-400 text-sm">Loading...</span>
        </div>
      )}

      {/* Error State */}
      {error && !isLoading && (
        <div className="p-6 text-center">
          <p className="text-slate-400 text-sm">{error}</p>
        </div>
      )}

      {/* Empty State */}
      {!isLoading && !error && traders.length === 0 && (
        <div className="p-8 text-center">
          <Trophy className="h-8 w-8 text-slate-600 mx-auto mb-2" />
          <p className="text-slate-400 text-sm">No traders scored yet</p>
          <p className="text-slate-500 text-xs mt-1">Run the scoring job to populate</p>
        </div>
      )}

      {/* Table */}
      {!isLoading && !error && traders.length > 0 && (
        <div className="divide-y divide-slate-800">
          {traders.map((trader) => (
            <Link
              key={trader.proxy_address || trader.username}
              href={`/traders/${trader.username || trader.proxy_address}`}
              className="flex items-center gap-4 p-4 hover:bg-slate-800/50 transition-colors"
            >
              {/* Rank */}
              <div className="w-8 text-center">
                {trader.rank <= 3 ? (
                  <span
                    className={cn(
                      'inline-flex items-center justify-center w-7 h-7 rounded-full text-sm font-bold',
                      trader.rank === 1 && 'bg-yellow-500/20 text-yellow-400',
                      trader.rank === 2 && 'bg-slate-400/20 text-slate-300',
                      trader.rank === 3 && 'bg-orange-500/20 text-orange-400'
                    )}
                  >
                    {trader.rank}
                  </span>
                ) : (
                  <span className="text-slate-500 font-medium">
                    {trader.rank}
                  </span>
                )}
              </div>

              {/* Avatar & Username */}
              <div className="flex items-center gap-3 flex-1">
                <div className="w-10 h-10 rounded-full bg-gradient-to-br from-aware-400 to-aware-600 flex items-center justify-center text-white font-semibold">
                  {(trader.username || trader.proxy_address || '?').charAt(0).toUpperCase()}
                </div>
                <div>
                  <p className="font-medium text-white">{trader.username || `${trader.proxy_address?.slice(0, 6)}...${trader.proxy_address?.slice(-4)}`}</p>
                  <span
                    className={cn(
                      'inline-flex px-2 py-0.5 text-xs font-medium rounded-full',
                      tierColors[trader.tier] || tierColors['BRONZE']
                    )}
                  >
                    {formatTier(trader.tier)}
                  </span>
                </div>
              </div>

              {/* Score */}
              <div className="text-right">
                <p className="text-lg font-bold text-white">{(trader.smart_money_score || 0).toFixed(1)}</p>
                <p className="text-xs text-slate-500">Score</p>
              </div>

              {/* Win Rate */}
              <div className="text-right w-20">
                <p className="font-medium text-white">{((trader.win_rate || 0) * 100).toFixed(1)}%</p>
                <p className="text-xs text-slate-500">Win Rate</p>
              </div>

              {/* Total P&L */}
              <div className="text-right w-24">
                <div
                  className={cn(
                    'flex items-center justify-end gap-1',
                    (trader.total_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400'
                  )}
                >
                  {(trader.total_pnl || 0) >= 0 ? (
                    <TrendingUp className="h-4 w-4" />
                  ) : (
                    <TrendingDown className="h-4 w-4" />
                  )}
                  <span className="font-medium">
                    {formatCurrency(Math.abs(trader.total_pnl || 0))}
                  </span>
                </div>
                <p className="text-xs text-slate-500">Total P&L</p>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
