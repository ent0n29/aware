'use client'

import { useState, useEffect } from 'react'
import {
  TrendingUp,
  Users,
  DollarSign,
  Activity,
  ArrowUpRight,
  ArrowDownRight,
  Loader2,
  AlertCircle,
} from 'lucide-react'
import { cn, formatNumber, formatCurrency, formatPercent } from '@/lib/utils'
import { StatsCard } from '@/components/dashboard/StatsCard'
import { TopTraders } from '@/components/dashboard/TopTraders'
import { RecentActivity } from '@/components/dashboard/RecentActivity'
import { IndexPerformance } from '@/components/dashboard/IndexPerformance'
import { ConsensusAlerts } from '@/components/dashboard/ConsensusAlerts'
import { api, DashboardStats, PSIIndex } from '@/lib/api'

interface DashboardData {
  stats: DashboardStats | null
  psi10: PSIIndex | null
  error: string | null
  isLoading: boolean
}

export default function DashboardPage() {
  const [data, setData] = useState<DashboardData>({
    stats: null,
    psi10: null,
    error: null,
    isLoading: true,
  })

  useEffect(() => {
    async function fetchDashboardData() {
      try {
        // Fetch stats and PSI-10 in parallel
        const [statsData, psi10Data] = await Promise.allSettled([
          api.getDashboardStats(),
          api.getPSI10(),
        ])

        setData({
          stats: statsData.status === 'fulfilled' ? statsData.value : null,
          psi10: psi10Data.status === 'fulfilled' ? psi10Data.value : null,
          error: null,
          isLoading: false,
        })
      } catch (err) {
        setData({
          stats: null,
          psi10: null,
          error: 'Failed to load dashboard data. Make sure the API server is running.',
          isLoading: false,
        })
        console.error('Dashboard fetch error:', err)
      }
    }
    fetchDashboardData()
  }, [])

  const { stats, psi10, error, isLoading } = data

  // Fallback values for display
  const displayStats = stats || {
    total_traders: 0,
    total_trades: 0,
    total_volume_usd: 0,
    trades_24h: 0,
    traders_24h: 0,
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Dashboard</h1>
          <p className="text-slate-400 mt-1">
            Real-time overview of smart money activity
          </p>
        </div>
        <div className="flex items-center gap-2 text-sm text-slate-500">
          {isLoading ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Activity className="w-4 h-4" />
          )}
          {isLoading ? 'Loading...' : 'Last updated: just now'}
        </div>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="rounded-xl bg-red-500/10 border border-red-500/30 p-4 flex items-center gap-3">
          <AlertCircle className="h-5 w-5 text-red-400 flex-shrink-0" />
          <div>
            <p className="text-red-400 text-sm font-medium">{error}</p>
            <p className="text-slate-500 text-xs mt-0.5">
              Run: <code className="bg-slate-800 px-1 rounded">cd aware-fund/services/api && uvicorn main:app --reload --port 8000</code>
            </p>
          </div>
        </div>
      )}

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatsCard
          title="Tracked Traders"
          value={formatNumber(displayStats.total_traders, 0)}
          icon={Users}
          trend={displayStats.traders_24h > 0 ? { value: displayStats.traders_24h, isPositive: true } : undefined}
          description="With scored activity"
        />
        <StatsCard
          title="Total Trades"
          value={formatNumber(displayStats.total_trades, 0)}
          icon={Activity}
          trend={displayStats.trades_24h > 0 ? { value: displayStats.trades_24h, isPositive: true } : undefined}
          description="Ingested trades"
        />
        <StatsCard
          title="Trading Volume"
          value={formatCurrency(displayStats.total_volume_usd)}
          icon={DollarSign}
          description="Total notional"
        />
        <StatsCard
          title="24h Trades"
          value={formatNumber(displayStats.trades_24h, 0)}
          icon={TrendingUp}
          description="Last 24 hours"
        />
      </div>

      {/* PSI Index Banner */}
      <div className="relative overflow-hidden rounded-2xl bg-gradient-to-r from-aware-600 via-aware-500 to-cyan-500 p-6">
        <div className="relative z-10 flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <span className="px-2 py-0.5 bg-white/20 rounded text-xs font-medium text-white">
                FLAGSHIP INDEX
              </span>
            </div>
            <h2 className="text-3xl font-bold text-white mb-1">
              PSI-10 Index
            </h2>
            <p className="text-aware-100">
              {psi10 ? `${psi10.trader_count} traders by Smart Money Score` : 'Top 10 traders by Smart Money Score'}
            </p>
          </div>
          <div className="text-right">
            {psi10 ? (
              <>
                <div className="text-4xl font-bold text-white">
                  {psi10.trader_count} Traders
                </div>
                <div className="text-aware-100 text-sm mt-1">
                  Total Weight: {(psi10.total_weight * 100).toFixed(0)}%
                </div>
              </>
            ) : (
              <div className="text-2xl font-bold text-white/60">
                {isLoading ? 'Loading...' : 'Not available'}
              </div>
            )}
          </div>
        </div>
        {/* Background decoration */}
        <div className="absolute top-0 right-0 w-64 h-64 bg-white/10 rounded-full blur-3xl -translate-y-1/2 translate-x-1/4" />
        <div className="absolute bottom-0 left-0 w-48 h-48 bg-cyan-400/20 rounded-full blur-3xl translate-y-1/2 -translate-x-1/4" />
      </div>

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Top Traders - Takes 2 columns */}
        <div className="lg:col-span-2">
          <TopTraders />
        </div>

        {/* Consensus Alerts */}
        <div>
          <ConsensusAlerts />
        </div>
      </div>

      {/* Secondary Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <IndexPerformance />
        <RecentActivity />
      </div>
    </div>
  )
}
