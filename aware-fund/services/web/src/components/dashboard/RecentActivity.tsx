'use client'

import { useState, useEffect } from 'react'
import { Activity, ArrowUpRight, ArrowDownRight, Loader2 } from 'lucide-react'
import { cn, formatCurrency, getTimeAgo } from '@/lib/utils'
import { api, RecentTrade } from '@/lib/api'

interface ActivityItem {
  id: string
  type: 'trade'
  trader: string
  tier: string
  action: string
  market: string
  outcome: string
  size: number
  timestamp: Date
}

export function RecentActivity() {
  const [activities, setActivities] = useState<ActivityItem[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function fetchActivity() {
      try {
        setIsLoading(true)
        const response = await api.getRecentActivity(50, 20)  // min_score=50, limit=20

        // Transform API response to ActivityItem format
        const items: ActivityItem[] = response.trades.map((trade, index) => ({
          id: `${trade.timestamp}-${index}`,
          type: 'trade' as const,
          trader: trade.username || 'Anonymous',
          tier: trade.smart_money_score >= 80 ? 'Diamond' :
                trade.smart_money_score >= 60 ? 'Gold' :
                trade.smart_money_score >= 40 ? 'Silver' : 'Bronze',
          action: trade.side?.toUpperCase() || 'TRADE',
          market: trade.title || trade.market_slug,
          outcome: trade.outcome || '',
          size: trade.notional || 0,
          timestamp: new Date(trade.timestamp),
        }))

        setActivities(items)
        setError(null)
      } catch (err) {
        console.error('Failed to fetch activity:', err)
        // Provide helpful error messages based on error type
        if (err instanceof TypeError && err.message.includes('fetch')) {
          setError('Cannot connect to API - is the server running?')
        } else if (err instanceof Error && err.message.includes('API error')) {
          setError('API error - check server logs')
        } else {
          setError('Failed to load activity')
        }
      } finally {
        setIsLoading(false)
      }
    }

    fetchActivity()

    // Refresh every 30 seconds for live feel
    const interval = setInterval(fetchActivity, 30000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="rounded-xl bg-slate-900/50 border border-slate-800 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between p-5 border-b border-slate-800">
        <div className="flex items-center gap-3">
          <div className="rounded-lg bg-green-500/10 p-2">
            <Activity className="h-5 w-5 text-green-400" />
          </div>
          <div>
            <h3 className="font-semibold text-white">Recent Activity</h3>
            <p className="text-xs text-slate-500">Live smart money moves</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {isLoading ? (
            <Loader2 className="h-4 w-4 animate-spin text-slate-400" />
          ) : (
            <>
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500" />
              </span>
              <span className="text-xs text-slate-500">Live</span>
            </>
          )}
        </div>
      </div>

      {/* Activity List */}
      <div className="divide-y divide-slate-800 max-h-80 overflow-y-auto">
        {error && (
          <div className="p-4 text-center text-sm text-slate-500">
            {error}
          </div>
        )}

        {!error && activities.length === 0 && !isLoading && (
          <div className="p-4 text-center text-sm text-slate-500">
            No recent activity from smart money traders
          </div>
        )}

        {activities.map((item) => (
          <div
            key={item.id}
            className="p-4 hover:bg-slate-800/30 transition-colors"
          >
            <div className="flex items-start gap-3">
              <div
                className={cn(
                  'mt-0.5 p-1.5 rounded-lg',
                  item.action === 'BUY'
                    ? 'bg-green-500/10'
                    : 'bg-red-500/10'
                )}
              >
                {item.action === 'BUY' ? (
                  <ArrowUpRight className="h-4 w-4 text-green-400" />
                ) : (
                  <ArrowDownRight className="h-4 w-4 text-red-400" />
                )}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm text-white">
                  <span className="font-medium text-aware-400">
                    {item.trader}
                  </span>{' '}
                  <span
                    className={cn(
                      'font-medium',
                      item.action === 'BUY'
                        ? 'text-green-400'
                        : 'text-red-400'
                    )}
                  >
                    {item.action === 'BUY' ? 'bought' : 'sold'}
                  </span>{' '}
                  {item.outcome && (
                    <span className="text-cyan-400">{item.outcome}</span>
                  )}
                  {item.outcome ? ' on' : ''}
                </p>
                <p className="text-sm text-slate-400 truncate">
                  {item.market}
                </p>
                <div className="flex items-center gap-3 mt-1">
                  <span className="text-xs text-slate-500">
                    {formatCurrency(item.size)}
                  </span>
                  <span className="text-xs text-slate-600">•</span>
                  <span className="text-xs text-slate-500">
                    {getTimeAgo(item.timestamp)}
                  </span>
                  <span className="text-xs text-slate-600">•</span>
                  <span className={cn(
                    'text-xs px-1.5 py-0.5 rounded',
                    item.tier === 'Diamond' ? 'bg-cyan-500/20 text-cyan-400' :
                    item.tier === 'Gold' ? 'bg-yellow-500/20 text-yellow-400' :
                    item.tier === 'Silver' ? 'bg-slate-500/20 text-slate-400' :
                    'bg-orange-500/20 text-orange-400'
                  )}>
                    {item.tier}
                  </span>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
