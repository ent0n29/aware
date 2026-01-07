'use client'

import { useState } from 'react'
import { Brain, Calculator, Info } from 'lucide-react'
import { cn } from '@/lib/utils'

interface MLScoreBadgeProps {
  score: number
  tier: string
  tierConfidence?: number
  modelVersion?: string
  predictedSharpe?: number
  showTooltip?: boolean
  size?: 'sm' | 'md' | 'lg'
}

// Tier color configurations
const tierColors: Record<string, { ring: string; bg: string; text: string }> = {
  DIAMOND: {
    ring: 'ring-cyan-400',
    bg: 'bg-gradient-to-br from-cyan-400/20 to-blue-500/20',
    text: 'text-cyan-400',
  },
  GOLD: {
    ring: 'ring-yellow-400',
    bg: 'bg-gradient-to-br from-yellow-400/20 to-amber-500/20',
    text: 'text-yellow-400',
  },
  SILVER: {
    ring: 'ring-slate-300',
    bg: 'bg-gradient-to-br from-slate-300/20 to-slate-400/20',
    text: 'text-slate-300',
  },
  BRONZE: {
    ring: 'ring-orange-400',
    bg: 'bg-gradient-to-br from-orange-400/20 to-amber-600/20',
    text: 'text-orange-400',
  },
}

// Size configurations
const sizeConfig = {
  sm: {
    container: 'w-12 h-12',
    score: 'text-sm',
    icon: 'w-3 h-3',
    ring: 'ring-2',
  },
  md: {
    container: 'w-16 h-16',
    score: 'text-lg',
    icon: 'w-4 h-4',
    ring: 'ring-3',
  },
  lg: {
    container: 'w-20 h-20',
    score: 'text-xl',
    icon: 'w-5 h-5',
    ring: 'ring-4',
  },
}

export function MLScoreBadge({
  score,
  tier,
  tierConfidence,
  modelVersion,
  predictedSharpe,
  showTooltip = true,
  size = 'md',
}: MLScoreBadgeProps) {
  const [isHovered, setIsHovered] = useState(false)

  const tierKey = tier.toUpperCase()
  const colors = tierColors[tierKey] || tierColors.BRONZE
  const sizes = sizeConfig[size]
  const isML = modelVersion && !modelVersion.toLowerCase().includes('rule')

  // Calculate confidence ring opacity (thicker ring = higher confidence)
  const confidenceOpacity = tierConfidence ? Math.max(0.3, tierConfidence) : 0.5

  return (
    <div
      className="relative inline-flex flex-col items-center gap-1"
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      {/* Score Circle with Confidence Ring */}
      <div
        className={cn(
          'relative rounded-full flex items-center justify-center',
          sizes.container,
          colors.bg,
          sizes.ring,
          colors.ring,
        )}
        style={{
          boxShadow: `0 0 ${tierConfidence ? tierConfidence * 20 : 10}px ${tierKey === 'DIAMOND' ? `rgba(34, 211, 238, ${confidenceOpacity})` : tierKey === 'GOLD' ? `rgba(250, 204, 21, ${confidenceOpacity})` : 'transparent'}`
        }}
      >
        <span className={cn('font-bold', sizes.score, colors.text)}>
          {Math.round(score)}
        </span>

        {/* ML/Rule indicator badge */}
        <div
          className={cn(
            'absolute -bottom-1 -right-1 rounded-full p-1',
            isML ? 'bg-aware-500' : 'bg-slate-600',
          )}
          title={isML ? 'ML Scored' : 'Rule-based'}
        >
          {isML ? (
            <Brain className={cn(sizes.icon, 'text-white')} />
          ) : (
            <Calculator className={cn(sizes.icon, 'text-white')} />
          )}
        </div>
      </div>

      {/* Confidence Label */}
      {tierConfidence !== undefined && (
        <span className="text-xs text-slate-500">
          {(tierConfidence * 100).toFixed(0)}% conf
        </span>
      )}

      {/* Tooltip */}
      {showTooltip && isHovered && (
        <div className="absolute bottom-full mb-2 left-1/2 -translate-x-1/2 z-50">
          <div className="bg-slate-800 border border-slate-700 rounded-lg shadow-xl p-3 min-w-[180px]">
            <div className="flex items-center gap-2 mb-2 pb-2 border-b border-slate-700">
              {isML ? (
                <Brain className="w-4 h-4 text-aware-400" />
              ) : (
                <Calculator className="w-4 h-4 text-slate-400" />
              )}
              <span className="text-sm font-medium text-white">
                {isML ? 'ML Ensemble Score' : 'Rule-based Score'}
              </span>
            </div>

            <div className="space-y-1.5 text-xs">
              <div className="flex justify-between">
                <span className="text-slate-400">Score:</span>
                <span className={cn('font-semibold', colors.text)}>{score.toFixed(1)}</span>
              </div>

              <div className="flex justify-between">
                <span className="text-slate-400">Tier:</span>
                <span className={cn('font-semibold', colors.text)}>{tier}</span>
              </div>

              {tierConfidence !== undefined && (
                <div className="flex justify-between">
                  <span className="text-slate-400">Confidence:</span>
                  <span className="text-white font-semibold">
                    {(tierConfidence * 100).toFixed(1)}%
                  </span>
                </div>
              )}

              {predictedSharpe !== undefined && (
                <div className="flex justify-between">
                  <span className="text-slate-400">Pred. Sharpe:</span>
                  <span className={cn(
                    'font-semibold',
                    predictedSharpe >= 1 ? 'text-green-400' :
                    predictedSharpe >= 0 ? 'text-yellow-400' : 'text-red-400'
                  )}>
                    {predictedSharpe.toFixed(2)}
                  </span>
                </div>
              )}

              {modelVersion && (
                <div className="flex justify-between pt-1 border-t border-slate-700/50">
                  <span className="text-slate-500">Model:</span>
                  <span className="text-slate-400 font-mono text-[10px]">
                    {modelVersion}
                  </span>
                </div>
              )}
            </div>

            {/* Tooltip arrow */}
            <div className="absolute -bottom-1 left-1/2 -translate-x-1/2 w-2 h-2 bg-slate-800 border-r border-b border-slate-700 transform rotate-45" />
          </div>
        </div>
      )}
    </div>
  )
}

// Compact inline version for table rows
export function MLScoreInline({
  score,
  tier,
  tierConfidence,
  modelVersion,
}: Omit<MLScoreBadgeProps, 'showTooltip' | 'size' | 'predictedSharpe'>) {
  const tierKey = tier.toUpperCase()
  const colors = tierColors[tierKey] || tierColors.BRONZE
  const isML = modelVersion && !modelVersion.toLowerCase().includes('rule')

  return (
    <div className="flex items-center gap-2">
      <span className={cn('text-lg font-bold', colors.text)}>
        {Math.round(score)}
      </span>

      {tierConfidence !== undefined && (
        <div className="flex items-center gap-1">
          {isML ? (
            <Brain className="w-3 h-3 text-aware-400" />
          ) : (
            <Calculator className="w-3 h-3 text-slate-500" />
          )}
          <span className="text-xs text-slate-500">
            {(tierConfidence * 100).toFixed(0)}%
          </span>
        </div>
      )}
    </div>
  )
}

export default MLScoreBadge
