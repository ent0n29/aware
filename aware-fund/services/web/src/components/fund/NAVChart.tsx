'use client'

import { useState, useEffect } from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Area,
  AreaChart,
} from 'recharts'
import { Loader2 } from 'lucide-react'
import { cn, formatCurrency } from '@/lib/utils'
import { api, NAVDataPoint } from '@/lib/api'

interface NAVChartProps {
  fundId: string
  height?: number
  showControls?: boolean
  className?: string
}

const timeRanges = [
  { label: '1W', days: 7 },
  { label: '1M', days: 30 },
  { label: '3M', days: 90 },
  { label: 'ALL', days: 365 },
]

export function NAVChart({
  fundId,
  height = 300,
  showControls = true,
  className,
}: NAVChartProps) {
  const [data, setData] = useState<NAVDataPoint[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedRange, setSelectedRange] = useState(30)

  // Fetch NAV history
  useEffect(() => {
    async function fetchData() {
      setIsLoading(true)
      setError(null)
      try {
        const response = await api.getFundNAVHistory(fundId, selectedRange)
        setData(response.data_points)
      } catch (err) {
        console.error('Failed to fetch NAV history:', err)
        setError('Failed to load chart data')
        setData([])
      } finally {
        setIsLoading(false)
      }
    }

    fetchData()
  }, [fundId, selectedRange])

  // Format data for chart
  const chartData = data.map(point => ({
    date: new Date(point.timestamp).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
    }),
    fullDate: new Date(point.timestamp).toLocaleDateString('en-US', {
      month: 'long',
      day: 'numeric',
      year: 'numeric',
    }),
    nav: point.nav_per_share,
    return: point.daily_return * 100,
  }))

  // Calculate performance
  const firstNav = data[0]?.nav_per_share || 1
  const lastNav = data[data.length - 1]?.nav_per_share || 1
  const performancePct = ((lastNav - firstNav) / firstNav) * 100
  const isPositive = performancePct >= 0

  // Custom tooltip
  const CustomTooltip = ({ active, payload }: any) => {
    if (!active || !payload?.[0]) return null

    const item = payload[0].payload
    return (
      <div className="bg-slate-800 border border-slate-700 rounded-lg shadow-xl p-3">
        <p className="text-slate-400 text-xs mb-1">{item.fullDate}</p>
        <p className="text-white font-semibold">
          NAV: {formatCurrency(item.nav)}
        </p>
        <p className={cn(
          'text-sm',
          item.return >= 0 ? 'text-green-400' : 'text-red-400'
        )}>
          {item.return >= 0 ? '+' : ''}{item.return.toFixed(2)}% daily
        </p>
      </div>
    )
  }

  if (isLoading) {
    return (
      <div
        className={cn('flex items-center justify-center bg-slate-900/50 rounded-xl', className)}
        style={{ height }}
      >
        <Loader2 className="w-6 h-6 text-aware-400 animate-spin" />
        <span className="ml-2 text-slate-400">Loading chart...</span>
      </div>
    )
  }

  if (error || data.length === 0) {
    return (
      <div
        className={cn('flex items-center justify-center bg-slate-900/50 rounded-xl text-slate-400', className)}
        style={{ height }}
      >
        {error || 'No data available'}
      </div>
    )
  }

  return (
    <div className={cn('space-y-4', className)}>
      {/* Controls */}
      {showControls && (
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            {timeRanges.map((range) => (
              <button
                key={range.days}
                onClick={() => setSelectedRange(range.days)}
                className={cn(
                  'px-3 py-1.5 text-sm font-medium rounded-lg transition-all',
                  selectedRange === range.days
                    ? 'bg-aware-500/20 text-aware-400 ring-1 ring-aware-500/50'
                    : 'bg-slate-800 text-slate-400 hover:bg-slate-700'
                )}
              >
                {range.label}
              </button>
            ))}
          </div>

          <div className={cn(
            'px-3 py-1.5 rounded-lg text-sm font-medium',
            isPositive ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'
          )}>
            {isPositive ? '+' : ''}{performancePct.toFixed(2)}%
          </div>
        </div>
      )}

      {/* Chart */}
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id={`navGradient-${fundId}`} x1="0" y1="0" x2="0" y2="1">
                <stop
                  offset="5%"
                  stopColor={isPositive ? '#22c55e' : '#ef4444'}
                  stopOpacity={0.3}
                />
                <stop
                  offset="95%"
                  stopColor={isPositive ? '#22c55e' : '#ef4444'}
                  stopOpacity={0}
                />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />
            <XAxis
              dataKey="date"
              stroke="#64748b"
              fontSize={12}
              tickLine={false}
              axisLine={false}
            />
            <YAxis
              stroke="#64748b"
              fontSize={12}
              tickLine={false}
              axisLine={false}
              tickFormatter={(value) => `$${value.toFixed(2)}`}
              domain={['dataMin - 0.1', 'dataMax + 0.1']}
            />
            <Tooltip content={<CustomTooltip />} />
            <Area
              type="monotone"
              dataKey="nav"
              stroke={isPositive ? '#22c55e' : '#ef4444'}
              strokeWidth={2}
              fill={`url(#navGradient-${fundId})`}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

// Mini version for fund cards
export function NAVChartMini({
  data,
  height = 60,
  className,
}: {
  data: NAVDataPoint[]
  height?: number
  className?: string
}) {
  const chartData = data.map(point => ({
    nav: point.nav_per_share,
  }))

  const firstNav = data[0]?.nav_per_share || 1
  const lastNav = data[data.length - 1]?.nav_per_share || 1
  const isPositive = lastNav >= firstNav

  return (
    <div className={className} style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData}>
          <Line
            type="monotone"
            dataKey="nav"
            stroke={isPositive ? '#22c55e' : '#ef4444'}
            strokeWidth={1.5}
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

export default NAVChart
