'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { useParams } from 'next/navigation'
import {
  ArrowLeft,
  Trophy,
  TrendingUp,
  TrendingDown,
  Target,
  Clock,
  BarChart3,
  Activity,
  Star,
  Shield,
  AlertTriangle,
  Loader2,
} from 'lucide-react'
import { cn, formatCurrency, formatNumber, formatPercent, getTimeAgo } from '@/lib/utils'
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from 'recharts'
import { api, TraderProfile } from '@/lib/api'

// Performance data (placeholder - will be populated from API when available)
const mockPerformance = [
  { date: 'Aug', pnl: 180000 },
  { date: 'Sep', pnl: 320000 },
  { date: 'Oct', pnl: 580000 },
  { date: 'Nov', pnl: 890000 },
  { date: 'Dec', pnl: 1250000 },
]

// Category breakdown (placeholder - will be populated from API when available)
const mockCategoryData = [
  { name: 'Crypto', value: 45, trades: 694, win_rate: 82 },
  { name: 'Politics', value: 30, trades: 463, win_rate: 76 },
  { name: 'Sports', value: 15, trades: 231, win_rate: 71 },
  { name: 'Other', value: 10, trades: 155, win_rate: 68 },
]

// Open positions (placeholder - will be populated from API when available)
const mockPositions = [
  { market: 'Will BTC > $100K by March 2025?', outcome: 'Yes', size: 45000, entry: 0.52, current: 0.68, pnl: 7200 },
  { market: 'Will Trump win 2024 election?', outcome: 'Yes', size: 32000, entry: 0.48, current: 0.92, pnl: 14080 },
  { market: 'Will Fed cut rates in Jan?', outcome: 'No', size: 28000, entry: 0.35, current: 0.41, pnl: 1680 },
]

// Recent trades (placeholder - will be populated from API when available)
const mockRecentTrades = [
  { market: 'ETH > $4K by EOY', outcome: 'Yes', side: 'BUY', size: 8500, price: 0.62, time: '2h ago' },
  { market: 'BTC ATH in December', outcome: 'Yes', side: 'SELL', size: 12000, price: 0.89, time: '5h ago' },
  { market: 'SpaceX launch success', outcome: 'Yes', side: 'BUY', size: 5200, price: 0.78, time: '8h ago' },
]

const COLORS = ['#0ea5e9', '#8b5cf6', '#f59e0b', '#64748b']

