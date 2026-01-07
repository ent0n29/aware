'use client'

import { useState } from 'react'
import { ChevronDown, Check, TrendingUp, TrendingDown, Users, Zap } from 'lucide-react'
import { cn, formatCurrency, formatPercent } from '@/lib/utils'
import { FundInfo, UserHolding } from '@/lib/api'

interface FundSelectorProps {
  funds: FundInfo[]
  selectedFundId?: string
  userHoldings?: UserHolding[]
  onSelect: (fundId: string) => void
  showHoldingsOnly?: boolean
}

// Fund category icons and colors
const fundTypeConfig: Record<string, { icon: typeof Users; color: string; bgColor: string }> = {
  'PSI-10': { icon: Users, color: 'text-blue-400', bgColor: 'bg-blue-500/20' },
  'PSI-25': { icon: Users, color: 'text-blue-400', bgColor: 'bg-blue-500/20' },
  'PSI-CRYPTO': { icon: Zap, color: 'text-orange-400', bgColor: 'bg-orange-500/20' },
  'PSI-POLITICS': { icon: Users, color: 'text-red-400', bgColor: 'bg-red-500/20' },
  'PSI-SPORTS': { icon: Users, color: 'text-green-400', bgColor: 'bg-green-500/20' },
  'ALPHA-ARB': { icon: Zap, color: 'text-purple-400', bgColor: 'bg-purple-500/20' },
  'ALPHA-INSIDER': { icon: Zap, color: 'text-yellow-400', bgColor: 'bg-yellow-500/20' },
  'ALPHA-EDGE': { icon: Zap, color: 'text-cyan-400', bgColor: 'bg-cyan-500/20' },
}

