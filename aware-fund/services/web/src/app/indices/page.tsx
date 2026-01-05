'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import {
  LineChart,
  TrendingUp,
  TrendingDown,
  Users,
  DollarSign,
  ArrowUpRight,
  Info,
  Loader2,
} from 'lucide-react'
import { cn, formatCurrency, formatPercent } from '@/lib/utils'
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts'
import { api, PSIIndex, IndexConstituent } from '@/lib/api'

const staticIndices = [
  {
    id: 'psi-10',
    name: 'PSI-10',
    description: 'Top 10 traders by Smart Money Score',
    value: 142.50,
    change_24h: 2.4,
    change_7d: 8.2,
    change_30d: 42.5,
    constituents: 10,
    aum: 2500000,
    rebalance: 'Monthly',
    color: '#0ea5e9',
    featured: true,
  },
  {
    id: 'psi-25',
    name: 'PSI-25',
    description: 'Top 25 traders with diversified exposure',
    value: 128.00,
    change_24h: 1.8,
    change_7d: 5.4,
    change_30d: 28.0,
    constituents: 25,
    aum: 1800000,
    rebalance: 'Monthly',
    color: '#06b6d4',
    featured: false,
  },
  {
    id: 'psi-crypto',
    name: 'PSI-Crypto',
    description: 'Top crypto market specialists',
    value: 156.20,
    change_24h: 4.2,
    change_7d: 12.8,
    change_30d: 56.2,
    constituents: 15,
    aum: 1200000,
    rebalance: 'Weekly',
    color: '#8b5cf6',
    featured: false,
  },
  {
    id: 'psi-politics',
    name: 'PSI-Politics',
    description: 'Political market specialists',
    value: 118.40,
    change_24h: -0.8,
    change_7d: 2.1,
    change_30d: 18.4,
    constituents: 12,
    aum: 950000,
    rebalance: 'Event-driven',
    color: '#f59e0b',
    featured: false,
  },
  {
    id: 'psi-alpha',
    name: 'PSI-Alpha',
    description: 'ML-selected traders with highest edge persistence',
    value: 165.80,
    change_24h: 3.1,
    change_7d: 9.5,
    change_30d: 65.8,
    constituents: 8,
    aum: 850000,
    rebalance: 'Real-time',
    color: '#22c55e',
    featured: false,
  },
]

const mockChartData = [
  { date: 'Nov 1', 'PSI-10': 100, 'PSI-25': 100, 'PSI-Crypto': 100, 'PSI-Politics': 100 },
  { date: 'Nov 8', 'PSI-10': 105, 'PSI-25': 103, 'PSI-Crypto': 108, 'PSI-Politics': 102 },
  { date: 'Nov 15', 'PSI-10': 112, 'PSI-25': 108, 'PSI-Crypto': 118, 'PSI-Politics': 105 },
  { date: 'Nov 22', 'PSI-10': 118, 'PSI-25': 112, 'PSI-Crypto': 128, 'PSI-Politics': 108 },
  { date: 'Nov 29', 'PSI-10': 125, 'PSI-25': 118, 'PSI-Crypto': 142, 'PSI-Politics': 112 },
  { date: 'Dec 6', 'PSI-10': 130, 'PSI-25': 122, 'PSI-Crypto': 148, 'PSI-Politics': 115 },
  { date: 'Dec 13', 'PSI-10': 135, 'PSI-25': 125, 'PSI-Crypto': 152, 'PSI-Politics': 117 },
  { date: 'Dec 20', 'PSI-10': 140, 'PSI-25': 127, 'PSI-Crypto': 155, 'PSI-Politics': 118 },
  { date: 'Dec 26', 'PSI-10': 142.5, 'PSI-25': 128, 'PSI-Crypto': 156.2, 'PSI-Politics': 118.4 },
]

const mockConstituents = [
  { username: 'whale_master', weight: 15, score: 98.5, pnl_contribution: 28500 },
  { username: 'alpha_hunter', weight: 12, score: 95.2, pnl_contribution: 21200 },
  { username: 'smart_money_joe', weight: 11, score: 94.1, pnl_contribution: 18900 },
  { username: 'prediction_pro', weight: 10, score: 89.4, pnl_contribution: 15400 },
  { username: 'market_sage', weight: 10, score: 87.1, pnl_contribution: 14200 },
]

