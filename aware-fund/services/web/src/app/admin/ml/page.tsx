'use client'

import { useState, useEffect } from 'react'
import {
  Brain,
  Activity,
  AlertTriangle,
  CheckCircle,
  XCircle,
  BarChart3,
  Loader2,
  AlertCircle,
  Clock,
  Users,
  RefreshCw,
  TrendingUp,
  History,
  Target,
  Zap,
} from 'lucide-react'
import { cn, formatNumber, getTimeAgo } from '@/lib/utils'
import { api, MLHealthResponse, ModelInfoResponse, FeatureImportanceResponse, TrainingRunResponse } from '@/lib/api'

// Tier colors for distribution chart
const tierColors: Record<string, string> = {
  DIAMOND: 'bg-cyan-400',
  GOLD: 'bg-yellow-400',
  SILVER: 'bg-slate-400',
  BRONZE: 'bg-orange-400',
}

// Drift status config
const driftStatusConfig: Record<string, { icon: typeof CheckCircle; color: string; bgColor: string; label: string }> = {
  normal: {
    icon: CheckCircle,
    color: 'text-green-400',
    bgColor: 'bg-green-500/10',
    label: 'Healthy',
  },
  warning: {
    icon: AlertTriangle,
    color: 'text-yellow-400',
    bgColor: 'bg-yellow-500/10',
    label: 'Warning',
  },
  critical: {
    icon: XCircle,
    color: 'text-red-400',
    bgColor: 'bg-red-500/10',
    label: 'Critical',
  },
}

