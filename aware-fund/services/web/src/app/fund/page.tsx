'use client'

import { useState, useEffect } from 'react'
import {
  TrendingUp,
  TrendingDown,
  DollarSign,
  Users,
  Activity,
  PieChart,
  BarChart2,
  Loader2,
  AlertCircle,
  ArrowUpRight,
  ArrowDownRight,
} from 'lucide-react'
import { cn, formatCurrency, formatNumber } from '@/lib/utils'

// Types
interface FundOverview {
  fund_id: string
  nav: number
  capital: number
  position_value: number
  unrealized_pnl: number
  realized_pnl: number
  total_return: number
  open_positions: number
  num_traders: number
  last_updated: string
}

interface FundPosition {
  token_id: string
  market_slug: string
  outcome: string
  shares: number
  avg_entry_price: number
  current_price: number
  current_value: number
  unrealized_pnl: number
  pnl_pct: number
}

interface IndexConstituent {
  username: string
  weight: number
  total_score: number
  sharpe_ratio: number
  strategy_type: string
}

// Mock data for now (API endpoints will be added)
const mockOverview: FundOverview = {
  fund_id: 'psi-10-main',
  nav: 10000,
  capital: 10000,
  position_value: 0,
  unrealized_pnl: 0,
  realized_pnl: 0,
  total_return: 0,
  open_positions: 0,
  num_traders: 10,
  last_updated: new Date().toISOString(),
}

