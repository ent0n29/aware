'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import {
  ArrowLeft,
  ArrowDownLeft,
  DollarSign,
  AlertCircle,
  CheckCircle,
  Loader2,
  Info,
} from 'lucide-react'
import { cn, formatCurrency } from '@/lib/utils'
import { api, FundInfo, DepositRequest, TransactionResponse } from '@/lib/api'
import { FundSelector } from '@/components/invest/FundSelector'

export default function DepositPage() {
  const router = useRouter()
  const [walletAddress, setWalletAddress] = useState<string>('')
  const [funds, setFunds] = useState<FundInfo[]>([])
  const [selectedFundId, setSelectedFundId] = useState<string>('')
  const [amount, setAmount] = useState<string>('')
  const [isLoadingFunds, setIsLoadingFunds] = useState(true)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<TransactionResponse | null>(null)

  // Load wallet from localStorage
  useEffect(() => {
    const saved = localStorage.getItem('aware_wallet_address')
    if (!saved) {
      router.push('/invest')
      return
    }
    setWalletAddress(saved)
  }, [router])

  // Fetch available funds
  useEffect(() => {
    async function fetchFunds() {
      try {
        const data = await api.getFunds()
        setFunds(data.funds.filter(f => f.is_active))
      } catch (err) {
        console.error('Failed to fetch funds:', err)
        setError('Failed to load available funds')
      } finally {
        setIsLoadingFunds(false)
      }
    }
    fetchFunds()
  }, [])

  // Get selected fund details
  const selectedFund = funds.find(f => f.fund_id === selectedFundId)

  // Calculate estimated shares
  const amountNum = parseFloat(amount) || 0
  const estimatedShares = selectedFund && selectedFund.nav_per_share > 0
    ? amountNum / selectedFund.nav_per_share
    : 0

  // Validate form
  const isValid = walletAddress && selectedFundId && amountNum >= 10

  // Handle submit
  const handleSubmit = async () => {
    if (!isValid || isSubmitting) return

    setIsSubmitting(true)
    setError(null)

    try {
      const request: DepositRequest = {
        wallet_address: walletAddress,
        fund_id: selectedFundId,
        amount_usd: amountNum,
      }

      const response = await api.deposit(request)
      setSuccess(response)
    } catch (err: any) {
      setError(err.message || 'Failed to process deposit')
    } finally {
      setIsSubmitting(false)
    }
  }

  // Success state
  if (success) {
    return (
      <div className="max-w-lg mx-auto">
        <div className="rounded-xl bg-slate-900/50 border border-slate-800 p-8 text-center">
          <div className="w-16 h-16 rounded-full bg-green-500/20 flex items-center justify-center mx-auto mb-4">
            <CheckCircle className="w-8 h-8 text-green-400" />
          </div>

          <h2 className="text-2xl font-bold text-white mb-2">
            Deposit Successful!
          </h2>
          <p className="text-slate-400 mb-6">
            Your deposit has been processed successfully
          </p>

          <div className="bg-slate-800/50 rounded-lg p-4 mb-6 text-left">
            <div className="space-y-3">
              <div className="flex justify-between">
                <span className="text-slate-400">Amount</span>
                <span className="text-white font-medium">{formatCurrency(success.amount_usd)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Fund</span>
                <span className="text-white font-medium">{success.fund_id}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Shares Received</span>
                <span className="text-green-400 font-medium">{success.shares.toFixed(4)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">NAV per Share</span>
                <span className="text-white font-medium">{formatCurrency(success.nav_per_share)}</span>
              </div>
            </div>
          </div>

          <div className="flex gap-3">
            <Link
              href="/invest"
              className="flex-1 px-6 py-3 bg-slate-700 hover:bg-slate-600 text-white font-medium rounded-lg transition-colors text-center"
            >
              View Portfolio
            </Link>
            <button
              onClick={() => {
                setSuccess(null)
                setAmount('')
                setSelectedFundId('')
              }}
              className="flex-1 px-6 py-3 bg-aware-500 hover:bg-aware-600 text-white font-medium rounded-lg transition-colors"
            >
              Deposit More
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="max-w-lg mx-auto space-y-6">
      {/* Header */}
      <div>
        <Link
          href="/invest"
          className="inline-flex items-center gap-2 text-slate-400 hover:text-white mb-4 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Portfolio
        </Link>

        <h1 className="text-2xl font-bold text-white flex items-center gap-3">
          <ArrowDownLeft className="h-7 w-7 text-green-400" />
          Deposit Funds
        </h1>
        <p className="text-slate-400 mt-1">
          Invest in an AWARE fund to start earning
        </p>
      </div>

      {/* Error State */}
      {error && (
        <div className="rounded-xl bg-red-500/10 border border-red-500/30 p-4 flex items-center gap-3">
          <AlertCircle className="h-5 w-5 text-red-400 flex-shrink-0" />
          <p className="text-red-400">{error}</p>
        </div>
      )}

      {/* Deposit Form */}
      <div className="rounded-xl bg-slate-900/50 border border-slate-800 p-6 space-y-6">
        {/* Fund Selection */}
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-2">
            Select Fund
          </label>
          {isLoadingFunds ? (
            <div className="h-14 bg-slate-800 rounded-xl animate-pulse" />
          ) : (
            <FundSelector
              funds={funds}
              selectedFundId={selectedFundId}
              onSelect={setSelectedFundId}
            />
          )}
        </div>

        {/* Amount Input */}
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-2">
            Amount (USDC)
          </label>
          <div className="relative">
            <DollarSign className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-500" />
            <input
              type="number"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="0.00"
              min="10"
              step="0.01"
              className="w-full pl-12 pr-4 py-4 bg-slate-800 border border-slate-700 rounded-xl text-white text-lg font-medium placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-aware-500/50"
            />
          </div>
          <div className="flex justify-between mt-2">
            <span className="text-xs text-slate-500">Minimum: $10</span>
            <div className="flex gap-2">
              {[100, 500, 1000].map((preset) => (
                <button
                  key={preset}
                  onClick={() => setAmount(preset.toString())}
                  className="px-2 py-1 text-xs bg-slate-700 hover:bg-slate-600 text-slate-300 rounded transition-colors"
                >
                  ${preset}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Summary */}
        {selectedFund && amountNum > 0 && (
          <div className="bg-slate-800/50 rounded-lg p-4 space-y-3">
            <h4 className="text-sm font-medium text-slate-400">Transaction Summary</h4>
            <div className="flex justify-between">
              <span className="text-slate-400">Deposit Amount</span>
              <span className="text-white font-medium">{formatCurrency(amountNum)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">Current NAV</span>
              <span className="text-white font-medium">{formatCurrency(selectedFund.nav_per_share)}/share</span>
            </div>
            <div className="flex justify-between pt-2 border-t border-slate-700">
              <span className="text-slate-400">Est. Shares to Receive</span>
              <span className="text-green-400 font-semibold">{estimatedShares.toFixed(4)}</span>
            </div>
          </div>
        )}

        {/* Info Note */}
        <div className="flex items-start gap-3 p-3 bg-blue-500/10 border border-blue-500/30 rounded-lg">
          <Info className="w-5 h-5 text-blue-400 flex-shrink-0 mt-0.5" />
          <div className="text-sm text-blue-300">
            <p>
              Shares are issued at the current NAV price. Actual shares received may vary
              slightly due to price changes between order and execution.
            </p>
          </div>
        </div>

        {/* Submit Button */}
        <button
          onClick={handleSubmit}
          disabled={!isValid || isSubmitting}
          className={cn(
            'w-full py-4 rounded-xl font-semibold text-lg transition-all flex items-center justify-center gap-2',
            isValid && !isSubmitting
              ? 'bg-green-500 hover:bg-green-600 text-white'
              : 'bg-slate-700 text-slate-500 cursor-not-allowed'
          )}
        >
          {isSubmitting ? (
            <>
              <Loader2 className="w-5 h-5 animate-spin" />
              Processing...
            </>
          ) : (
            <>
              <ArrowDownLeft className="w-5 h-5" />
              Deposit {amountNum > 0 ? formatCurrency(amountNum) : ''}
            </>
          )}
        </button>
      </div>
    </div>
  )
}
