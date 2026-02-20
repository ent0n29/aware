'use client'

import { Suspense, useState, useEffect } from 'react'
import { useSearchParams } from 'next/navigation'
import Link from 'next/link'
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
  ChevronDown,
  Zap,
} from 'lucide-react'
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts'
import { cn, formatCurrency, formatNumber, formatPercent } from '@/lib/utils'
import { NAVChart } from '@/components/fund/NAVChart'

// Mock chart data for fund comparison (will be replaced with real data)
const mockComparisonData = [
  { date: 'Nov 1', 'PSI-10': 100, 'PSI-25': 100, 'PSI-CRYPTO': 100, 'ALPHA-ARB': 100 },
  { date: 'Nov 8', 'PSI-10': 102, 'PSI-25': 101, 'PSI-CRYPTO': 104, 'ALPHA-ARB': 101 },
  { date: 'Nov 15', 'PSI-10': 105, 'PSI-25': 103, 'PSI-CRYPTO': 108, 'ALPHA-ARB': 102 },
  { date: 'Nov 22', 'PSI-10': 108, 'PSI-25': 105, 'PSI-CRYPTO': 112, 'ALPHA-ARB': 103 },
  { date: 'Nov 29', 'PSI-10': 110, 'PSI-25': 107, 'PSI-CRYPTO': 115, 'ALPHA-ARB': 104 },
  { date: 'Dec 6', 'PSI-10': 112, 'PSI-25': 108, 'PSI-CRYPTO': 118, 'ALPHA-ARB': 105 },
  { date: 'Dec 13', 'PSI-10': 115, 'PSI-25': 110, 'PSI-CRYPTO': 120, 'ALPHA-ARB': 106 },
  { date: 'Dec 20', 'PSI-10': 118, 'PSI-25': 112, 'PSI-CRYPTO': 122, 'ALPHA-ARB': 107 },
  { date: 'Dec 27', 'PSI-10': 120, 'PSI-25': 114, 'PSI-CRYPTO': 125, 'ALPHA-ARB': 108 },
]

// Fund colors for chart
const fundColors: Record<string, string> = {
  'PSI-10': '#0ea5e9',
  'PSI-25': '#06b6d4',
  'PSI-CRYPTO': '#8b5cf6',
  'PSI-POLITICS': '#f59e0b',
  'PSI-SPORTS': '#22c55e',
  'ALPHA-ARB': '#ec4899',
  'ALPHA-INSIDER': '#f97316',
  'ALPHA-EDGE': '#14b8a6',
}

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

// Fund type configurations
const fundTypes = [
  { id: 'PSI-10', name: 'PSI-10', type: 'MIRROR', description: 'Top 10 Smart Money traders' },
  { id: 'PSI-25', name: 'PSI-25', type: 'MIRROR', description: 'Top 25 Smart Money traders' },
  { id: 'PSI-CRYPTO', name: 'PSI-CRYPTO', type: 'MIRROR', description: 'Crypto market specialists' },
  { id: 'PSI-POLITICS', name: 'PSI-POLITICS', type: 'MIRROR', description: 'Political markets experts' },
  { id: 'PSI-SPORTS', name: 'PSI-SPORTS', type: 'MIRROR', description: 'Sports betting specialists' },
  { id: 'ALPHA-ARB', name: 'ALPHA-ARB', type: 'ACTIVE', description: 'Complete-set arbitrage' },
  { id: 'ALPHA-INSIDER', name: 'ALPHA-INSIDER', type: 'ACTIVE', description: 'Insider activity signals' },
  { id: 'ALPHA-EDGE', name: 'ALPHA-EDGE', type: 'ACTIVE', description: 'ML edge predictions' },
]