const tierStyles: Record<string, string> = {
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

export default function TraderProfilePage() {
  const params = useParams()
  const [activeTab, setActiveTab] = useState<'overview' | 'positions' | 'history'>('overview')
  const [trader, setTrader] = useState<TraderProfile | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function fetchTrader() {
      const username = params.username as string
      if (!username) return

      try {
        setIsLoading(true)
        setError(null)
        const data = await api.getTrader(username)
        setTrader(data)
      } catch (err) {
        setError('Failed to load trader profile. Make sure the API server is running.')
        console.error('Trader fetch error:', err)
      } finally {
        setIsLoading(false)
      }
    }
    fetchTrader()
  }, [params.username])

  // Loading state
  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Loader2 className="h-8 w-8 text-aware-400 animate-spin" />
        <span className="ml-3 text-slate-400">Loading trader profile...</span>
      </div>
    )
  }

  // Error state
  if (error || !trader) {
    return (
      <div className="space-y-6">
        <Link
          href="/leaderboard"
          className="inline-flex items-center gap-2 text-sm text-slate-400 hover:text-white transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Leaderboard
        </Link>
        <div className="rounded-xl bg-red-500/10 border border-red-500/30 p-6">
          <p className="text-red-400 font-medium">{error || 'Trader not found'}</p>
          <p className="text-sm text-slate-400 mt-2">
            Start the API server: <code className="bg-slate-800 px-2 py-0.5 rounded">cd aware-fund/services/api && uvicorn main:app --reload</code>
          </p>
        </div>
      </div>
    )
  }

  // Compute derived values
  const avgTradeSize = trader.total_trades > 0 ? trader.total_volume / trader.total_trades : 0

  return (
    <div className="space-y-6">
      {/* Back Button */}
      <Link
        href="/leaderboard"
        className="inline-flex items-center gap-2 text-sm text-slate-400 hover:text-white transition-colors"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to Leaderboard
      </Link>

      {/* Profile Header */}
      <div className="rounded-xl bg-slate-900/50 border border-slate-800 p-6">
        <div className="flex flex-col md:flex-row md:items-start justify-between gap-6">
          {/* Left: Avatar & Info */}
          <div className="flex items-start gap-4">
            <div className="relative">
              <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-aware-400 to-aware-600 flex items-center justify-center text-3xl font-bold text-white">
                {(trader.username || trader.proxy_address || '?').charAt(0).toUpperCase()}
              </div>
            </div>
            <div>
              <div className="flex items-center gap-3">
                <h1 className="text-2xl font-bold text-white">{trader.username || `${trader.proxy_address?.slice(0, 6)}...${trader.proxy_address?.slice(-4)}`}</h1>
                <span className={cn('px-3 py-1 text-sm font-semibold rounded-full', tierStyles[trader.tier] || tierStyles['BRONZE'])}>
                  {formatTier(trader.tier)}
                </span>
              </div>
              <p className="text-slate-500 text-sm mt-1 font-mono">{trader.proxy_address?.slice(0, 10)}...{trader.proxy_address?.slice(-8)}</p>
              <div className="flex items-center gap-4 mt-3">
                <div className="flex items-center gap-1 text-sm text-slate-400">
                  <Target className="h-4 w-4" />
                  {trader.strategy_type || 'Multi-category'}
                </div>
                <div className="flex items-center gap-1 text-sm text-slate-400">
                  <Clock className="h-4 w-4" />
                  {trader.days_active || 0} days active
                </div>
              </div>
            </div>
          </div>

          {/* Right: Key Stats */}
          <div className="flex gap-6">
            <div className="text-center">
              <p className="text-3xl font-bold text-white">{(trader.smart_money_score || 0).toFixed(1)}</p>
              <p className="text-sm text-slate-500">Smart Money Score</p>
            </div>
            <div className="text-center">
              <p className={cn('text-3xl font-bold', (trader.total_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400')}>
                {formatCurrency(trader.total_pnl || 0)}
              </p>
              <p className="text-sm text-slate-500">Total P&L</p>
            </div>
            <div className="text-center">
              <p className="text-3xl font-bold text-white">{trader.unique_markets || 0}</p>
              <p className="text-sm text-slate-500">Markets</p>
            </div>
          </div>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
        <StatBox label="Profitability" value={`${((trader.profitability_score || 0) * 100).toFixed(0)}%`} icon={Target} color="text-green-400" />
        <StatBox label="Risk-Adjusted" value={`${((trader.risk_adjusted_score || 0) * 100).toFixed(0)}%`} icon={BarChart3} color="text-aware-400" />
        <StatBox label="Total Trades" value={formatNumber(trader.total_trades || 0, 0)} icon={Activity} color="text-purple-400" />
        <StatBox label="Avg Trade" value={formatCurrency(avgTradeSize)} icon={TrendingUp} color="text-cyan-400" />
        <StatBox label="Consistency" value={`${((trader.consistency_score || 0) * 100).toFixed(0)}%`} icon={Shield} color="text-emerald-400" />
        <StatBox label="Track Record" value={`${((trader.track_record_score || 0) * 100).toFixed(0)}%`} icon={Star} color="text-yellow-400" />
      </div>

      {/* Tabs */}
      <div className="flex gap-1 p-1 bg-slate-800/50 rounded-lg w-fit">
        {['overview', 'positions', 'history'].map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab as any)}
            className={cn(
              'px-4 py-2 text-sm font-medium rounded-md transition-all capitalize',
              activeTab === tab
                ? 'bg-aware-500 text-white'
                : 'text-slate-400 hover:text-white'
            )}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {activeTab === 'overview' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Performance Chart */}
          <div className="rounded-xl bg-slate-900/50 border border-slate-800 p-5">
            <h3 className="text-lg font-semibold text-white mb-4">Cumulative P&L</h3>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={mockPerformance}>
                  <defs>
                    <linearGradient id="colorPnl" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#22c55e" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="date" axisLine={false} tickLine={false} tick={{ fill: '#64748b', fontSize: 12 }} />
                  <YAxis axisLine={false} tickLine={false} tick={{ fill: '#64748b', fontSize: 12 }} tickFormatter={(v) => `$${v / 1000}K`} />
                  <Tooltip contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '8px' }} />
                  <Area type="monotone" dataKey="pnl" stroke="#22c55e" strokeWidth={2} fill="url(#colorPnl)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Category Breakdown */}
          <div className="rounded-xl bg-slate-900/50 border border-slate-800 p-5">
            <h3 className="text-lg font-semibold text-white mb-4">Category Breakdown</h3>
            <div className="flex items-center gap-8">
              <div className="w-40 h-40">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={mockCategoryData}
                      innerRadius={45}
                      outerRadius={70}
                      paddingAngle={4}
                      dataKey="value"
                    >
                      {mockCategoryData.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                      ))}
                    </Pie>
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <div className="flex-1 space-y-3">
                {mockCategoryData.map((cat, i) => (
                  <div key={cat.name} className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <div className="w-3 h-3 rounded-full" style={{ backgroundColor: COLORS[i] }} />
                      <span className="text-sm text-slate-300">{cat.name}</span>
                    </div>
                    <div className="text-right">
                      <span className="text-sm font-medium text-white">{cat.value}%</span>
                      <span className="text-xs text-green-400 ml-2">({cat.win_rate}% win)</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'positions' && (
        <div className="rounded-xl bg-slate-900/50 border border-slate-800 overflow-hidden">
          <div className="p-4 border-b border-slate-800">
            <h3 className="font-semibold text-white">Open Positions</h3>
          </div>
          <div className="divide-y divide-slate-800">
            {mockPositions.map((pos, i) => (
              <div key={i} className="p-4 grid grid-cols-6 gap-4 items-center">
                <div className="col-span-2">
                  <p className="text-sm text-white font-medium">{pos.market}</p>
                  <span className="text-xs text-aware-400">{pos.outcome}</span>
                </div>
                <div className="text-right">
                  <p className="text-sm text-white">{formatCurrency(pos.size)}</p>
                  <p className="text-xs text-slate-500">Size</p>
                </div>
                <div className="text-right">
                  <p className="text-sm text-white">{(pos.entry * 100).toFixed(0)}¢</p>
                  <p className="text-xs text-slate-500">Entry</p>
                </div>
                <div className="text-right">
                  <p className="text-sm text-white">{(pos.current * 100).toFixed(0)}¢</p>
                  <p className="text-xs text-slate-500">Current</p>
                </div>
                <div className="text-right">
                  <p className={cn('text-sm font-medium', pos.pnl >= 0 ? 'text-green-400' : 'text-red-400')}>
                    {pos.pnl >= 0 ? '+' : ''}{formatCurrency(pos.pnl)}
                  </p>
                  <p className="text-xs text-slate-500">Unrealized</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {activeTab === 'history' && (
        <div className="rounded-xl bg-slate-900/50 border border-slate-800 overflow-hidden">
          <div className="p-4 border-b border-slate-800">
            <h3 className="font-semibold text-white">Recent Trades</h3>
          </div>
          <div className="divide-y divide-slate-800">
            {mockRecentTrades.map((trade, i) => (
              <div key={i} className="p-4 flex items-center gap-4">
                <div className={cn(
                  'p-2 rounded-lg',
                  trade.side === 'BUY' ? 'bg-green-500/10' : 'bg-red-500/10'
                )}>
                  {trade.side === 'BUY' ? (
                    <TrendingUp className="h-4 w-4 text-green-400" />
                  ) : (
                    <TrendingDown className="h-4 w-4 text-red-400" />
                  )}
                </div>
                <div className="flex-1">
                  <p className="text-sm text-white">{trade.market}</p>
                  <div className="flex items-center gap-2 text-xs text-slate-500">
                    <span className={trade.side === 'BUY' ? 'text-green-400' : 'text-red-400'}>{trade.side}</span>
                    <span>•</span>
                    <span>{trade.outcome}</span>
                    <span>•</span>
                    <span>{trade.time}</span>
                  </div>
                </div>
                <div className="text-right">
                  <p className="text-sm font-medium text-white">{formatCurrency(trade.size)}</p>
                  <p className="text-xs text-slate-500">@ {(trade.price * 100).toFixed(0)}¢</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function StatBox({ label, value, icon: Icon, color }: { label: string; value: string; icon: any; color: string }) {
  return (
    <div className="rounded-lg bg-slate-800/50 p-4">
      <div className="flex items-center gap-2 mb-2">
        <Icon className={cn('h-4 w-4', color)} />
        <span className="text-xs text-slate-500">{label}</span>
      </div>
      <p className="text-xl font-bold text-white">{value}</p>
    </div>
  )
}
