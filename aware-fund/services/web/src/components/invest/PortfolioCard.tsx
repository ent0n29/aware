'use client'

import { TrendingUp, TrendingDown, Wallet, PieChart } from 'lucide-react'
import { cn, formatCurrency, formatPercent } from '@/lib/utils'
import { UserHolding } from '@/lib/api'

interface PortfolioCardProps {
  holdings: UserHolding[]
  totalValue: number
  totalPnL: number
  totalPnLPct: number
}

// Fund type badge colors
const fundTypeColors: Record<string, { bg: string; text: string }> = {
  MIRROR: { bg: 'bg-blue-500/20', text: 'text-blue-400' },
  ACTIVE: { bg: 'bg-purple-500/20', text: 'text-purple-400' },
}

export function PortfolioCard({
  holdings,
  totalValue,
  totalPnL,
  totalPnLPct,
}: PortfolioCardProps) {
  const isPositive = totalPnL >= 0

  return (
    <div className="rounded-xl bg-slate-900/50 border border-slate-800 overflow-hidden">
      {/* Header */}
      <div className="p-6 border-b border-slate-800">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-xl bg-aware-500/20 flex items-center justify-center">
              <Wallet className="w-6 h-6 text-aware-400" />
            </div>
            <div>
              <p className="text-sm text-slate-400">Total Portfolio Value</p>
              <p className="text-3xl font-bold text-white">
                {formatCurrency(totalValue)}
              </p>
            </div>
          </div>

          <div className={cn(
            'flex items-center gap-2 px-4 py-2 rounded-lg',
            isPositive ? 'bg-green-500/10' : 'bg-red-500/10'
          )}>
            {isPositive ? (
              <TrendingUp className="w-5 h-5 text-green-400" />
            ) : (
              <TrendingDown className="w-5 h-5 text-red-400" />
            )}
            <div className="text-right">
              <p className={cn(
                'font-semibold',
                isPositive ? 'text-green-400' : 'text-red-400'
              )}>
                {isPositive ? '+' : ''}{formatCurrency(totalPnL)}
              </p>
              <p className={cn(
                'text-sm',
                isPositive ? 'text-green-400/70' : 'text-red-400/70'
              )}>
                {isPositive ? '+' : ''}{totalPnLPct.toFixed(2)}%
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Holdings List */}
      <div className="divide-y divide-slate-800">
        {holdings.length === 0 ? (
          <div className="p-8 text-center">
            <PieChart className="w-12 h-12 text-slate-600 mx-auto mb-3" />
            <p className="text-slate-400">No holdings yet</p>
            <p className="text-sm text-slate-500 mt-1">
              Deposit into a fund to start investing
            </p>
          </div>
        ) : (
          holdings.map((holding) => {
            const fundColors = fundTypeColors[holding.fund_type] || fundTypeColors.MIRROR
            const holdingPositive = holding.unrealized_pnl >= 0

            return (
              <div
                key={holding.fund_id}
                className="p-4 flex items-center justify-between hover:bg-slate-800/30 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-slate-800 flex items-center justify-center">
                    <span className="font-bold text-white text-sm">
                      {holding.fund_id.split('-')[0]}
                    </span>
                  </div>
                  <div>
                    <p className="font-medium text-white">{holding.fund_id}</p>
                    <div className="flex items-center gap-2">
                      <span className={cn(
                        'text-xs px-2 py-0.5 rounded-full',
                        fundColors.bg,
                        fundColors.text
                      )}>
                        {holding.fund_type}
                      </span>
                      <span className="text-xs text-slate-500">
                        {holding.shares.toFixed(4)} shares
                      </span>
                    </div>
                  </div>
                </div>

                <div className="text-right">
                  <p className="font-semibold text-white">
                    {formatCurrency(holding.value_usd)}
                  </p>
                  <p className={cn(
                    'text-sm',
                    holdingPositive ? 'text-green-400' : 'text-red-400'
                  )}>
                    {holdingPositive ? '+' : ''}{formatCurrency(holding.unrealized_pnl)}
                    <span className="ml-1 text-xs">
                      ({holdingPositive ? '+' : ''}{holding.unrealized_pnl_pct.toFixed(2)}%)
                    </span>
                  </p>
                </div>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}

// Skeleton version for loading state
export function PortfolioCardSkeleton() {
  return (
    <div className="rounded-xl bg-slate-900/50 border border-slate-800 overflow-hidden animate-pulse">
      <div className="p-6 border-b border-slate-800">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-xl bg-slate-700" />
            <div>
              <div className="h-4 w-24 bg-slate-700 rounded mb-2" />
              <div className="h-8 w-32 bg-slate-700 rounded" />
            </div>
          </div>
          <div className="h-16 w-28 bg-slate-700 rounded-lg" />
        </div>
      </div>
      <div className="p-4 space-y-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-slate-700" />
              <div>
                <div className="h-4 w-20 bg-slate-700 rounded mb-1" />
                <div className="h-3 w-16 bg-slate-700 rounded" />
              </div>
            </div>
            <div className="text-right">
              <div className="h-4 w-16 bg-slate-700 rounded mb-1" />
              <div className="h-3 w-12 bg-slate-700 rounded" />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export default PortfolioCard
