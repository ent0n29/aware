'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import {
  AlertTriangle,
  Eye,
  TrendingUp,
  TrendingDown,
  Users,
  DollarSign,
  Clock,
  Filter,
  Loader2,
  Zap,
  UserPlus,
  BarChart3,
  GitBranch,
  Whale,
  ExternalLink,
} from 'lucide-react'
import { cn, formatNumber, formatCurrency } from '@/lib/utils'
import { api, InsiderAlert, InsiderAlertsResponse } from '@/lib/api'

const signalTypes = {
  NEW_ACCOUNT_WHALE: {
    icon: UserPlus,
    label: 'New Account Whale',
    description: 'New account placing large bets on obscure markets',
    color: 'text-red-400',
    bg: 'bg-red-500/10',
    border: 'border-red-500/30',
  },
  VOLUME_SPIKE: {
    icon: BarChart3,
    label: 'Volume Spike',
    description: '10x+ normal volume before news event',
    color: 'text-orange-400',
    bg: 'bg-orange-500/10',
    border: 'border-orange-500/30',
  },
  SMART_MONEY_DIVERGENCE: {
    icon: GitBranch,
    label: 'Smart Money Divergence',
    description: 'Top traders betting against market consensus',
    color: 'text-yellow-400',
    bg: 'bg-yellow-500/10',
    border: 'border-yellow-500/30',
  },
  WHALE_ANOMALY: {
    icon: Whale,
    label: 'Whale Anomaly',
    description: 'Known whale entering unusual market category',
    color: 'text-purple-400',
    bg: 'bg-purple-500/10',
    border: 'border-purple-500/30',
  },
}

const severityConfig = {
  CRITICAL: {
    color: 'text-red-400',
    bg: 'bg-red-500/20',
    border: 'border-red-500/50',
    badge: 'bg-red-500',
  },
  HIGH: {
    color: 'text-orange-400',
    bg: 'bg-orange-500/20',
    border: 'border-orange-500/50',
    badge: 'bg-orange-500',
  },
  MEDIUM: {
    color: 'text-yellow-400',
    bg: 'bg-yellow-500/20',
    border: 'border-yellow-500/50',
    badge: 'bg-yellow-500',
  },
  LOW: {
    color: 'text-slate-400',
    bg: 'bg-slate-500/20',
    border: 'border-slate-500/50',
    badge: 'bg-slate-500',
  },
}