export default function IndicesPage() {
  const [psi10, setPsi10] = useState<PSIIndex | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedIndex, setSelectedIndex] = useState(staticIndices[0])
  const [timeframe, setTimeframe] = useState('1M')

  useEffect(() => {
    async function fetchPSI10() {
      try {
        setIsLoading(true)
        setError(null)
        const data = await api.getPSI10()
        setPsi10(data)
      } catch (err) {
        setError('Failed to load PSI-10 index. Make sure the API server is running.')
        console.error('PSI-10 fetch error:', err)
      } finally {
        setIsLoading(false)
      }
    }
    fetchPSI10()
  }, [])

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white flex items-center gap-3">
          <LineChart className="h-7 w-7 text-aware-400" />
          PSI Indices
        </h1>
        <p className="text-slate-400 mt-1">
          Track smart money performance with our index family
        </p>
      </div>

      {/* Error State */}
      {error && (
        <div className="rounded-xl bg-red-500/10 border border-red-500/30 p-6">
          <p className="text-red-400 font-medium">{error}</p>
          <p className="text-sm text-slate-400 mt-2">
            Start the API server: <code className="bg-slate-800 px-2 py-0.5 rounded">cd aware-fund/services/api && uvicorn main:app --reload</code>
          </p>
        </div>
      )}

      {/* Featured Index Card */}
      <div className="relative overflow-hidden rounded-2xl bg-gradient-to-r from-aware-600 via-aware-500 to-cyan-500 p-8">
        <div className="relative z-10 grid grid-cols-1 lg:grid-cols-2 gap-8">
          <div>
            <span className="inline-flex px-3 py-1 bg-white/20 rounded-full text-sm font-medium text-white mb-4">
              Flagship Index
            </span>
            <h2 className="text-4xl font-bold text-white mb-2">PSI-10</h2>
            <p className="text-aware-100 text-lg mb-6">
              {psi10?.description || 'Top 10 traders by Smart Money Score, rebalanced monthly'}
            </p>
            <div className="flex gap-8">
              <div>
                <p className="text-5xl font-bold text-white">
                  {isLoading ? '...' : (psi10?.trader_count || 0)}
                </p>
                <p className="text-aware-100 mt-1">Traders</p>
              </div>
              <div className="border-l border-white/20 pl-8">
                <p className="text-3xl font-bold text-green-300">
                  {isLoading ? '...' : `${((psi10?.total_weight || 0) * 100).toFixed(0)}%`}
                </p>
                <p className="text-aware-100 mt-1">Total Weight</p>
              </div>
            </div>
          </div>
          <div className="flex items-center justify-end gap-6">
            <div className="text-center">
              <p className="text-2xl font-bold text-white">{psi10?.trader_count || '—'}</p>
              <p className="text-sm text-aware-100">Constituents</p>
            </div>
            <div className="text-center">
              <p className="text-2xl font-bold text-white">
                {psi10?.composition?.length ? formatCurrency(
                  psi10.composition.reduce((sum, c) => sum + Math.abs(c.total_pnl), 0)
                ) : '—'}
              </p>
              <p className="text-sm text-aware-100">Combined P&L</p>
            </div>
            <div className="text-center">
              <p className="text-2xl font-bold text-white">Monthly</p>
              <p className="text-sm text-aware-100">Rebalance</p>
            </div>
          </div>
        </div>
        <div className="absolute top-0 right-0 w-96 h-96 bg-white/10 rounded-full blur-3xl -translate-y-1/2 translate-x-1/4" />
      </div>

      {/* All Indices Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {staticIndices.filter(i => !i.featured).map((index) => (
          <div
            key={index.id}
            onClick={() => setSelectedIndex(index)}
            className={cn(
              'rounded-xl bg-slate-900/50 border p-5 cursor-pointer transition-all hover:shadow-lg',
              selectedIndex.id === index.id
                ? 'border-aware-500 shadow-aware-500/20'
                : 'border-slate-800 hover:border-slate-700'
            )}
          >
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full" style={{ backgroundColor: index.color }} />
                <h3 className="font-semibold text-white">{index.name}</h3>
              </div>
              <span className={cn(
                'text-sm font-medium',
                index.change_24h >= 0 ? 'text-green-400' : 'text-red-400'
              )}>
                {formatPercent(index.change_24h)}
              </span>
            </div>
            <p className="text-2xl font-bold text-white mb-1">${index.value.toFixed(2)}</p>
            <p className="text-xs text-slate-500">{index.description}</p>
            <div className="flex items-center justify-between mt-4 pt-3 border-t border-slate-800">
              <span className="text-xs text-slate-500">{index.constituents} traders</span>
              <span className="text-xs text-slate-500">{index.rebalance}</span>
            </div>
          </div>
        ))}
      </div>

      {/* Performance Chart */}
      <div className="rounded-xl bg-slate-900/50 border border-slate-800 p-6">
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-lg font-semibold text-white">Index Performance Comparison</h3>
          <div className="flex gap-1 p-1 bg-slate-800/50 rounded-lg">
            {['1W', '1M', '3M', 'ALL'].map((tf) => (
              <button
                key={tf}
                onClick={() => setTimeframe(tf)}
                className={cn(
                  'px-3 py-1.5 text-xs font-medium rounded-md transition-all',
                  timeframe === tf
                    ? 'bg-aware-500 text-white'
                    : 'text-slate-400 hover:text-white'
                )}
              >
                {tf}
              </button>
            ))}
          </div>
        </div>
        <div className="h-80">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={mockChartData}>
              <defs>
                {staticIndices.map((index) => (
                  <linearGradient key={index.id} id={`color-${index.id}`} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={index.color} stopOpacity={0.2} />
                    <stop offset="95%" stopColor={index.color} stopOpacity={0} />
                  </linearGradient>
                ))}
              </defs>
              <XAxis dataKey="date" axisLine={false} tickLine={false} tick={{ fill: '#64748b', fontSize: 12 }} />
              <YAxis axisLine={false} tickLine={false} tick={{ fill: '#64748b', fontSize: 12 }} domain={[90, 170]} />
              <Tooltip contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '8px' }} />
              <Legend />
              {staticIndices.slice(0, 4).map((index) => (
                <Area
                  key={index.id}
                  type="monotone"
                  dataKey={index.name}
                  stroke={index.color}
                  strokeWidth={2}
                  fill={`url(#color-${index.id})`}
                />
              ))}
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Constituents Table */}
      <div className="rounded-xl bg-slate-900/50 border border-slate-800 overflow-hidden">
        <div className="p-5 border-b border-slate-800">
          <h3 className="font-semibold text-white">PSI-10 Constituents</h3>
          <p className="text-sm text-slate-500 mt-1">Current index holdings and weights</p>
        </div>

        {/* Loading State */}
        {isLoading && (
          <div className="p-8 flex items-center justify-center">
            <Loader2 className="h-6 w-6 text-aware-400 animate-spin" />
            <span className="ml-2 text-slate-400 text-sm">Loading constituents...</span>
          </div>
        )}

        {/* Empty State */}
        {!isLoading && (!psi10?.composition || psi10.composition.length === 0) && (
          <div className="p-8 text-center">
            <Users className="h-8 w-8 text-slate-600 mx-auto mb-2" />
            <p className="text-slate-400 text-sm">No constituents found</p>
            <p className="text-slate-500 text-xs mt-1">Run the scoring job to populate the index</p>
          </div>
        )}

        {/* Constituents List */}
        {!isLoading && psi10?.composition && psi10.composition.length > 0 && (
          <div className="divide-y divide-slate-800">
            {psi10.composition.map((c) => (
              <Link
                key={c.proxy_address || c.username}
                href={`/traders/${c.username || c.proxy_address}`}
                className="flex items-center gap-4 p-4 hover:bg-slate-800/30 transition-colors"
              >
                <span className="w-8 text-center text-slate-500 font-medium">{c.rank}</span>
                <div className="w-10 h-10 rounded-full bg-gradient-to-br from-aware-400 to-aware-600 flex items-center justify-center text-white font-bold">
                  {(c.username || c.proxy_address || '?').charAt(0).toUpperCase()}
                </div>
                <div className="flex-1">
                  <p className="font-medium text-white">{c.username || `${c.proxy_address?.slice(0, 6)}...${c.proxy_address?.slice(-4)}`}</p>
                  <p className="text-xs text-slate-500">Score: {c.smart_money_score.toFixed(1)}</p>
                </div>
                <div className="text-right">
                  <p className="font-semibold text-white">{(c.weight * 100).toFixed(1)}%</p>
                  <p className="text-xs text-slate-500">Weight</p>
                </div>
                <div className="text-right w-28">
                  <p className={cn('font-medium', c.total_pnl >= 0 ? 'text-green-400' : 'text-red-400')}>
                    {c.total_pnl >= 0 ? '+' : ''}{formatCurrency(c.total_pnl)}
                  </p>
                  <p className="text-xs text-slate-500">Total P&L</p>
                </div>
                <ArrowUpRight className="h-4 w-4 text-slate-600" />
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
