'use client'

import { ArrowDownLeft, ArrowUpRight, Clock, CheckCircle, XCircle, Loader2 } from 'lucide-react'
import { cn, formatCurrency, getTimeAgo } from '@/lib/utils'
import { Transaction } from '@/lib/api'

interface TransactionRowProps {
  transaction: Transaction
  showFundId?: boolean
}

const statusConfig: Record<string, { icon: typeof Clock; color: string; bgColor: string; label: string }> = {
  PENDING: {
    icon: Loader2,
    color: 'text-yellow-400',
    bgColor: 'bg-yellow-500/10',
    label: 'Processing',
  },
  COMPLETED: {
    icon: CheckCircle,
    color: 'text-green-400',
    bgColor: 'bg-green-500/10',
    label: 'Completed',
  },
  FAILED: {
    icon: XCircle,
    color: 'text-red-400',
    bgColor: 'bg-red-500/10',
    label: 'Failed',
  },
}

export function TransactionRow({ transaction, showFundId = true }: TransactionRowProps) {
  const isDeposit = transaction.transaction_type === 'DEPOSIT'
  const status = statusConfig[transaction.status] || statusConfig.PENDING
  const StatusIcon = status.icon

  return (
    <div className="flex items-center justify-between p-4 hover:bg-slate-800/30 transition-colors">
      <div className="flex items-center gap-4">
        {/* Type Icon */}
        <div className={cn(
          'w-10 h-10 rounded-lg flex items-center justify-center',
          isDeposit ? 'bg-green-500/10' : 'bg-red-500/10'
        )}>
          {isDeposit ? (
            <ArrowDownLeft className="w-5 h-5 text-green-400" />
          ) : (
            <ArrowUpRight className="w-5 h-5 text-red-400" />
          )}
        </div>

        {/* Details */}
        <div>
          <div className="flex items-center gap-2">
            <p className="font-medium text-white">
              {isDeposit ? 'Deposit' : 'Withdrawal'}
            </p>
            {showFundId && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-slate-700 text-slate-300">
                {transaction.fund_id}
              </span>
            )}
          </div>
          <p className="text-sm text-slate-400">
            {transaction.shares.toFixed(4)} shares @ {formatCurrency(transaction.nav_per_share)}/share
          </p>
        </div>
      </div>

      <div className="flex items-center gap-4">
        {/* Amount */}
        <div className="text-right">
          <p className={cn(
            'font-semibold',
            isDeposit ? 'text-green-400' : 'text-red-400'
          )}>
            {isDeposit ? '+' : '-'}{formatCurrency(transaction.amount_usd)}
          </p>
          <p className="text-xs text-slate-500">
            {getTimeAgo(transaction.created_at)}
          </p>
        </div>

        {/* Status */}
        <div className={cn(
          'flex items-center gap-1.5 px-3 py-1.5 rounded-lg',
          status.bgColor
        )}>
          <StatusIcon className={cn(
            'w-4 h-4',
            status.color,
            transaction.status === 'PENDING' && 'animate-spin'
          )} />
          <span className={cn('text-sm font-medium', status.color)}>
            {status.label}
          </span>
        </div>
      </div>
    </div>
  )
}

// Table header for transaction list
export function TransactionTableHeader() {
  return (
    <div className="grid grid-cols-5 gap-4 px-4 py-3 bg-slate-800/50 text-sm font-medium text-slate-400 border-b border-slate-800">
      <div className="col-span-2">Transaction</div>
      <div className="text-right">Amount</div>
      <div className="text-right">Date</div>
      <div className="text-right">Status</div>
    </div>
  )
}

// Skeleton for loading state
export function TransactionRowSkeleton() {
  return (
    <div className="flex items-center justify-between p-4 animate-pulse">
      <div className="flex items-center gap-4">
        <div className="w-10 h-10 rounded-lg bg-slate-700" />
        <div>
          <div className="h-4 w-24 bg-slate-700 rounded mb-2" />
          <div className="h-3 w-32 bg-slate-700 rounded" />
        </div>
      </div>
      <div className="flex items-center gap-4">
        <div className="text-right">
          <div className="h-4 w-16 bg-slate-700 rounded mb-1" />
          <div className="h-3 w-12 bg-slate-700 rounded" />
        </div>
        <div className="h-8 w-24 bg-slate-700 rounded-lg" />
      </div>
    </div>
  )
}

export default TransactionRow