function FundPageContent() {
  const searchParams = useSearchParams()
  const typeParam = searchParams.get('type') || 'PSI-10'

  const [selectedFund, setSelectedFund] = useState(typeParam)
  const [showFundSelector, setShowFundSelector] = useState(false)
  const [overview, setOverview] = useState<FundOverview | null>(null)
  const [positions, setPositions] = useState<FundPosition[]>([])
  const [constituents, setConstituents] = useState<IndexConstituent[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [comparisonTimeframe, setComparisonTimeframe] = useState('1M')

  // Get current fund config
  const currentFund = fundTypes.find(f => f.id === selectedFund) || fundTypes[0]
  const isMirrorFund = currentFund.type === 'MIRROR'

  useEffect(() => {
    async function fetchFundData() {
      try {
        setIsLoading(true)
        setError(null)

        const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

        // Fetch fund overview with fund type
        const navResponse = await fetch(`${API_BASE}/api/fund/nav?fund_id=${selectedFund}`)
        if (navResponse.ok) {
          const navData = await navResponse.json()
          setOverview({
            fund_id: navData.fund_id || selectedFund,
            nav: navData.nav || 10000,
            capital: navData.capital || 10000,
            position_value: navData.position_value || 0,
            unrealized_pnl: navData.unrealized_pnl || 0,
            realized_pnl: navData.realized_pnl || 0,
            total_return: navData.total_return || 0,
            open_positions: navData.open_positions || 0,
            num_traders: navData.num_traders || (selectedFund.includes('10') ? 10 : selectedFund.includes('25') ? 25 : 0),
            last_updated: navData.last_updated || new Date().toISOString(),
          })
        } else {
          // Set default values if API not available
          setOverview({
            fund_id: selectedFund,
            nav: 10000,
            capital: 10000,
            position_value: 0,
            unrealized_pnl: 0,
            realized_pnl: 0,
            total_return: 0,
            open_positions: 0,
            num_traders: selectedFund.includes('10') ? 10 : selectedFund.includes('25') ? 25 : 0,
            last_updated: new Date().toISOString(),
          })
        }

        // Fetch positions
        const posResponse = await fetch(`${API_BASE}/api/fund/positions?fund_id=${selectedFund}`)
        if (posResponse.ok) {
          const posData = await posResponse.json()
          setPositions(Array.isArray(posData) ? posData : posData.positions || [])
        } else {
          setPositions([])
        }

        // Fetch index constituents for MIRROR funds
        if (isMirrorFund) {
          const indexResponse = await fetch(`${API_BASE}/api/fund/index?index_type=${selectedFund}`)
          if (indexResponse.ok) {
            const indexData = await indexResponse.json()
            const mappedConstituents = (indexData.constituents || []).map((c: any) => ({
              username: c.username,
              weight: c.weight / 100,
              total_score: c.smart_money_score,
              sharpe_ratio: c.sharpe_ratio,
              strategy_type: c.strategy_type,
            }))
            setConstituents(mappedConstituents)
          } else {
            setConstituents([])
          }
        } else {
          setConstituents([])
        }

      } catch (err) {
        console.error('Fund data fetch error:', err)
        setError('Failed to load fund data')
      } finally {
        setIsLoading(false)
      }
    }

    fetchFundData()
    const interval = setInterval(fetchFundData, 30000)
    return () => clearInterval(interval)
  }, [selectedFund, isMirrorFund])

  const totalReturn = overview ? overview.nav - overview.capital : 0
  const returnPct = overview && overview.capital > 0 ? (totalReturn / overview.capital) * 100 : 0
  const isPositive = totalReturn >= 0

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-3">
            {isMirrorFund ? (
              <Users className="h-7 w-7 text-blue-400" />
            ) : (
              <Zap className="h-7 w-7 text-purple-400" />
            )}
            {currentFund.name} Fund
          </h1>
          <p className="text-slate-400 mt-1">
            {currentFund.description}
          </p>
        </div>

        {/* Fund Selector */}
        <div className="relative">
          <button
            onClick={() => setShowFundSelector(!showFundSelector)}
            className="flex items-center gap-2 px-4 py-2 bg-slate-800 border border-slate-700 rounded-lg hover:bg-slate-700 transition-colors"
          >
            <span className={cn(
              'text-xs px-2 py-0.5 rounded-full',
              isMirrorFund ? 'bg-blue-500/20 text-blue-400' : 'bg-purple-500/20 text-purple-400'
            )}>
              {currentFund.type}
            </span>
            <span className="text-white font-medium">{currentFund.name}</span>
            <ChevronDown className={cn(
              'w-4 h-4 text-slate-400 transition-transform',
              showFundSelector && 'rotate-180'
            )} />
          </button>

          {showFundSelector && (
            <>
              <div
                className="fixed inset-0 z-40"
                onClick={() => setShowFundSelector(false)}
              />
              <div className="absolute right-0 mt-2 w-64 bg-slate-800 border border-slate-700 rounded-lg shadow-xl z-50 overflow-hidden">
                {fundTypes.map((fund) => (
                  <button
                    key={fund.id}
                    onClick={() => {
                      setSelectedFund(fund.id)
                      setShowFundSelector(false)
                    }}
                    className={cn(
                      'w-full px-4 py-3 text-left hover:bg-slate-700/50 transition-colors flex items-center justify-between',
                      selectedFund === fund.id && 'bg-aware-500/10'
                    )}
                  >
                    <div>
                      <p className="text-white font-medium">{fund.name}</p>
                      <p className="text-xs text-slate-500">{fund.description}</p>
                    </div>
                    <span className={cn(
                      'text-xs px-2 py-0.5 rounded-full',
                      fund.type === 'MIRROR' ? 'bg-blue-500/20 text-blue-400' : 'bg-purple-500/20 text-purple-400'
                    )}>
                      {fund.type}
                    </span>
                  </button>
                ))}

                <div className="border-t border-slate-700 p-2">
                  <Link
                    href="/funds"
                    className="block w-full px-3 py-2 text-sm text-aware-400 hover:text-aware-300 text-center"
                  >
                    View All Funds →
                  </Link>
                </div>
              </div>
            </>
          )}
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
        <div className="rounded-xl bg-slate-900/50 border border-slate-800 p-12 flex items-center justify-center">
          <Loader2 className="h-8 w-8 text-aware-400 animate-spin" />
          <span className="ml-3 text-slate-400">Loading fund data...</span>
        </div>
      )}

      {!isLoading && overview && (
        <>
          {/* NAV Card - Hero */}
          <div className={cn(
            'rounded-xl border p-6',
            isMirrorFund
              ? 'bg-gradient-to-br from-blue-500/10 to-cyan-500/10 border-blue-500/30'
              : 'bg-gradient-to-br from-purple-500/10 to-violet-500/10 border-purple-500/30'
          )}>
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

          {/* NAV Chart */}
          <div className="rounded-xl bg-slate-900/50 border border-slate-800 p-6">
            <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
              <Activity className="w-5 h-5 text-aware-400" />
              NAV History
            </h3>
            <NAVChart fundId={selectedFund} height={300} />
          </div>

          {/* Quick Fund Switcher Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {fundTypes.slice(0, 4).filter(f => f.id !== selectedFund).map((fund) => (
              <button
                key={fund.id}
                onClick={() => setSelectedFund(fund.id)}
                className={cn(
                  'rounded-xl bg-slate-900/50 border p-4 text-left transition-all hover:shadow-lg',
                  'border-slate-800 hover:border-slate-600'
                )}
              >
                <div className="flex items-center gap-2 mb-2">
                  <div
                    className="w-3 h-3 rounded-full"
                    style={{ backgroundColor: fundColors[fund.id] || '#64748b' }}
                  />
                  <span className="font-medium text-white text-sm">{fund.name}</span>
                </div>
                <p className="text-xs text-slate-500 line-clamp-1">{fund.description}</p>
                <div className="mt-2 flex items-center justify-between">
                  <span className={cn(
                    'text-xs px-1.5 py-0.5 rounded',
                    fund.type === 'MIRROR' ? 'bg-blue-500/20 text-blue-400' : 'bg-purple-500/20 text-purple-400'
                  )}>
                    {fund.type}
                  </span>
                </div>
              </button>
            ))}
          </div>

          {/* Fund Performance Comparison Chart */}
          <div className="rounded-xl bg-slate-900/50 border border-slate-800 p-6">
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-lg font-semibold text-white">Fund Performance Comparison</h3>
              <div className="flex gap-1 p-1 bg-slate-800/50 rounded-lg">
                {['1W', '1M', '3M', 'ALL'].map((tf) => (
                  <button
                    key={tf}
                    onClick={() => setComparisonTimeframe(tf)}
                    className={cn(
                      'px-3 py-1.5 text-xs font-medium rounded-md transition-all',
                      comparisonTimeframe === tf
                        ? 'bg-aware-500 text-white'
                        : 'text-slate-400 hover:text-white'
                    )}
                  >
                    {tf}
                  </button>
                ))}
              </div>
            </div>
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={mockComparisonData}>
                  <defs>
                    {Object.entries(fundColors).map(([fundId, color]) => (
                      <linearGradient key={fundId} id={`color-${fundId}`} x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={color} stopOpacity={0.2} />
                        <stop offset="95%" stopColor={color} stopOpacity={0} />
                      </linearGradient>
                    ))}
                  </defs>
                  <XAxis
                    dataKey="date"
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: '#64748b', fontSize: 12 }}
                  />
                  <YAxis
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: '#64748b', fontSize: 12 }}
                    domain={[95, 130]}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#1e293b',
                      border: '1px solid #334155',
                      borderRadius: '8px'
                    }}
                  />
                  <Legend />
                  {['PSI-10', 'PSI-25', 'PSI-CRYPTO', 'ALPHA-ARB'].map((fundId) => (
                    <Area
                      key={fundId}
                      type="monotone"
                      dataKey={fundId}
                      stroke={fundColors[fundId]}
                      strokeWidth={selectedFund === fundId ? 3 : 1.5}
                      fill={`url(#color-${fundId})`}
                      opacity={selectedFund === fundId ? 1 : 0.5}
                    />
                  ))}
                </AreaChart>
              </ResponsiveContainer>
            </div>
            <p className="text-xs text-slate-500 mt-3 text-center">
              Normalized performance (base = 100). Real data will populate as trades execute.
            </p>
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

            {isMirrorFund && (
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
            )}

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
                    {isMirrorFund
                      ? 'Fund will open positions when tracked traders trade'
                      : 'Waiting for trading signals'}
                  </p>
                </div>
              ) : (
                <div className="divide-y divide-slate-800 max-h-96 overflow-y-auto">
                  {positions.map((pos) => (
                    <div key={pos.token_id} className="p-4 hover:bg-slate-800/30">
                      <div className="flex justify-between items-start">
                        <div>
                          <p className="text-white font-medium truncate max-w-[200px]">{pos.market_slug}</p>
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

            {/* Index Constituents (for MIRROR funds) or Strategy Info (for ACTIVE funds) */}
            {isMirrorFund ? (
              <div className="rounded-xl bg-slate-900/50 border border-slate-800 overflow-hidden">
                <div className="p-4 border-b border-slate-800">
                  <h2 className="text-lg font-semibold text-white flex items-center gap-2">
                    <Users className="h-5 w-5 text-aware-400" />
                    {currentFund.name} Constituents
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
                  <div className="divide-y divide-slate-800 max-h-96 overflow-y-auto">
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
            ) : (
              <div className="rounded-xl bg-slate-900/50 border border-slate-800 overflow-hidden">
                <div className="p-4 border-b border-slate-800">
                  <h2 className="text-lg font-semibold text-white flex items-center gap-2">
                    <Zap className="h-5 w-5 text-purple-400" />
                    Strategy Details
                  </h2>
                </div>
                <div className="p-6">
                  <div className="space-y-4">
                    {selectedFund === 'ALPHA-ARB' && (
                      <>
                        <div>
                          <p className="text-slate-400 text-sm">Strategy Type</p>
                          <p className="text-white font-medium">Complete-Set Arbitrage</p>
                        </div>
                        <div>
                          <p className="text-slate-400 text-sm">Description</p>
                          <p className="text-white">Exploits price discrepancies by buying complete sets when outcomes sum to less than $1</p>
                        </div>
                      </>
                    )}
                    {selectedFund === 'ALPHA-INSIDER' && (
                      <>
                        <div>
                          <p className="text-slate-400 text-sm">Strategy Type</p>
                          <p className="text-white font-medium">Insider Activity Detection</p>
                        </div>
                        <div>
                          <p className="text-slate-400 text-sm">Description</p>
                          <p className="text-white">Follows unusual trading patterns that suggest informed trading activity</p>
                        </div>
                      </>
                    )}
                    {selectedFund === 'ALPHA-EDGE' && (
                      <>
                        <div>
                          <p className="text-slate-400 text-sm">Strategy Type</p>
                          <p className="text-white font-medium">ML Edge Predictions</p>
                        </div>
                        <div>
                          <p className="text-slate-400 text-sm">Description</p>
                          <p className="text-white">Uses machine learning to identify high-probability trading opportunities</p>
                        </div>
                      </>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Fund Info */}
          <div className="rounded-xl bg-slate-800/30 border border-slate-800 p-6">
            <h3 className="text-lg font-semibold text-white mb-4">About This Fund</h3>
            <div className="grid md:grid-cols-3 gap-6 text-sm">
              <div>
                <p className="text-slate-400">Strategy</p>
                <p className="text-white mt-1">{currentFund.description}</p>
              </div>
              <div>
                <p className="text-slate-400">Execution</p>
                <p className="text-white mt-1">
                  {isMirrorFund
                    ? '5-second delay after detecting trader trades, limit orders with market fallback'
                    : 'Algorithmic execution based on strategy signals'}
                </p>
              </div>
              <div>
                <p className="text-slate-400">Risk Controls</p>
                <p className="text-white mt-1">
                  Max 10% per position, 10% max drawdown circuit breaker
                </p>
              </div>
            </div>
          </div>

          {/* Quick Actions */}
          <div className="flex justify-center gap-4">
            <Link
              href={`/invest/deposit?fund=${selectedFund}`}
              className="px-6 py-3 bg-green-500 hover:bg-green-600 text-white font-medium rounded-lg transition-colors"
            >
              Deposit into {currentFund.name}
            </Link>
            <Link
              href="/funds"
              className="px-6 py-3 bg-slate-700 hover:bg-slate-600 text-white font-medium rounded-lg transition-colors"
            >
              Compare Funds
            </Link>
          </div>
        </>
      )}
    </div>
  )
}

export default function FundPage() {
  return (
    <Suspense fallback={
      <div className="rounded-xl bg-slate-900/50 border border-slate-800 p-12 flex items-center justify-center">
        <Loader2 className="h-8 w-8 text-aware-400 animate-spin" />
        <span className="ml-3 text-slate-400">Loading fund details...</span>
      </div>
    }>
      <FundPageContent />
    </Suspense>
  )
}
