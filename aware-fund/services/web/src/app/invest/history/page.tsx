'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import {
  ArrowLeft,
  History,
  Filter,
  Download,
  AlertCircle,
  Loader2,
  Calendar,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { api, Transaction, FundInfo } from '@/lib/api'
import { TransactionRow, TransactionRowSkeleton } from '@/components/invest/TransactionRow'

export default function HistoryPage() {
  const router = useRouter()
  const [walletAddress, setWalletAddress] = useState<string>('')
  const [transactions, setTransactions] = useState<Transaction[]>([])
  const [funds, setFunds] = useState<FundInfo[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Filters
  const [selectedFund, setSelectedFund] = useState<string>('all')
  const [selectedType, setSelectedType] = useState<string>('all')
  const [selectedStatus, setSelectedStatus] = useState<string>('all')

  // Load wallet from localStorage
  useEffect(() => {
    const saved = localStorage.getItem('aware_wallet_address')
    if (!saved) {
      router.push('/invest')
      return
    }
    setWalletAddress(saved)
  }, [router])

  // Fetch transactions and funds
  useEffect(() => {
    if (!walletAddress) return

    async function fetchData() {
      setIsLoading(true)
      setError(null)
      try {
        const [txData, fundsData] = await Promise.all([
          api.getTransactions(walletAddress, undefined, 100),
          api.getFunds(),
        ])
        setTransactions(txData.transactions)
        setFunds(fundsData.funds)
      } catch (err) {
        console.error('Failed to fetch transactions:', err)
        setError('Failed to load transaction history')
      } finally {
        setIsLoading(false)
      }
    }

    fetchData()
  }, [walletAddress])

  // Filter transactions
  const filteredTransactions = transactions.filter(tx => {
    if (selectedFund !== 'all' && tx.fund_id !== selectedFund) return false
    if (selectedType !== 'all' && tx.transaction_type !== selectedType) return false
    if (selectedStatus !== 'all' && tx.status !== selectedStatus) return false
    return true
  })

  // Get unique fund IDs from transactions
  const uniqueFunds = Array.from(new Set(transactions.map(tx => tx.fund_id)))

  // Export to CSV
  const handleExport = () => {
    const headers = ['Date', 'Type', 'Fund', 'Amount', 'Shares', 'NAV', 'Status']
    const rows = filteredTransactions.map(tx => [
      new Date(tx.created_at).toISOString(),
      tx.transaction_type,
      tx.fund_id,
      tx.amount_usd.toFixed(2),
      tx.shares.toFixed(4),
      tx.nav_per_share.toFixed(2),
      tx.status,
    ])

    const csv = [headers, ...rows].map(row => row.join(',')).join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `aware-transactions-${new Date().toISOString().split('T')[0]}.csv`
    a.click()
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <Link
            href="/invest"
            className="inline-flex items-center gap-2 text-slate-400 hover:text-white mb-4 transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to Portfolio
          </Link>

          <h1 className="text-2xl font-bold text-white flex items-center gap-3">
            <History className="h-7 w-7 text-aware-400" />
            Transaction History
          </h1>
          <p className="text-slate-400 mt-1">
            View all your deposits and withdrawals
          </p>
        </div>

        {/* Export Button */}
        {filteredTransactions.length > 0 && (
          <button
            onClick={handleExport}
            className="inline-flex items-center gap-2 px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white rounded-lg transition-colors"
          >
            <Download className="w-4 h-4" />
            Export CSV
          </button>
        )}
      </div>

      {/* Error State */}
      {error && (
        <div className="rounded-xl bg-red-500/10 border border-red-500/30 p-4 flex items-center gap-3">
          <AlertCircle className="h-5 w-5 text-red-400 flex-shrink-0" />
          <p className="text-red-400">{error}</p>
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-4 p-4 bg-slate-900/50 border border-slate-800 rounded-xl">
        <div className="flex items-center gap-2 text-slate-400">
          <Filter className="w-4 h-4" />
          <span className="text-sm font-medium">Filters:</span>
        </div>

        {/* Fund Filter */}
        <select
          value={selectedFund}
          onChange={(e) => setSelectedFund(e.target.value)}
          className="px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-white focus:outline-none focus:ring-2 focus:ring-aware-500/50"
        >
          <option value="all">All Funds</option>
          {uniqueFunds.map(fundId => (
            <option key={fundId} value={fundId}>{fundId}</option>
          ))}
        </select>

        {/* Type Filter */}
        <select
          value={selectedType}
          onChange={(e) => setSelectedType(e.target.value)}
          className="px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-white focus:outline-none focus:ring-2 focus:ring-aware-500/50"
        >
          <option value="all">All Types</option>
          <option value="DEPOSIT">Deposits</option>
          <option value="WITHDRAWAL">Withdrawals</option>
        </select>

        {/* Status Filter */}
        <select
          value={selectedStatus}
          onChange={(e) => setSelectedStatus(e.target.value)}
          className="px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm text-white focus:outline-none focus:ring-2 focus:ring-aware-500/50"
        >
          <option value="all">All Statuses</option>
          <option value="COMPLETED">Completed</option>
          <option value="PENDING">Pending</option>
          <option value="FAILED">Failed</option>
        </select>

        {/* Results Count */}
        <span className="text-sm text-slate-500 ml-auto">
          {filteredTransactions.length} transactions
        </span>
      </div>

      {/* Transaction List */}
      <div className="rounded-xl bg-slate-900/50 border border-slate-800 overflow-hidden">
        {/* Loading State */}
        {isLoading && (
          <div className="divide-y divide-slate-800">
            {[1, 2, 3, 4, 5].map((i) => (
              <TransactionRowSkeleton key={i} />
            ))}
          </div>
        )}

        {/* Empty State */}
        {!isLoading && filteredTransactions.length === 0 && (
          <div className="p-12 text-center">
            <Calendar className="w-12 h-12 text-slate-600 mx-auto mb-4" />
            <h3 className="text-lg font-semibold text-white mb-2">
              No Transactions Found
            </h3>
            <p className="text-slate-400 max-w-sm mx-auto">
              {transactions.length === 0
                ? "You haven't made any deposits or withdrawals yet."
                : "No transactions match your current filters."}
            </p>
            {transactions.length === 0 && (
              <Link
                href="/invest/deposit"
                className="inline-block mt-4 px-6 py-3 bg-aware-500 hover:bg-aware-600 text-white font-medium rounded-lg transition-colors"
              >
                Make Your First Deposit
              </Link>
            )}
          </div>
        )}

        {/* Transaction Rows */}
        {!isLoading && filteredTransactions.length > 0 && (
          <div className="divide-y divide-slate-800">
            {filteredTransactions.map((tx) => (
              <TransactionRow key={tx.id} transaction={tx} />
            ))}
          </div>
        )}
      </div>

      {/* Summary Stats */}
      {!isLoading && transactions.length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="rounded-lg bg-slate-800/50 p-4 text-center">
            <p className="text-2xl font-bold text-white">{transactions.length}</p>
            <p className="text-sm text-slate-400">Total Transactions</p>
          </div>
          <div className="rounded-lg bg-slate-800/50 p-4 text-center">
            <p className="text-2xl font-bold text-green-400">
              {transactions.filter(tx => tx.transaction_type === 'DEPOSIT').length}
            </p>
            <p className="text-sm text-slate-400">Deposits</p>
          </div>
          <div className="rounded-lg bg-slate-800/50 p-4 text-center">
            <p className="text-2xl font-bold text-red-400">
              {transactions.filter(tx => tx.transaction_type === 'WITHDRAWAL').length}
            </p>
            <p className="text-sm text-slate-400">Withdrawals</p>
          </div>
          <div className="rounded-lg bg-slate-800/50 p-4 text-center">
            <p className="text-2xl font-bold text-yellow-400">
              {transactions.filter(tx => tx.status === 'PENDING').length}
            </p>
            <p className="text-sm text-slate-400">Pending</p>
          </div>
        </div>
      )}
    </div>
  )
}
