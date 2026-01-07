'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import {
  Wallet,
  ArrowDownLeft,
  ArrowUpRight,
  History,
  Loader2,
  AlertCircle,
  LogIn,
} from 'lucide-react'
import { cn, formatCurrency } from '@/lib/utils'
import { api, InvestorPortfolio, Transaction } from '@/lib/api'
import { PortfolioCard, PortfolioCardSkeleton } from '@/components/invest/PortfolioCard'
import { TransactionRow, TransactionRowSkeleton } from '@/components/invest/TransactionRow'

export default function InvestPage() {
  const [walletAddress, setWalletAddress] = useState<string>('')
  const [inputAddress, setInputAddress] = useState<string>('')
  const [portfolio, setPortfolio] = useState<InvestorPortfolio | null>(null)
  const [recentTransactions, setRecentTransactions] = useState<Transaction[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Load wallet from localStorage on mount
  useEffect(() => {
    const saved = localStorage.getItem('aware_wallet_address')
    if (saved) {
      setWalletAddress(saved)
      setInputAddress(saved)
    }
  }, [])

  // Fetch portfolio when wallet changes
  useEffect(() => {
    if (!walletAddress) return

    async function fetchData() {
      setIsLoading(true)
      setError(null)
      try {
        const [portfolioData, txData] = await Promise.all([
          api.getPortfolio(walletAddress),
          api.getTransactions(walletAddress, undefined, 5),
        ])
        setPortfolio(portfolioData)
        setRecentTransactions(txData.transactions)
      } catch (err) {
        console.error('Failed to fetch portfolio:', err)
        setError('Failed to load portfolio. Please check your wallet address.')
        setPortfolio(null)
        setRecentTransactions([])
      } finally {
        setIsLoading(false)
      }
    }

    fetchData()
  }, [walletAddress])

  // Handle wallet connect (simple input for MVP)
  const handleConnect = () => {
    if (!inputAddress.trim()) return
    localStorage.setItem('aware_wallet_address', inputAddress.trim())
    setWalletAddress(inputAddress.trim())
  }

  // Handle disconnect
  const handleDisconnect = () => {
    localStorage.removeItem('aware_wallet_address')
    setWalletAddress('')
    setPortfolio(null)
    setRecentTransactions([])
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-3">
            <Wallet className="h-7 w-7 text-aware-400" />
            Investor Portal
          </h1>
          <p className="text-slate-400 mt-1">
            Manage your AWARE Fund investments
          </p>
        </div>

        {/* Wallet Status */}
        {walletAddress ? (
          <div className="flex items-center gap-3">
            <div className="px-4 py-2 bg-slate-800/50 border border-slate-700 rounded-lg">
              <p className="text-xs text-slate-400">Connected Wallet</p>
              <p className="text-sm font-mono text-white">
                {walletAddress.slice(0, 6)}...{walletAddress.slice(-4)}
              </p>
            </div>
            <button
              onClick={handleDisconnect}
              className="px-4 py-2 text-sm text-red-400 hover:text-red-300 hover:bg-red-500/10 rounded-lg transition-colors"
            >
              Disconnect
            </button>
          </div>
        ) : null}
      </div>

      {/* Connect Wallet Card (when not connected) */}
      {!walletAddress && (
        <div className="rounded-xl bg-slate-900/50 border border-slate-800 p-8">
          <div className="max-w-md mx-auto text-center">
            <div className="w-16 h-16 rounded-full bg-aware-500/20 flex items-center justify-center mx-auto mb-4">
              <LogIn className="w-8 h-8 text-aware-400" />
            </div>
            <h2 className="text-xl font-semibold text-white mb-2">
              Connect Your Wallet
            </h2>
            <p className="text-slate-400 mb-6">
              Enter your wallet address to view your portfolio and manage investments
            </p>

            <div className="flex gap-3">
              <input
                type="text"
                value={inputAddress}
                onChange={(e) => setInputAddress(e.target.value)}
                placeholder="0x... or ENS name"
                className="flex-1 px-4 py-3 bg-slate-800 border border-slate-700 rounded-lg text-white placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-aware-500/50"
              />
              <button
                onClick={handleConnect}
                disabled={!inputAddress.trim()}
                className={cn(
                  'px-6 py-3 rounded-lg font-medium transition-all',
                  inputAddress.trim()
                    ? 'bg-aware-500 hover:bg-aware-600 text-white'
                    : 'bg-slate-700 text-slate-500 cursor-not-allowed'
                )}
              >
                Connect
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Error State */}
      {error && (
        <div className="rounded-xl bg-red-500/10 border border-red-500/30 p-4 flex items-center gap-3">
          <AlertCircle className="h-5 w-5 text-red-400 flex-shrink-0" />
          <p className="text-red-400">{error}</p>
        </div>
      )}

      {/* Loading State */}
      {isLoading && walletAddress && (
        <div className="space-y-6">
          <PortfolioCardSkeleton />
          <div className="rounded-xl bg-slate-900/50 border border-slate-800 overflow-hidden">
            <div className="p-4 border-b border-slate-800">
              <div className="h-6 w-32 bg-slate-700 rounded animate-pulse" />
            </div>
            {[1, 2, 3].map((i) => (
              <TransactionRowSkeleton key={i} />
            ))}
          </div>
        </div>
      )}

      {/* Portfolio Content */}
      {!isLoading && walletAddress && portfolio && (
        <div className="grid lg:grid-cols-3 gap-6">
          {/* Main Portfolio */}
          <div className="lg:col-span-2 space-y-6">
            <PortfolioCard
              holdings={portfolio.holdings}
              totalValue={portfolio.total_value_usd}
              totalPnL={portfolio.total_unrealized_pnl}
              totalPnLPct={portfolio.total_unrealized_pnl_pct}
            />

            {/* Recent Transactions */}
            <div className="rounded-xl bg-slate-900/50 border border-slate-800 overflow-hidden">
              <div className="p-4 border-b border-slate-800 flex items-center justify-between">
                <h3 className="font-semibold text-white flex items-center gap-2">
                  <History className="w-5 h-5 text-slate-400" />
                  Recent Transactions
                </h3>
                <Link
                  href="/invest/history"
                  className="text-sm text-aware-400 hover:text-aware-300"
                >
                  View all
                </Link>
              </div>

              {recentTransactions.length === 0 ? (
                <div className="p-8 text-center">
                  <History className="w-10 h-10 text-slate-600 mx-auto mb-2" />
                  <p className="text-slate-400">No transactions yet</p>
                </div>
              ) : (
                <div className="divide-y divide-slate-800">
                  {recentTransactions.map((tx) => (
                    <TransactionRow key={tx.id} transaction={tx} />
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Quick Actions Sidebar */}
          <div className="space-y-4">
            {/* Deposit Card */}
            <Link
              href="/invest/deposit"
              className="block rounded-xl bg-gradient-to-br from-green-500/10 to-emerald-500/10 border border-green-500/30 p-6 hover:border-green-500/50 transition-colors group"
            >
              <div className="w-12 h-12 rounded-xl bg-green-500/20 flex items-center justify-center mb-4 group-hover:scale-110 transition-transform">
                <ArrowDownLeft className="w-6 h-6 text-green-400" />
              </div>
              <h3 className="text-lg font-semibold text-white mb-1">Deposit</h3>
              <p className="text-sm text-slate-400">
                Add funds to your portfolio by investing in any AWARE fund
              </p>
            </Link>

            {/* Withdraw Card */}
            <Link
              href="/invest/withdraw"
              className="block rounded-xl bg-gradient-to-br from-red-500/10 to-orange-500/10 border border-red-500/30 p-6 hover:border-red-500/50 transition-colors group"
            >
              <div className="w-12 h-12 rounded-xl bg-red-500/20 flex items-center justify-center mb-4 group-hover:scale-110 transition-transform">
                <ArrowUpRight className="w-6 h-6 text-red-400" />
              </div>
              <h3 className="text-lg font-semibold text-white mb-1">Withdraw</h3>
              <p className="text-sm text-slate-400">
                Redeem your shares and withdraw funds to your wallet
              </p>
            </Link>

            {/* Quick Stats */}
            {portfolio.holdings.length > 0 && (
              <div className="rounded-xl bg-slate-900/50 border border-slate-800 p-4">
                <h4 className="text-sm font-medium text-slate-400 mb-3">Quick Stats</h4>
                <div className="space-y-3">
                  <div className="flex justify-between">
                    <span className="text-slate-400">Funds Invested</span>
                    <span className="text-white font-medium">{portfolio.holdings.length}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Cost Basis</span>
                    <span className="text-white font-medium">{formatCurrency(portfolio.total_cost_basis)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Total Return</span>
                    <span className={cn(
                      'font-medium',
                      portfolio.total_unrealized_pnl_pct >= 0 ? 'text-green-400' : 'text-red-400'
                    )}>
                      {portfolio.total_unrealized_pnl_pct >= 0 ? '+' : ''}{portfolio.total_unrealized_pnl_pct.toFixed(2)}%
                    </span>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Empty Portfolio State */}
      {!isLoading && walletAddress && portfolio && portfolio.holdings.length === 0 && (
        <div className="rounded-xl bg-slate-900/50 border border-slate-800 p-12 text-center">
          <Wallet className="w-16 h-16 text-slate-600 mx-auto mb-4" />
          <h2 className="text-xl font-semibold text-white mb-2">
            Start Your Investment Journey
          </h2>
          <p className="text-slate-400 max-w-md mx-auto mb-6">
            You haven't invested in any AWARE funds yet. Explore our funds and start building your portfolio.
          </p>
          <div className="flex justify-center gap-4">
            <Link
              href="/invest/deposit"
              className="px-6 py-3 bg-aware-500 hover:bg-aware-600 text-white font-medium rounded-lg transition-colors"
            >
              Make Your First Deposit
            </Link>
            <Link
              href="/funds"
              className="px-6 py-3 bg-slate-700 hover:bg-slate-600 text-white font-medium rounded-lg transition-colors"
            >
              Explore Funds
            </Link>
          </div>
        </div>
      )}
    </div>
  )
}