export default function InsiderAlertsPage() {
  const [alerts, setAlerts] = useState<InsiderAlert[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedType, setSelectedType] = useState<string | null>(null)
  const [selectedSeverity, setSelectedSeverity] = useState<string | null>(null)
  const [lookbackHours, setLookbackHours] = useState(48)

  useEffect(() => {
    async function fetchAlerts() {
      try {
        setIsLoading(true)
        setError(null)

        const response = await api.getInsiderAlerts(lookbackHours, 0.3)
        setAlerts(response.alerts)
      } catch (err) {
        setError('Failed to load insider alerts. Make sure the API server is running.')
        console.error('Insider alerts fetch error:', err)
      } finally {
        setIsLoading(false)
      }
    }
    fetchAlerts()
  }, [lookbackHours])

  const filteredAlerts = alerts.filter((alert) => {
    if (selectedType && alert.signal_type !== selectedType) return false
    if (selectedSeverity && alert.severity !== selectedSeverity) return false
    return true
  })

  // Group by severity for summary
  const criticalCount = alerts.filter((a) => a.severity === 'CRITICAL').length
  const highCount = alerts.filter((a) => a.severity === 'HIGH').length
  const mediumCount = alerts.filter((a) => a.severity === 'MEDIUM').length

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white flex items-center gap-3">
          <AlertTriangle className="h-7 w-7 text-red-400" />
          Insider Alerts
        </h1>
        <p className="text-slate-400 mt-1">
          Detecting unusual trading activity that may indicate insider knowledge
        </p>
      </div>

      {/* Explainer */}
      <div className="rounded-xl bg-gradient-to-r from-red-500/10 via-orange-500/10 to-yellow-500/10 border border-red-500/20 p-6">
        <div className="flex items-start gap-4">
          <div className="p-3 rounded-xl bg-red-500/20">
            <Eye className="h-6 w-6 text-red-400" />
          </div>
          <div>
            <h3 className="font-semibold text-white text-lg mb-2">Insider Activity Detection</h3>
            <p className="text-sm text-slate-400 mb-4">
              Our algorithms scan for suspicious trading patterns that may indicate someone has
              advance knowledge of market outcomes. Prediction markets have no insider trading laws,
              but detecting this activity creates massive alpha opportunities.
            </p>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {Object.entries(signalTypes).map(([key, type]) => (
                <div key={key} className={cn('p-3 rounded-lg', type.bg, type.border, 'border')}>
                  <type.icon className={cn('h-5 w-5 mb-2', type.color)} />
                  <p className="text-sm font-medium text-white">{type.label}</p>
                  <p className="text-xs text-slate-500 mt-1">{type.description}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Summary Stats */}
      {!isLoading && alerts.length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="rounded-xl bg-slate-900/50 border border-slate-800 p-4">
            <div className="flex items-center gap-2 mb-2">
              <AlertTriangle className="h-4 w-4 text-slate-400" />
              <span className="text-xs text-slate-400">Total Alerts</span>
            </div>
            <p className="text-2xl font-bold text-white">{alerts.length}</p>
            <p className="text-xs text-slate-500">Last {lookbackHours}h</p>
          </div>
          <div className="rounded-xl bg-red-500/10 border border-red-500/30 p-4">
            <div className="flex items-center gap-2 mb-2">
              <Zap className="h-4 w-4 text-red-400" />
              <span className="text-xs text-red-400">Critical</span>
            </div>
            <p className="text-2xl font-bold text-red-400">{criticalCount}</p>
            <p className="text-xs text-slate-500">Immediate attention</p>
          </div>
          <div className="rounded-xl bg-orange-500/10 border border-orange-500/30 p-4">
            <div className="flex items-center gap-2 mb-2">
              <AlertTriangle className="h-4 w-4 text-orange-400" />
              <span className="text-xs text-orange-400">High</span>
            </div>
            <p className="text-2xl font-bold text-orange-400">{highCount}</p>
            <p className="text-xs text-slate-500">Worth investigating</p>
          </div>
          <div className="rounded-xl bg-yellow-500/10 border border-yellow-500/30 p-4">
            <div className="flex items-center gap-2 mb-2">
              <Clock className="h-4 w-4 text-yellow-400" />
              <span className="text-xs text-yellow-400">Medium</span>
            </div>
            <p className="text-2xl font-bold text-yellow-400">{mediumCount}</p>
            <p className="text-xs text-slate-500">Monitor</p>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap gap-2">
        {/* Type Filter */}
        <button
          onClick={() => setSelectedType(null)}
          className={cn(
            'px-4 py-2 text-sm font-medium rounded-lg transition-all',
            !selectedType
              ? 'bg-aware-500/20 text-aware-400 ring-1 ring-aware-500/50'
              : 'bg-slate-800/50 text-slate-400 hover:bg-slate-800'
          )}
        >
          All Types
        </button>
        {Object.entries(signalTypes).map(([key, type]) => (
          <button
            key={key}
            onClick={() => setSelectedType(key)}
            className={cn(
              'px-4 py-2 text-sm font-medium rounded-lg transition-all flex items-center gap-2',
              selectedType === key
                ? `${type.bg} ${type.color} ring-1 ${type.border}`
                : 'bg-slate-800/50 text-slate-400 hover:bg-slate-800'
            )}
          >
            <type.icon className="h-4 w-4" />
            {type.label}
          </button>
        ))}
      </div>

      {/* Severity Filter */}
      <div className="flex flex-wrap gap-2">
        <span className="text-xs text-slate-500 py-2">Severity:</span>
        <button
          onClick={() => setSelectedSeverity(null)}
          className={cn(
            'px-3 py-1.5 text-xs font-medium rounded-lg transition-all',
            !selectedSeverity
              ? 'bg-slate-700 text-white'
              : 'bg-slate-800/50 text-slate-400 hover:bg-slate-800'
          )}
        >
          All
        </button>
        {['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'].map((sev) => {
          const config = severityConfig[sev as keyof typeof severityConfig]
          return (
            <button
              key={sev}
              onClick={() => setSelectedSeverity(sev)}
              className={cn(
                'px-3 py-1.5 text-xs font-medium rounded-lg transition-all',
                selectedSeverity === sev
                  ? `${config.bg} ${config.color} ring-1 ${config.border}`
                  : 'bg-slate-800/50 text-slate-400 hover:bg-slate-800'
              )}
            >
              {sev}
            </button>
          )
        })}
      </div>

      {/* Loading State */}
      {isLoading && (
        <div className="rounded-xl bg-slate-900/50 border border-slate-800 p-12 flex items-center justify-center">
          <Loader2 className="h-8 w-8 text-aware-400 animate-spin" />
          <span className="ml-3 text-slate-400">Scanning for insider activity...</span>
        </div>
      )}

      {/* Error State */}
      {error && !isLoading && (
        <div className="rounded-xl bg-red-500/10 border border-red-500/30 p-6">
          <p className="text-red-400 font-medium">{error}</p>
          <p className="text-sm text-slate-400 mt-2">
            Start the API server:{' '}
            <code className="bg-slate-800 px-2 py-0.5 rounded">
              cd aware-fund/services/api && uvicorn main:app --reload
            </code>
          </p>
        </div>
      )}

      {/* Empty State */}
      {!isLoading && !error && filteredAlerts.length === 0 && (
        <div className="rounded-xl bg-slate-900/50 border border-slate-800 p-12 text-center">
          <AlertTriangle className="h-12 w-12 text-slate-600 mx-auto mb-4" />
          <p className="text-slate-400">No insider alerts detected</p>
          <p className="text-sm text-slate-500 mt-1">
            {alerts.length > 0
              ? 'No alerts match your current filters'
              : 'Run the insider detection scan to find suspicious activity'}
          </p>
        </div>
      )}

      {/* Alerts List */}
      {!isLoading && !error && filteredAlerts.length > 0 && (
        <div className="space-y-4">
          {filteredAlerts.map((alert, idx) => {
            const type = signalTypes[alert.signal_type as keyof typeof signalTypes]
            const severity = severityConfig[alert.severity as keyof typeof severityConfig]
            const Icon = type?.icon || AlertTriangle

            return (
              <div
                key={`${alert.market_slug}-${alert.signal_type}-${idx}`}
                className={cn(
                  'rounded-xl border p-5 transition-all hover:shadow-lg',
                  severity.bg,
                  severity.border
                )}
              >
                <div className="flex items-start justify-between mb-4">
                  <div className="flex items-start gap-4">
                    <div className={cn('p-3 rounded-xl', type?.bg || 'bg-slate-500/10')}>
                      <Icon className={cn('h-6 w-6', type?.color || 'text-slate-400')} />
                    </div>
                    <div>
                      <div className="flex items-center gap-3 mb-1">
                        <span
                          className={cn(
                            'text-xs font-bold px-2 py-0.5 rounded-full text-white',
                            severity.badge
                          )}
                        >
                          {alert.severity}
                        </span>
                        <span className={cn('text-sm font-medium', type?.color || 'text-slate-400')}>
                          {type?.label || alert.signal_type}
                        </span>
                      </div>
                      <p className="text-white font-semibold">{alert.market_question}</p>
                      <p className="text-sm text-slate-400 mt-1">{alert.description}</p>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="flex items-center gap-2">
                      {alert.direction === 'YES' ? (
                        <TrendingUp className="h-5 w-5 text-green-400" />
                      ) : (
                        <TrendingDown className="h-5 w-5 text-red-400" />
                      )}
                      <span
                        className={cn(
                          'text-lg font-bold',
                          alert.direction === 'YES' ? 'text-green-400' : 'text-red-400'
                        )}
                      >
                        {alert.direction}
                      </span>
                    </div>
                    <p className="text-xs text-slate-500 mt-1">
                      {Math.round(alert.confidence * 100)}% confidence
                    </p>
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-4 mb-4">
                  <div className="text-center p-3 bg-slate-800/30 rounded-lg">
                    <DollarSign className="h-4 w-4 text-slate-400 mx-auto mb-1" />
                    <p className="text-lg font-bold text-white">
                      ${formatNumber(alert.total_volume_usd, 0)}
                    </p>
                    <p className="text-xs text-slate-500">Volume</p>
                  </div>
                  <div className="text-center p-3 bg-slate-800/30 rounded-lg">
                    <Users className="h-4 w-4 text-slate-400 mx-auto mb-1" />
                    <p className="text-lg font-bold text-white">{alert.num_traders}</p>
                    <p className="text-xs text-slate-500">Traders</p>
                  </div>
                  <div className="text-center p-3 bg-slate-800/30 rounded-lg">
                    <Clock className="h-4 w-4 text-slate-400 mx-auto mb-1" />
                    <p className="text-lg font-bold text-white">
                      {new Date(alert.detected_at).toLocaleTimeString([], {
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </p>
                    <p className="text-xs text-slate-500">
                      {new Date(alert.detected_at).toLocaleDateString()}
                    </p>
                  </div>
                </div>

                {alert.traders_involved && alert.traders_involved.length > 0 && (
                  <div className="pt-3 border-t border-slate-800/50">
                    <p className="text-xs text-slate-500 mb-2">Traders Involved:</p>
                    <div className="flex flex-wrap gap-2">
                      {alert.traders_involved.slice(0, 5).map((trader) => (
                        <Link
                          key={trader}
                          href={`/traders/${trader}`}
                          className="text-xs px-2 py-1 bg-slate-800 text-slate-300 rounded hover:bg-slate-700 transition-colors"
                        >
                          {trader}
                        </Link>
                      ))}
                      {alert.traders_involved.length > 5 && (
                        <span className="text-xs px-2 py-1 text-slate-500">
                          +{alert.traders_involved.length - 5} more
                        </span>
                      )}
                    </div>
                  </div>
                )}

                <div className="mt-4 flex items-center justify-between pt-3 border-t border-slate-800/50">
                  <a
                    href={`https://polymarket.com/event/${alert.market_slug}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm text-aware-400 hover:text-aware-300 flex items-center gap-1"
                  >
                    View on Polymarket
                    <ExternalLink className="h-3 w-3" />
                  </a>
                  <button className="px-4 py-1.5 text-sm font-medium bg-aware-500/20 text-aware-400 rounded-lg hover:bg-aware-500/30 transition-colors">
                    Follow Signal
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* CTA */}
      <div className="rounded-xl bg-slate-800/50 border border-slate-700 p-6 text-center">
        <AlertTriangle className="h-8 w-8 text-red-400 mx-auto mb-3" />
        <h3 className="text-lg font-semibold text-white mb-2">Get Instant Alerts</h3>
        <p className="text-sm text-slate-400 mb-4 max-w-md mx-auto">
          Don't miss the next insider signal. Subscribe to get real-time notifications via Telegram
          or Discord when we detect suspicious activity.
        </p>
        <button className="px-6 py-2.5 bg-gradient-to-r from-red-500 to-orange-500 text-white font-medium rounded-lg hover:opacity-90 transition-opacity">
          Enable Telegram Alerts
        </button>
      </div>
    </div>
  )
}