export default function MLMonitoringPage() {
  const [health, setHealth] = useState<MLHealthResponse | null>(null)
  const [modelInfo, setModelInfo] = useState<ModelInfoResponse | null>(null)
  const [featureImportance, setFeatureImportance] = useState<FeatureImportanceResponse | null>(null)
  const [trainingHistory, setTrainingHistory] = useState<TrainingRunResponse | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [isRefreshing, setIsRefreshing] = useState(false)

  const fetchAllData = async () => {
    try {
      setError(null)
      const [healthData, modelData, featuresData, historyData] = await Promise.all([
        api.getMLHealth().catch(() => null),
        api.getModelInfo().catch(() => null),
        api.getFeatureImportance(15).catch(() => null),
        api.getTrainingHistory(5).catch(() => null),
      ])

      if (healthData) setHealth(healthData)
      if (modelData) setModelInfo(modelData)
      if (featuresData) setFeatureImportance(featuresData)
      if (historyData) setTrainingHistory(historyData)

      if (!healthData && !modelData) {
        setError('Failed to load ML health status')
      }
    } catch (err) {
      console.error('Failed to fetch ML data:', err)
      setError('Failed to load ML health status')
    }
  }

  useEffect(() => {
    setIsLoading(true)
    fetchAllData().finally(() => setIsLoading(false))

    // Auto-refresh every 60 seconds
    const interval = setInterval(fetchAllData, 60000)
    return () => clearInterval(interval)
  }, [])

  const handleRefresh = async () => {
    setIsRefreshing(true)
    await fetchAllData()
    setIsRefreshing(false)
  }

  // Calculate tier distribution total
  const totalTraders = health?.tier_distribution
    ? Object.values(health.tier_distribution).reduce((a, b) => a + b, 0)
    : 0

  // Get drift status config with safe fallback
  const driftConfig = health?.drift_status
    ? (driftStatusConfig[health.drift_status] ?? driftStatusConfig.normal)
    : driftStatusConfig.normal
  const DriftIcon = driftConfig?.icon ?? CheckCircle

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-3">
            <Brain className="h-7 w-7 text-aware-400" />
            ML Pipeline Status
          </h1>
          <p className="text-slate-400 mt-1">
            Monitor model health, drift detection, and scoring statistics
          </p>
        </div>

        <button
          onClick={handleRefresh}
          disabled={isRefreshing}
          className="flex items-center gap-2 px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white rounded-lg transition-colors disabled:opacity-50"
        >
          <RefreshCw className={cn('w-4 h-4', isRefreshing && 'animate-spin')} />
          Refresh
        </button>
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
          <span className="ml-3 text-slate-400">Loading ML status...</span>
        </div>
      )}

      {!isLoading && health && (
        <>
          {/* Status Cards */}
          <div className="grid md:grid-cols-4 gap-4">
            {/* Overall Status */}
            <div className={cn(
              'rounded-xl border p-6',
              health.status === 'healthy'
                ? 'bg-green-500/10 border-green-500/30'
                : health.status === 'degraded'
                ? 'bg-yellow-500/10 border-yellow-500/30'
                : 'bg-red-500/10 border-red-500/30'
            )}>
              <div className="flex items-center gap-3 mb-2">
                {health.status === 'healthy' ? (
                  <CheckCircle className="w-6 h-6 text-green-400" />
                ) : health.status === 'degraded' ? (
                  <AlertTriangle className="w-6 h-6 text-yellow-400" />
                ) : (
                  <XCircle className="w-6 h-6 text-red-400" />
                )}
                <span className="text-slate-300 text-sm">Pipeline Status</span>
              </div>
              <p className={cn(
                'text-2xl font-bold capitalize',
                health.status === 'healthy' ? 'text-green-400' :
                health.status === 'degraded' ? 'text-yellow-400' : 'text-red-400'
              )}>
                {health.status}
              </p>
            </div>

            {/* Model Version */}
            <div className="rounded-xl bg-slate-900/50 border border-slate-800 p-6">
              <div className="flex items-center gap-3 mb-2">
                <Brain className="w-6 h-6 text-aware-400" />
                <span className="text-slate-300 text-sm">Model Version</span>
              </div>
              <p className="text-2xl font-bold text-white font-mono">
                {health.model_version}
              </p>
            </div>

            {/* Scoring Method */}
            <div className="rounded-xl bg-slate-900/50 border border-slate-800 p-6">
              <div className="flex items-center gap-3 mb-2">
                <Activity className="w-6 h-6 text-purple-400" />
                <span className="text-slate-300 text-sm">Scoring Method</span>
              </div>
              <p className={cn(
                'text-2xl font-bold',
                health.scoring_method === 'ml_ensemble' ? 'text-aware-400' : 'text-slate-400'
              )}>
                {health.scoring_method === 'ml_ensemble' ? 'ML Ensemble' : 'Rule-based'}
              </p>
            </div>

            {/* Traders Scored */}
            <div className="rounded-xl bg-slate-900/50 border border-slate-800 p-6">
              <div className="flex items-center gap-3 mb-2">
                <Users className="w-6 h-6 text-blue-400" />
                <span className="text-slate-300 text-sm">Traders Scored</span>
              </div>
              <p className="text-2xl font-bold text-white">
                {formatNumber(health.traders_scored, 0)}
              </p>
            </div>
          </div>

          {/* Drift Detection Section */}
          <div className="rounded-xl bg-slate-900/50 border border-slate-800 overflow-hidden">
            <div className="p-4 border-b border-slate-800 flex items-center justify-between">
              <h3 className="font-semibold text-white flex items-center gap-2">
                <AlertTriangle className="w-5 h-5 text-yellow-400" />
                Drift Detection
              </h3>
              <div className={cn(
                'flex items-center gap-2 px-3 py-1.5 rounded-lg',
                driftConfig.bgColor
              )}>
                <DriftIcon className={cn('w-4 h-4', driftConfig.color)} />
                <span className={cn('text-sm font-medium', driftConfig.color)}>
                  {driftConfig.label}
                </span>
              </div>
            </div>

            <div className="p-6">
              <div className="grid md:grid-cols-2 gap-6">
                {/* Drift Ratio */}
                <div>
                  <p className="text-sm text-slate-400 mb-2">Feature Drift Ratio</p>
                  <div className="relative h-4 bg-slate-800 rounded-full overflow-hidden">
                    <div
                      className={cn(
                        'absolute h-full rounded-full transition-all',
                        health.drift_ratio < 0.1 ? 'bg-green-500' :
                        health.drift_ratio < 0.3 ? 'bg-yellow-500' : 'bg-red-500'
                      )}
                      style={{ width: `${Math.min(health.drift_ratio * 100, 100)}%` }}
                    />
                  </div>
                  <div className="flex justify-between mt-1">
                    <span className="text-xs text-slate-500">0%</span>
                    <span className={cn(
                      'text-sm font-medium',
                      health.drift_ratio < 0.1 ? 'text-green-400' :
                      health.drift_ratio < 0.3 ? 'text-yellow-400' : 'text-red-400'
                    )}>
                      {(health.drift_ratio * 100).toFixed(1)}%
                    </span>
                    <span className="text-xs text-slate-500">100%</span>
                  </div>
                </div>

                {/* Drifted Features */}
                <div>
                  <p className="text-sm text-slate-400 mb-2">Drifted Features</p>
                  {health.drifted_features.length === 0 ? (
                    <p className="text-green-400 flex items-center gap-2">
                      <CheckCircle className="w-4 h-4" />
                      No significant drift detected
                    </p>
                  ) : (
                    <div className="flex flex-wrap gap-2">
                      {health.drifted_features.map((feature) => (
                        <span
                          key={feature}
                          className="px-2 py-1 bg-red-500/20 text-red-400 text-xs rounded-full"
                        >
                          {feature}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* Tier Distribution */}
          <div className="rounded-xl bg-slate-900/50 border border-slate-800 overflow-hidden">
            <div className="p-4 border-b border-slate-800">
              <h3 className="font-semibold text-white flex items-center gap-2">
                <BarChart3 className="w-5 h-5 text-aware-400" />
                Tier Distribution
              </h3>
            </div>

            <div className="p-6">
              <div className="space-y-4">
                {Object.entries(health.tier_distribution).map(([tier, count]) => {
                  const percentage = totalTraders > 0 ? (count / totalTraders) * 100 : 0

                  return (
                    <div key={tier} className="flex items-center gap-4">
                      <div className="w-24 text-sm font-medium text-slate-300">
                        {tier}
                      </div>
                      <div className="flex-1 h-8 bg-slate-800 rounded-lg overflow-hidden relative">
                        <div
                          className={cn(
                            'h-full rounded-lg transition-all',
                            tierColors[tier] || 'bg-slate-500'
                          )}
                          style={{ width: `${percentage}%` }}
                        />
                        <span className="absolute inset-0 flex items-center justify-center text-sm font-medium text-white">
                          {count.toLocaleString()} ({percentage.toFixed(1)}%)
                        </span>
                      </div>
                    </div>
                  )
                })}
              </div>

              {/* Distribution Summary */}
              <div className="mt-6 pt-4 border-t border-slate-800 grid grid-cols-4 gap-4">
                {Object.entries(health.tier_distribution).map(([tier, count]) => (
                  <div key={tier} className="text-center">
                    <div className={cn(
                      'inline-flex w-4 h-4 rounded-full mb-1',
                      tierColors[tier] || 'bg-slate-500'
                    )} />
                    <p className="text-lg font-bold text-white">{count.toLocaleString()}</p>
                    <p className="text-xs text-slate-500">{tier}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Model Accuracy Metrics */}
          {modelInfo && (
            <div className="grid md:grid-cols-3 gap-4">
              <div className="rounded-xl bg-slate-900/50 border border-slate-800 p-6">
                <div className="flex items-center gap-3 mb-2">
                  <Target className="w-6 h-6 text-green-400" />
                  <span className="text-slate-300 text-sm">Tier Accuracy</span>
                </div>
                <p className="text-2xl font-bold text-white">
                  {(modelInfo.tier_accuracy * 100).toFixed(1)}%
                </p>
                <p className="text-xs text-slate-500 mt-1">Model classification accuracy</p>
              </div>

              <div className="rounded-xl bg-slate-900/50 border border-slate-800 p-6">
                <div className="flex items-center gap-3 mb-2">
                  <TrendingUp className="w-6 h-6 text-blue-400" />
                  <span className="text-slate-300 text-sm">Sharpe MAE</span>
                </div>
                <p className="text-2xl font-bold text-white">
                  {modelInfo.sharpe_mae.toFixed(3)}
                </p>
                <p className="text-xs text-slate-500 mt-1">Mean absolute error on Sharpe</p>
              </div>

              <div className="rounded-xl bg-slate-900/50 border border-slate-800 p-6">
                <div className="flex items-center gap-3 mb-2">
                  <Users className="w-6 h-6 text-purple-400" />
                  <span className="text-slate-300 text-sm">Trained On</span>
                </div>
                <p className="text-2xl font-bold text-white">
                  {formatNumber(modelInfo.n_traders_trained, 0)}
                </p>
                <p className="text-xs text-slate-500 mt-1">Traders in training set</p>
              </div>
            </div>
          )}

          {/* Feature Importance Section */}
          {featureImportance && featureImportance.features.length > 0 && (
            <div className="rounded-xl bg-slate-900/50 border border-slate-800 overflow-hidden">
              <div className="p-4 border-b border-slate-800">
                <h3 className="font-semibold text-white flex items-center gap-2">
                  <Zap className="w-5 h-5 text-yellow-400" />
                  Top Feature Importance
                </h3>
              </div>

              <div className="p-6">
                <div className="space-y-3">
                  {featureImportance.features.slice(0, 10).map((feature, idx) => {
                    const maxImportance = featureImportance.features[0]?.importance || 1
                    const percentage = (feature.importance / maxImportance) * 100

                    return (
                      <div key={feature.name} className="flex items-center gap-4">
                        <div className="w-8 text-sm text-slate-500">#{idx + 1}</div>
                        <div className="w-40 text-sm font-medium text-slate-300 truncate">
                          {feature.name}
                        </div>
                        <div className="flex-1 h-6 bg-slate-800 rounded overflow-hidden relative">
                          <div
                            className="h-full bg-gradient-to-r from-aware-500 to-aware-400 rounded transition-all"
                            style={{ width: `${percentage}%` }}
                          />
                        </div>
                        <div className="w-16 text-right text-sm text-slate-400">
                          {feature.importance.toFixed(3)}
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            </div>
          )}

          {/* Training History Section */}
          {trainingHistory && trainingHistory.runs.length > 0 && (
            <div className="rounded-xl bg-slate-900/50 border border-slate-800 overflow-hidden">
              <div className="p-4 border-b border-slate-800">
                <h3 className="font-semibold text-white flex items-center gap-2">
                  <History className="w-5 h-5 text-slate-400" />
                  Training History
                </h3>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-slate-800/50">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-medium text-slate-400 uppercase">Version</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-slate-400 uppercase">Date</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-slate-400 uppercase">Status</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-slate-400 uppercase">Trigger</th>
                      <th className="px-4 py-3 text-right text-xs font-medium text-slate-400 uppercase">Accuracy</th>
                      <th className="px-4 py-3 text-right text-xs font-medium text-slate-400 uppercase">Duration</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800">
                    {trainingHistory.runs.map((run) => (
                      <tr key={run.run_id} className="hover:bg-slate-800/30">
                        <td className="px-4 py-3 text-sm font-mono text-white">{run.model_version}</td>
                        <td className="px-4 py-3 text-sm text-slate-400">
                          {run.completed_at ? getTimeAgo(run.completed_at) : 'In progress'}
                        </td>
                        <td className="px-4 py-3">
                          <span className={cn(
                            'px-2 py-1 text-xs rounded-full',
                            run.status === 'success' ? 'bg-green-500/20 text-green-400' :
                            run.status === 'failed' ? 'bg-red-500/20 text-red-400' :
                            'bg-yellow-500/20 text-yellow-400'
                          )}>
                            {run.status}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-sm text-slate-400">{run.trigger_reason || '-'}</td>
                        <td className="px-4 py-3 text-sm text-right text-slate-300">
                          {run.tier_accuracy ? `${(run.tier_accuracy * 100).toFixed(1)}%` : '-'}
                        </td>
                        <td className="px-4 py-3 text-sm text-right text-slate-400">
                          {run.duration_seconds ? `${Math.round(run.duration_seconds / 60)}m` : '-'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Last Update Info */}
          <div className="flex items-center justify-center gap-2 text-sm text-slate-500">
            <Clock className="w-4 h-4" />
            {health.last_scoring_at ? (
              <span>Last scoring: {getTimeAgo(health.last_scoring_at)}</span>
            ) : (
              <span>No scoring data available</span>
            )}
          </div>
        </>
      )}

      {/* Fallback when no health data */}
      {!isLoading && !health && !error && (
        <div className="rounded-xl bg-slate-900/50 border border-slate-800 p-12 text-center">
          <Brain className="w-12 h-12 text-slate-600 mx-auto mb-4" />
          <h3 className="text-lg font-semibold text-white mb-2">ML Pipeline Not Available</h3>
          <p className="text-slate-400 max-w-md mx-auto">
            The ML scoring pipeline hasn't been initialized yet. Run the training script to get started.
          </p>
          <code className="block mt-4 p-3 bg-slate-800 rounded-lg text-sm text-slate-300 font-mono">
            python ml/training/train.py --no-cache
          </code>
        </div>
      )}
    </div>
  )
}