export default function FundPage() {
  const [overview, setOverview] = useState<FundOverview>(mockOverview)
  const [positions, setPositions] = useState<FundPosition[]>([])
  const [constituents, setConstituents] = useState<IndexConstituent[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function fetchFundData() {
      try {
        setIsLoading(true)
        setError(null)

        // API base URL (use environment variable in production)
        const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

        // Fetch fund overview
        const navResponse = await fetch(`${API_BASE}/api/fund/nav`)
        if (navResponse.ok) {
          const navData = await navResponse.json()
          setOverview({
            fund_id: navData.fund_id,
            nav: navData.nav,
            capital: navData.capital,
            position_value: navData.position_value,
            unrealized_pnl: navData.unrealized_pnl,
            realized_pnl: navData.realized_pnl,
            total_return: navData.total_return,
            open_positions: navData.open_positions,
            num_traders: 10,  // Will be fetched from index
            last_updated: navData.last_updated || new Date().toISOString(),
          })
        }

        // Fetch positions
        const posResponse = await fetch(`${API_BASE}/api/fund/positions`)
        if (posResponse.ok) {
          const posData = await posResponse.json()
          // API returns array directly, not wrapped in positions key
          setPositions(Array.isArray(posData) ? posData : posData.positions || [])
        }

        // Fetch index constituents
        const indexResponse = await fetch(`${API_BASE}/api/fund/index?index_type=PSI-10`)
        if (indexResponse.ok) {
          const indexData = await indexResponse.json()
          const mappedConstituents = (indexData.constituents || []).map((c: any) => ({
            username: c.username,
            weight: c.weight / 100,  // API returns percentage, convert to decimal
            total_score: c.smart_money_score,
            sharpe_ratio: c.sharpe_ratio,
            strategy_type: c.strategy_type,
          }))
          setConstituents(mappedConstituents)
        }

      } catch (err) {
        console.error('Fund data fetch error:', err)
        // Use mock data if API not available
        setOverview(mockOverview)
      } finally {
        setIsLoading(false)
      }
    }

    fetchFundData()
    // Refresh every 30 seconds
    const interval = setInterval(fetchFundData, 30000)
    return () => clearInterval(interval)
  }, [])

  const totalReturn = overview.nav - overview.capital
  const returnPct = overview.capital > 0 ? (totalReturn / overview.capital) * 100 : 0
  const isPositive = totalReturn >= 0

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-3">
            <PieChart className="h-7 w-7 text-aware-400" />
            AWARE Fund
          </h1>
          <p className="text-slate-400 mt-1">
            PSI-10 Smart Money Index Fund
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span className="px-3 py-1 rounded-full bg-green-500/10 text-green-400 text-sm font-medium">
            Active
          </span>
          <span className="text-xs text-slate-500">
            Updated {new Date(overview.last_updated).toLocaleTimeString()}
          </span>
        </div>
      </div>

      {/* Error State */}
      {error && (
        <div className="rounded-xl bg-red-500/10 border border-red-500/30 p-6 flex items-center gap-4">
          <AlertCircle className="h-6 w-6 text-red-400" />
          <div>
            <p className="text-red-400 font-medium">{error}</p>
          </div>
        </div>
      )}

      {/* Loading State */}
      {isLoading && (
        <div className="rounded-xl bg-slate-900/50 border border-slate-800 p-12 flex items-center justify-center">
          <Loader2 className="h-8 w-8 text-aware-400 animate-spin" />
          <span className="ml-3 text-slate-400">Loading fund data...</span>
        </div>
      )}

      {!isLoading && (
        <>
          {/* NAV Card - Hero */}
          <div className="rounded-xl bg-gradient-to-br from-aware-500/20 to-aware-600/10 border border-aware-500/30 p-6">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
              <div>
                <p className="text-slate-400 text-sm">Net Asset Value (NAV)</p>
                <div className="flex items-baseline gap-3 mt-1">
                  <span className="text-4xl font-bold text-white">
                    {formatCurrency(overview.nav)}
                  </span>
                  <span className={cn(
                    'flex items-center text-lg font-semibold',
                    isPositive ? 'text-green-400' : 'text-red-400'
                  )}>
                    {isPositive ? <ArrowUpRight className="h-5 w-5" /> : <ArrowDownRight className="h-5 w-5" />}
                    {returnPct.toFixed(2)}%
                  </span>
                </div>
                <p className="text-slate-500 text-sm mt-1">
                  Initial Capital: {formatCurrency(overview.capital)}
                </p>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="bg-slate-800/50 rounded-lg p-4 text-center">
                  <p className={cn(
                    'text-2xl font-bold',
                    overview.unrealized_pnl >= 0 ? 'text-green-400' : 'text-red-400'
                  )}>
                    {formatCurrency(overview.unrealized_pnl)}
                  </p>
                  <p className="text-xs text-slate-500">Unrealized P&L</p>
                </div>
                <div className="bg-slate-800/50 rounded-lg p-4 text-center">
                  <p className={cn(
                    'text-2xl font-bold',
                    overview.realized_pnl >= 0 ? 'text-green-400' : 'text-red-400'
                  )}>
                    {formatCurrency(overview.realized_pnl)}
                  </p>
                  <p className="text-xs text-slate-500">Realized P&L</p>
                </div>
              </div>
            </div>
          </div>

          {/* Stats Grid */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="rounded-xl bg-slate-900/50 border border-slate-800 p-4">
              <div className="flex items-center gap-3 mb-2">
                <div className="p-2 rounded-lg bg-blue-500/10">
                  <DollarSign className="h-5 w-5 text-blue-400" />
                </div>
                <span className="text-slate-400 text-sm">Position Value</span>
              </div>
              <p className="text-2xl font-bold text-white">
                {formatCurrency(overview.position_value)}
              </p>
            </div>

            <div className="rounded-xl bg-slate-900/50 border border-slate-800 p-4">
              <div className="flex items-center gap-3 mb-2">
                <div className="p-2 rounded-lg bg-green-500/10">
                  <Activity className="h-5 w-5 text-green-400" />
                </div>
                <span className="text-slate-400 text-sm">Open Positions</span>
              </div>
              <p className="text-2xl font-bold text-white">
                {overview.open_positions}
              </p>
            </div>

            <div className="rounded-xl bg-slate-900/50 border border-slate-800 p-4">
              <div className="flex items-center gap-3 mb-2">
                <div className="p-2 rounded-lg bg-purple-500/10">
                  <Users className="h-5 w-5 text-purple-400" />
                </div>
                <span className="text-slate-400 text-sm">Tracked Traders</span>
              </div>
              <p className="text-2xl font-bold text-white">
                {overview.num_traders}
              </p>
            </div>

            <div className="rounded-xl bg-slate-900/50 border border-slate-800 p-4">
              <div className="flex items-center gap-3 mb-2">
                <div className="p-2 rounded-lg bg-yellow-500/10">
                  <TrendingUp className="h-5 w-5 text-yellow-400" />
                </div>
                <span className="text-slate-400 text-sm">Total Return</span>
              </div>
              <p className={cn(
                'text-2xl font-bold',
                isPositive ? 'text-green-400' : 'text-red-400'
              )}>
                {isPositive ? '+' : ''}{returnPct.toFixed(2)}%
              </p>
            </div>
          </div>

          {/* Two Column Layout */}
          <div className="grid lg:grid-cols-2 gap-6">
            {/* Positions Table */}
            <div className="rounded-xl bg-slate-900/50 border border-slate-800 overflow-hidden">
              <div className="p-4 border-b border-slate-800">
                <h2 className="text-lg font-semibold text-white flex items-center gap-2">
                  <BarChart2 className="h-5 w-5 text-aware-400" />
                  Open Positions
                </h2>
              </div>

              {positions.length === 0 ? (
                <div className="p-8 text-center">
                  <Activity className="h-12 w-12 text-slate-600 mx-auto mb-4" />
                  <p className="text-slate-400">No open positions</p>
                  <p className="text-sm text-slate-500 mt-1">
                    Fund will open positions when traders in the index trade
                  </p>
                </div>
              ) : (
                <div className="divide-y divide-slate-800">
                  {positions.map((pos) => (
                    <div key={pos.token_id} className="p-4 hover:bg-slate-800/30">
                      <div className="flex justify-between items-start">
                        <div>
                          <p className="text-white font-medium">{pos.market_slug}</p>
                          <p className="text-sm text-slate-400">
                            {formatNumber(pos.shares, 2)} shares @ {pos.outcome}
                          </p>
                        </div>
                        <div className="text-right">
                          <p className={cn(
                            'font-semibold',
                            pos.unrealized_pnl >= 0 ? 'text-green-400' : 'text-red-400'
                          )}>
                            {formatCurrency(pos.unrealized_pnl)}
                          </p>
                          <p className="text-sm text-slate-500">
                            {formatCurrency(pos.current_value)}
                          </p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Index Constituents */}
            <div className="rounded-xl bg-slate-900/50 border border-slate-800 overflow-hidden">
              <div className="p-4 border-b border-slate-800">
                <h2 className="text-lg font-semibold text-white flex items-center gap-2">
                  <Users className="h-5 w-5 text-aware-400" />
                  PSI-10 Constituents
                </h2>
              </div>

              {constituents.length === 0 ? (
                <div className="p-8 text-center">
                  <Users className="h-12 w-12 text-slate-600 mx-auto mb-4" />
                  <p className="text-slate-400">No index data</p>
                  <p className="text-sm text-slate-500 mt-1">
                    Run the analytics pipeline to build the index
                  </p>
                </div>
              ) : (
                <div className="divide-y divide-slate-800">
                  {constituents.map((c, i) => (
                    <div key={c.username} className="p-4 hover:bg-slate-800/30 flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <span className="text-slate-500 font-medium w-6">{i + 1}</span>
                        <div className="w-8 h-8 rounded-full bg-gradient-to-br from-aware-400 to-aware-600 flex items-center justify-center text-white text-sm font-bold">
                          {c.username.charAt(0).toUpperCase()}
                        </div>
                        <div>
                          <p className="text-white font-medium">{c.username}</p>
                          <p className="text-xs text-slate-500">{c.strategy_type}</p>
                        </div>
                      </div>
                      <div className="text-right">
                        <p className="text-white font-medium">
                          {(c.weight * 100).toFixed(1)}%
                        </p>
                        <p className="text-xs text-slate-500">
                          Score: {c.total_score.toFixed(0)}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Fund Info */}
          <div className="rounded-xl bg-slate-800/30 border border-slate-800 p-6">
            <h3 className="text-lg font-semibold text-white mb-4">About the Fund</h3>
            <div className="grid md:grid-cols-3 gap-6 text-sm">
              <div>
                <p className="text-slate-400">Strategy</p>
                <p className="text-white mt-1">
                  Mirrors the top 10 traders by Smart Money Score, weighted equally
                </p>
              </div>
              <div>
                <p className="text-slate-400">Execution</p>
                <p className="text-white mt-1">
                  5-second delay after detecting trader trades, limit orders with market fallback
                </p>
              </div>
              <div>
                <p className="text-slate-400">Risk Controls</p>
                <p className="text-white mt-1">
                  Max 10% per position, $1,000 max market exposure, 10% max drawdown
                </p>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
