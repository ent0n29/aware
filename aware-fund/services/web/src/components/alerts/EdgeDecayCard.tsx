'use client'

import { TrendingDown, AlertTriangle, Eye, UserMinus, RefreshCw } from 'lucide-react'
import { cn, formatPercent } from '@/lib/utils'
import { EdgeDecayAlert } from '@/lib/api'

interface EdgeDecayCardProps {
  alert: EdgeDecayAlert
}

const decayTypeConfig: Record<string, { icon: typeof TrendingDown; color: string; label: string }> = {
  SHARPE_DECLINE: {
    icon: TrendingDown,
    color: 'text-red-400',
    label: 'Sharpe Decline',
  },
  WIN_RATE_DECLINE: {
    icon: TrendingDown,
    color: 'text-orange-400',
    label: 'Win Rate Drop',
  },
  VOLUME_DROP: {
    icon: TrendingDown,
    color: 'text-yellow-400',
    label: 'Volume Decline',
  },
  STRATEGY_SHIFT: {
    icon: RefreshCw,
    color: 'text-purple-400',
    label: 'Strategy Shift',
  },
}

const severityConfig: Record<string, { bg: string; border: string; color: string }> = {
  HIGH: {
    bg: 'bg-red-500/10',
    border: 'border-red-500/30',
    color: 'text-red-400',
  },
  MEDIUM: {
    bg: 'bg-yellow-500/10',
    border: 'border-yellow-500/30',
    color: 'text-yellow-400',
  },
  LOW: {
    bg: 'bg-slate-500/10',
    border: 'border-slate-500/30',
    color: 'text-slate-400',
  },
}

const actionConfig: Record<string, { icon: typeof Eye; color: string; label: string }> = {
  MONITOR: {
    icon: Eye,
    color: 'text-blue-400',
    label: 'Monitor',
  },
  REDUCE_WEIGHT: {
    icon: TrendingDown,
    color: 'text-yellow-400',
    label: 'Reduce Weight',
  },
  REMOVE_FROM_INDEX: {
    icon: UserMinus,
    color: 'text-red-400',
    label: 'Remove from Index',
  },
}

export function EdgeDecayCard({ alert }: EdgeDecayCardProps) {
  const decayType = decayTypeConfig[alert.decay_type] || decayTypeConfig.SHARPE_DECLINE
  const severity = severityConfig[alert.severity] || severityConfig.MEDIUM
  const action = actionConfig[alert.recommended_action] || actionConfig.MONITOR

  const DecayIcon = decayType.icon
  const ActionIcon = action.icon

  const sharpeChange = alert.current_sharpe - alert.historical_sharpe
  const winRateChange = alert.current_win_rate - alert.historical_win_rate

  return (
    <div className={cn(
      'rounded-xl border p-5 transition-all hover:shadow-lg',
      severity.bg,
      severity.border
    )}>
      {/* Header */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className={cn('p-2.5 rounded-xl', severity.bg)}>
            <DecayIcon className={cn('h-5 w-5', decayType.color)} />
          </div>
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className={cn(
                'text-xs font-bold px-2 py-0.5 rounded-full',
                severity.bg,
                severity.color
              )}>
                {alert.severity}
              </span>
              <span className={cn('text-sm font-medium', decayType.color)}>
                {decayType.label}
              </span>
            </div>
            <p className="text-white font-semibold">{alert.username}</p>
          </div>
        </div>

        {/* Recommended Action */}
        <div className={cn(
          'flex items-center gap-2 px-3 py-1.5 rounded-lg',
          action.color === 'text-red-400' ? 'bg-red-500/20' :
          action.color === 'text-yellow-400' ? 'bg-yellow-500/20' : 'bg-blue-500/20'
        )}>
          <ActionIcon className={cn('w-4 h-4', action.color)} />
          <span className={cn('text-sm font-medium', action.color)}>
            {action.label}
          </span>
        </div>
      </div>

      {/* Signal */}
      <p className="text-slate-400 text-sm mb-4">{alert.signal}</p>

      {/* Metrics Grid */}
      <div className="grid grid-cols-2 gap-4 mb-4">
        {/* Sharpe Ratio */}
        <div className="bg-slate-800/50 rounded-lg p-3">
          <p className="text-xs text-slate-500 mb-1">Sharpe Ratio</p>
          <div className="flex items-center justify-between">
            <div>
              <span className="text-slate-500 text-sm">{alert.historical_sharpe.toFixed(2)}</span>
              <span className="text-slate-500 mx-2">→</span>
              <span className={cn(
                'text-lg font-bold',
                sharpeChange < 0 ? 'text-red-400' : 'text-green-400'
              )}>
                {alert.current_sharpe.toFixed(2)}
              </span>
            </div>
            <span className={cn(
              'text-sm font-medium',
              sharpeChange < 0 ? 'text-red-400' : 'text-green-400'
            )}>
              {sharpeChange >= 0 ? '+' : ''}{sharpeChange.toFixed(2)}
            </span>
          </div>
          <div className="mt-2 h-1.5 bg-slate-700 rounded-full overflow-hidden">
            <div
              className={cn(
                'h-full rounded-full',
                alert.sharpe_decline_pct > 50 ? 'bg-red-500' :
                alert.sharpe_decline_pct > 25 ? 'bg-yellow-500' : 'bg-green-500'
              )}
              style={{ width: `${100 - Math.min(alert.sharpe_decline_pct, 100)}%` }}
            />
          </div>
          <p className="text-xs text-slate-500 mt-1">
            {alert.sharpe_decline_pct.toFixed(1)}% decline
          </p>
        </div>

        {/* Win Rate */}
        <div className="bg-slate-800/50 rounded-lg p-3">
          <p className="text-xs text-slate-500 mb-1">Win Rate</p>
          <div className="flex items-center justify-between">
            <div>
              <span className="text-slate-500 text-sm">{(alert.historical_win_rate * 100).toFixed(1)}%</span>
              <span className="text-slate-500 mx-2">→</span>
              <span className={cn(
                'text-lg font-bold',
                winRateChange < 0 ? 'text-red-400' : 'text-green-400'
              )}>
                {(alert.current_win_rate * 100).toFixed(1)}%
              </span>
            </div>
            <span className={cn(
              'text-sm font-medium',
              winRateChange < 0 ? 'text-red-400' : 'text-green-400'
            )}>
              {winRateChange >= 0 ? '+' : ''}{(winRateChange * 100).toFixed(1)}%
            </span>
          </div>
        </div>
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between pt-3 border-t border-slate-800/50 text-xs text-slate-500">
        <span>
          Detected: {new Date(alert.detected_at).toLocaleDateString()}
        </span>
        <span className="font-mono">
          {alert.proxy_address.slice(0, 6)}...{alert.proxy_address.slice(-4)}
        </span>
      </div>
    </div>
  )
}

export default EdgeDecayCard
