'use client'

import Link from 'next/link'
import { Users, ArrowRight, Zap } from 'lucide-react'
import { cn } from '@/lib/utils'

// Mock data
const mockConsensus = [
  {
    id: 1,
    market_question: 'Will Bitcoin reach $100K by March 2025?',
    outcome: 'Yes',
    consensus_level: 85,
    traders_count: 12,
    signal_strength: 'STRONG',
  },
  {
    id: 2,
    market_question: 'Will the Fed cut rates in January?',
    outcome: 'No',
    consensus_level: 72,
    traders_count: 8,
    signal_strength: 'MODERATE',
  },
  {
    id: 3,
    market_question: 'Will Trump win the Republican primary?',
    outcome: 'Yes',
    consensus_level: 91,
    traders_count: 15,
    signal_strength: 'STRONG',
  },
]

const strengthColors: Record<string, string> = {
  STRONG: 'bg-green-500/20 text-green-400 border-green-500/30',
  MODERATE: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
  WEAK: 'bg-slate-500/20 text-slate-400 border-slate-500/30',
}

export function ConsensusAlerts() {
  return (
    <div className="rounded-xl bg-slate-900/50 border border-slate-800 overflow-hidden h-full">
      {/* Header */}
      <div className="flex items-center justify-between p-5 border-b border-slate-800">
        <div className="flex items-center gap-3">
          <div className="rounded-lg bg-purple-500/10 p-2">
            <Users className="h-5 w-5 text-purple-400" />
          </div>
          <div>
            <h3 className="font-semibold text-white">Consensus Signals</h3>
            <p className="text-xs text-slate-500">Smart money alignment</p>
          </div>
        </div>
        <Link
          href="/consensus"
          className="text-sm text-aware-400 hover:text-aware-300 transition-colors"
        >
          View all
        </Link>
      </div>

      {/* Signals List */}
      <div className="divide-y divide-slate-800">
        {mockConsensus.map((signal) => (
          <div
            key={signal.id}
            className="p-4 hover:bg-slate-800/50 transition-colors"
          >
            <div className="flex items-start justify-between gap-3 mb-2">
              <p className="text-sm text-white font-medium leading-tight line-clamp-2">
                {signal.market_question}
              </p>
              <span
                className={cn(
                  'shrink-0 px-2 py-0.5 text-xs font-medium rounded border',
                  strengthColors[signal.signal_strength]
                )}
              >
                {signal.signal_strength}
              </span>
            </div>

            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div className="flex items-center gap-1">
                  <Zap className="h-3.5 w-3.5 text-aware-400" />
                  <span className="text-sm font-semibold text-aware-400">
                    {signal.outcome}
                  </span>
                </div>
                <span className="text-xs text-slate-500">
                  {signal.traders_count} traders
                </span>
              </div>

              {/* Consensus bar */}
              <div className="flex items-center gap-2">
                <div className="w-16 h-1.5 bg-slate-800 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-aware-500 to-cyan-400 rounded-full"
                    style={{ width: `${signal.consensus_level}%` }}
                  />
                </div>
                <span className="text-xs font-medium text-slate-400">
                  {signal.consensus_level}%
                </span>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Footer */}
      <div className="p-4 bg-slate-800/30">
        <Link
          href="/consensus"
          className="flex items-center justify-center gap-2 text-sm text-slate-400 hover:text-white transition-colors"
        >
          See all consensus signals
          <ArrowRight className="h-4 w-4" />
        </Link>
      </div>
    </div>
  )
}
