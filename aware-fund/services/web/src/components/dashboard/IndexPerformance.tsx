'use client'

import { LineChart, TrendingUp, TrendingDown } from 'lucide-react'
import { cn, formatPercent } from '@/lib/utils'
import {
  LineChart as RechartsLineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Area,
  AreaChart,
} from 'recharts'

// Mock chart data
const mockChartData = [
  { date: 'Dec 1', psi10: 100, psi25: 100 },
  { date: 'Dec 5', psi10: 105, psi25: 103 },
  { date: 'Dec 10', psi10: 112, psi25: 108 },
  { date: 'Dec 15', psi10: 108, psi25: 105 },
  { date: 'Dec 20', psi10: 125, psi25: 118 },
  { date: 'Dec 25', psi10: 138, psi25: 125 },
  { date: 'Dec 26', psi10: 142.5, psi25: 128 },
]

const indices = [
  { name: 'PSI-10', value: 142.50, change: 42.5, color: '#0ea5e9' },
  { name: 'PSI-25', value: 128.00, change: 28.0, color: '#06b6d4' },
  { name: 'PSI-Crypto', value: 156.20, change: 56.2, color: '#8b5cf6' },
  { name: 'PSI-Politics', value: 118.40, change: 18.4, color: '#f59e0b' },
]

export function IndexPerformance() {
  return (
    <div className="rounded-xl bg-slate-900/50 border border-slate-800 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between p-5 border-b border-slate-800">
        <div className="flex items-center gap-3">
          <div className="rounded-lg bg-aware-500/10 p-2">
            <LineChart className="h-5 w-5 text-aware-400" />
          </div>
          <div>
            <h3 className="font-semibold text-white">Index Performance</h3>
            <p className="text-xs text-slate-500">Since inception (Dec 1)</p>
          </div>
        </div>
        <div className="flex gap-2">
          {['7D', '1M', '3M', 'ALL'].map((period) => (
            <button
              key={period}
              className={cn(
                'px-3 py-1 text-xs font-medium rounded-md transition-colors',
                period === '1M'
                  ? 'bg-aware-500/20 text-aware-400'
                  : 'text-slate-500 hover:text-slate-300 hover:bg-slate-800'
              )}
            >
              {period}
            </button>
          ))}
        </div>
      </div>

      {/* Chart */}
      <div className="p-4">
        <div className="h-48">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={mockChartData}>
              <defs>
                <linearGradient id="colorPsi10" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#0ea5e9" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#0ea5e9" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="colorPsi25" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#06b6d4" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#06b6d4" stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis
                dataKey="date"
                axisLine={false}
                tickLine={false}
                tick={{ fill: '#64748b', fontSize: 11 }}
              />
              <YAxis
                axisLine={false}
                tickLine={false}
                tick={{ fill: '#64748b', fontSize: 11 }}
                domain={['dataMin - 10', 'dataMax + 10']}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#1e293b',
                  border: '1px solid #334155',
                  borderRadius: '8px',
                  boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.3)',
                }}
                labelStyle={{ color: '#94a3b8' }}
              />
              <Area
                type="monotone"
                dataKey="psi10"
                stroke="#0ea5e9"
                strokeWidth={2}
                fill="url(#colorPsi10)"
                name="PSI-10"
              />
              <Area
                type="monotone"
                dataKey="psi25"
                stroke="#06b6d4"
                strokeWidth={2}
                fill="url(#colorPsi25)"
                name="PSI-25"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Index Cards */}
      <div className="grid grid-cols-2 gap-3 p-4 pt-0">
        {indices.map((index) => (
          <div
            key={index.name}
            className="flex items-center justify-between p-3 bg-slate-800/50 rounded-lg"
          >
            <div className="flex items-center gap-2">
              <div
                className="w-2 h-2 rounded-full"
                style={{ backgroundColor: index.color }}
              />
              <span className="text-sm font-medium text-slate-300">
                {index.name}
              </span>
            </div>
            <div className="text-right">
              <p className="text-sm font-semibold text-white">
                ${index.value.toFixed(2)}
              </p>
              <p className="text-xs text-green-400">
                {formatPercent(index.change)}
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