export function FundSelector({
  funds,
  selectedFundId,
  userHoldings,
  onSelect,
  showHoldingsOnly = false,
}: FundSelectorProps) {
  const [isOpen, setIsOpen] = useState(false)

  // Filter funds if showHoldingsOnly
  const displayFunds = showHoldingsOnly && userHoldings
    ? funds.filter(f => userHoldings.some(h => h.fund_id === f.fund_id))
    : funds

  // Get selected fund info
  const selectedFund = funds.find(f => f.fund_id === selectedFundId)

  // Get user holding for a fund
  const getHolding = (fundId: string) =>
    userHoldings?.find(h => h.fund_id === fundId)

  return (
    <div className="relative">
      {/* Trigger Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={cn(
          'w-full flex items-center justify-between gap-3 p-4',
          'bg-slate-800/50 border border-slate-700 rounded-xl',
          'hover:bg-slate-800 hover:border-slate-600 transition-all',
          'focus:outline-none focus:ring-2 focus:ring-aware-500/50'
        )}
      >
        {selectedFund ? (
          <div className="flex items-center gap-3">
            <div className={cn(
              'w-10 h-10 rounded-lg flex items-center justify-center',
              fundTypeConfig[selectedFund.fund_id]?.bgColor || 'bg-slate-700'
            )}>
              {(() => {
                const Icon = fundTypeConfig[selectedFund.fund_id]?.icon || Users
                const color = fundTypeConfig[selectedFund.fund_id]?.color || 'text-slate-400'
                return <Icon className={cn('w-5 h-5', color)} />
              })()}
            </div>
            <div className="text-left">
              <p className="font-medium text-white">{selectedFund.name}</p>
              <p className="text-sm text-slate-400">
                NAV: {formatCurrency(selectedFund.nav_per_share)}
              </p>
            </div>
          </div>
        ) : (
          <span className="text-slate-400">Select a fund...</span>
        )}
        <ChevronDown className={cn(
          'w-5 h-5 text-slate-400 transition-transform',
          isOpen && 'rotate-180'
        )} />
      </button>

      {/* Dropdown */}
      {isOpen && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 z-40"
            onClick={() => setIsOpen(false)}
          />

          {/* Dropdown Panel */}
          <div className="absolute top-full left-0 right-0 mt-2 z-50 bg-slate-800 border border-slate-700 rounded-xl shadow-xl overflow-hidden">
            <div className="max-h-96 overflow-y-auto">
              {displayFunds.length === 0 ? (
                <div className="p-4 text-center text-slate-400">
                  {showHoldingsOnly ? 'No holdings to withdraw from' : 'No funds available'}
                </div>
              ) : (
                displayFunds.map((fund) => {
                  const holding = getHolding(fund.fund_id)
                  const isSelected = fund.fund_id === selectedFundId
                  const config = fundTypeConfig[fund.fund_id] || { icon: Users, color: 'text-slate-400', bgColor: 'bg-slate-700' }
                  const Icon = config.icon

                  return (
                    <button
                      key={fund.fund_id}
                      onClick={() => {
                        onSelect(fund.fund_id)
                        setIsOpen(false)
                      }}
                      className={cn(
                        'w-full p-4 flex items-center gap-3',
                        'hover:bg-slate-700/50 transition-colors',
                        'border-b border-slate-700/50 last:border-0',
                        isSelected && 'bg-aware-500/10'
                      )}
                    >
                      <div className={cn(
                        'w-10 h-10 rounded-lg flex items-center justify-center',
                        config.bgColor
                      )}>
                        <Icon className={cn('w-5 h-5', config.color)} />
                      </div>

                      <div className="flex-1 text-left">
                        <div className="flex items-center gap-2">
                          <p className="font-medium text-white">{fund.name}</p>
                          <span className={cn(
                            'text-xs px-2 py-0.5 rounded-full',
                            fund.fund_type === 'MIRROR'
                              ? 'bg-blue-500/20 text-blue-400'
                              : 'bg-purple-500/20 text-purple-400'
                          )}>
                            {fund.fund_type}
                          </span>
                        </div>
                        <p className="text-sm text-slate-400 line-clamp-1">
                          {fund.description}
                        </p>
                      </div>

                      <div className="text-right">
                        <p className="text-sm font-medium text-white">
                          {formatCurrency(fund.nav_per_share)}
                        </p>
                        <div className="flex items-center justify-end gap-1">
                          {fund.performance_30d >= 0 ? (
                            <TrendingUp className="w-3 h-3 text-green-400" />
                          ) : (
                            <TrendingDown className="w-3 h-3 text-red-400" />
                          )}
                          <span className={cn(
                            'text-xs',
                            fund.performance_30d >= 0 ? 'text-green-400' : 'text-red-400'
                          )}>
                            {formatPercent(fund.performance_30d)}
                          </span>
                        </div>
                        {holding && (
                          <p className="text-xs text-aware-400 mt-1">
                            {formatCurrency(holding.value_usd)} invested
                          </p>
                        )}
                      </div>

                      {isSelected && (
                        <Check className="w-5 h-5 text-aware-400" />
                      )}
                    </button>
                  )
                })
              )}
            </div>
          </div>
        </>
      )}
    </div>
  )
}

// Compact inline version for forms
export function FundSelectorCompact({
  funds,
  selectedFundId,
  onSelect,
}: Omit<FundSelectorProps, 'userHoldings' | 'showHoldingsOnly'>) {
  return (
    <select
      value={selectedFundId || ''}
      onChange={(e) => onSelect(e.target.value)}
      className={cn(
        'w-full px-4 py-3 bg-slate-800 border border-slate-700 rounded-lg',
        'text-white focus:outline-none focus:ring-2 focus:ring-aware-500/50',
        'appearance-none cursor-pointer'
      )}
    >
      <option value="" disabled>Select a fund...</option>
      {funds.map((fund) => (
        <option key={fund.fund_id} value={fund.fund_id}>
          {fund.name} - NAV: ${fund.nav_per_share.toFixed(2)}
        </option>
      ))}
    </select>
  )
}

export default FundSelector
