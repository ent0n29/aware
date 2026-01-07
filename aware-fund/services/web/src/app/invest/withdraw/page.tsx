'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import {
  ArrowLeft,
  ArrowUpRight,
  AlertCircle,
  CheckCircle,
  Loader2,
  Info,
  Wallet,
} from 'lucide-react'
import { cn, formatCurrency } from '@/lib/utils'
import { api, FundInfo, UserHolding, WithdrawRequest, TransactionResponse, InvestorPortfolio } from '@/lib/api'
import { FundSelector } from '@/components/invest/FundSelector'

export default function WithdrawPage() {
  const router = useRouter()
  const [walletAddress, setWalletAddress] = useState<string>('')
  const [portfolio, setPortfolio] = useState<InvestorPortfolio | null>(null)
  const [funds, setFunds] = useState<FundInfo[]>([])
  const [selectedFundId, setSelectedFundId] = useState<string>('')
  const [withdrawType, setWithdrawType] = useState<'shares' | 'amount' | 'all'>('shares')
  const [sharesInput, setSharesInput] = useState<string>('')
  const [amountInput, setAmountInput] = useState<string>('')
  const [isLoading, setIsLoading] = useState(true)
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

  // Fetch portfolio and funds
  useEffect(() => {
    if (!walletAddress) return

    async function fetchData() {
      try {
        const [portfolioData, fundsData] = await Promise.all([
          api.getPortfolio(walletAddress),
          api.getFunds(),
        ])
        setPortfolio(portfolioData)
        setFunds(fundsData.funds)
      } catch (err) {
        console.error('Failed to fetch data:', err)
        setError('Failed to load your holdings')
      } finally {
        setIsLoading(false)
      }
    }

    fetchData()
  }, [walletAddress])

  // Get selected holding
  const selectedHolding = portfolio?.holdings.find(h => h.fund_id === selectedFundId)
  const selectedFund = funds.find(f => f.fund_id === selectedFundId)

  // Calculate withdrawal values
  const shares = withdrawType === 'all'
    ? selectedHolding?.shares || 0
    : withdrawType === 'shares'
    ? parseFloat(sharesInput) || 0
    : selectedFund && parseFloat(amountInput)
    ? parseFloat(amountInput) / selectedFund.nav_per_share
    : 0

  const estimatedValue = selectedFund
    ? shares * selectedFund.nav_per_share
    : 0

  // Validate form
  const maxShares = selectedHolding?.shares || 0
  const isValid = walletAddress &&
    selectedFundId &&
    shares > 0 &&
    shares <= maxShares

  // Handle submit
  const handleSubmit = async () => {
    if (!isValid || isSubmitting) return

    setIsSubmitting(true)
    setError(null)

    try {
      const request: WithdrawRequest = {
        wallet_address: walletAddress,
        fund_id: selectedFundId,
        ...(withdrawType === 'all'
          ? { withdraw_all: true }
          : withdrawType === 'shares'
          ? { shares: shares }
          : { amount_usd: parseFloat(amountInput) })
      }

      const response = await api.withdraw(request)
      setSuccess(response)
    } catch (err: any) {
      setError(err.message || 'Failed to process withdrawal')
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
            Withdrawal Initiated!
          </h2>
          <p className="text-slate-400 mb-6">
            Your withdrawal is being processed
          </p>

          <div className="bg-slate-800/50 rounded-lg p-4 mb-6 text-left">
            <div className="space-y-3">
              <div className="flex justify-between">
                <span className="text-slate-400">Shares Redeemed</span>
                <span className="text-white font-medium">{success.shares.toFixed(4)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Fund</span>
                <span className="text-white font-medium">{success.fund_id}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">NAV per Share</span>
                <span className="text-white font-medium">{formatCurrency(success.nav_per_share)}</span>
              </div>
              <div className="flex justify-between pt-2 border-t border-slate-700">
                <span className="text-slate-400">Est. Amount to Receive</span>
                <span className="text-green-400 font-semibold">{formatCurrency(success.amount_usd)}</span>
              </div>
            </div>
          </div>

          <Link
            href="/invest"
            className="block w-full px-6 py-3 bg-aware-500 hover:bg-aware-600 text-white font-medium rounded-lg transition-colors text-center"
          >
            Return to Portfolio
          </Link>
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
          <ArrowUpRight className="h-7 w-7 text-red-400" />
          Withdraw Funds
        </h1>
        <p className="text-slate-400 mt-1">
          Redeem shares and withdraw to your wallet
        </p>
      </div>

      {/* Error State */}
      {error && (
        <div className="rounded-xl bg-red-500/10 border border-red-500/30 p-4 flex items-center gap-3">
          <AlertCircle className="h-5 w-5 text-red-400 flex-shrink-0" />
          <p className="text-red-400">{error}</p>
        </div>
      )}

      {/* Loading State */}
      {isLoading && (
        <div className="rounded-xl bg-slate-900/50 border border-slate-800 p-8 flex items-center justify-center">
          <Loader2 className="w-6 h-6 text-aware-400 animate-spin" />
          <span className="ml-3 text-slate-400">Loading your holdings...</span>
        </div>
      )}

      {/* No Holdings State */}
      {!isLoading && portfolio && portfolio.holdings.length === 0 && (
        <div className="rounded-xl bg-slate-900/50 border border-slate-800 p-8 text-center">
          <Wallet className="w-12 h-12 text-slate-600 mx-auto mb-4" />
          <h3 className="text-lg font-semibold text-white mb-2">No Holdings</h3>
          <p className="text-slate-400 mb-4">
            You don't have any fund holdings to withdraw from.
          </p>
          <Link
            href="/invest/deposit"
            className="inline-block px-6 py-3 bg-aware-500 hover:bg-aware-600 text-white font-medium rounded-lg transition-colors"
          >
            Make a Deposit
          </Link>
        </div>
      )}

      {/* Withdraw Form */}
      {!isLoading && portfolio && portfolio.holdings.length > 0 && (
        <div className="rounded-xl bg-slate-900/50 border border-slate-800 p-6 space-y-6">
          {/* Fund Selection */}
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-2">
              Select Fund to Withdraw From
            </label>
            <FundSelector
              funds={funds}
              selectedFundId={selectedFundId}
              userHoldings={portfolio.holdings}
              onSelect={setSelectedFundId}
              showHoldingsOnly
            />
          </div>

          {/* Show holding details */}
          {selectedHolding && (
            <div className="bg-slate-800/50 rounded-lg p-4">
              <p className="text-sm text-slate-400 mb-2">Your Position</p>
              <div className="flex justify-between">
                <span className="text-white font-medium">{selectedHolding.shares.toFixed(4)} shares</span>
                <span className="text-slate-300">{formatCurrency(selectedHolding.value_usd)}</span>
              </div>
            </div>
          )}

          {/* Withdraw Type Selection */}
          {selectedFundId && (
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-2">
                Withdrawal Amount
              </label>
              <div className="flex gap-2 mb-4">
                {[
                  { id: 'shares', label: 'By Shares' },
                  { id: 'amount', label: 'By Amount' },
                  { id: 'all', label: 'Withdraw All' },
                ].map((option) => (
                  <button
                    key={option.id}
                    onClick={() => setWithdrawType(option.id as typeof withdrawType)}
                    className={cn(
                      'flex-1 px-4 py-2 text-sm font-medium rounded-lg transition-all',
                      withdrawType === option.id
                        ? 'bg-aware-500/20 text-aware-400 ring-1 ring-aware-500/50'
                        : 'bg-slate-800 text-slate-400 hover:bg-slate-700'
                    )}
                  >
                    {option.label}
                  </button>
                ))}
              </div>

              {/* Shares Input */}
              {withdrawType === 'shares' && (
                <div className="relative">
                  <input
                    type="number"
                    value={sharesInput}
                    onChange={(e) => setSharesInput(e.target.value)}
                    placeholder="0.0000"
                    max={maxShares}
                    step="0.0001"
                    className="w-full px-4 py-4 bg-slate-800 border border-slate-700 rounded-xl text-white text-lg font-medium placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-aware-500/50"
                  />
                  <button
                    onClick={() => setSharesInput(maxShares.toString())}
                    className="absolute right-3 top-1/2 -translate-y-1/2 px-3 py-1 text-xs bg-slate-700 hover:bg-slate-600 text-slate-300 rounded transition-colors"
                  >
                    MAX
                  </button>
                </div>
              )}

              {/* Amount Input */}
              {withdrawType === 'amount' && (
                <div className="relative">
                  <span className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-500">$</span>
                  <input
                    type="number"
                    value={amountInput}
                    onChange={(e) => setAmountInput(e.target.value)}
                    placeholder="0.00"
                    max={selectedHolding?.value_usd}
                    step="0.01"
                    className="w-full pl-8 pr-4 py-4 bg-slate-800 border border-slate-700 rounded-xl text-white text-lg font-medium placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-aware-500/50"
                  />
                </div>
              )}

              {/* All confirmation */}
              {withdrawType === 'all' && selectedHolding && (
                <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-4 text-center">
                  <p className="text-yellow-300">
                    You will withdraw all <span className="font-semibold">{selectedHolding.shares.toFixed(4)}</span> shares
                  </p>
                  <p className="text-sm text-yellow-400/70 mt-1">
                    Estimated value: {formatCurrency(selectedHolding.value_usd)}
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Summary */}
          {selectedFund && shares > 0 && (
            <div className="bg-slate-800/50 rounded-lg p-4 space-y-3">
              <h4 className="text-sm font-medium text-slate-400">Withdrawal Summary</h4>
              <div className="flex justify-between">
                <span className="text-slate-400">Shares to Redeem</span>
                <span className="text-white font-medium">{shares.toFixed(4)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Current NAV</span>
                <span className="text-white font-medium">{formatCurrency(selectedFund.nav_per_share)}/share</span>
              </div>
              <div className="flex justify-between pt-2 border-t border-slate-700">
                <span className="text-slate-400">Est. Amount to Receive</span>
                <span className="text-green-400 font-semibold">{formatCurrency(estimatedValue)}</span>
              </div>
            </div>
          )}

          {/* Info Note */}
          <div className="flex items-start gap-3 p-3 bg-blue-500/10 border border-blue-500/30 rounded-lg">
            <Info className="w-5 h-5 text-blue-400 flex-shrink-0 mt-0.5" />
            <div className="text-sm text-blue-300">
              <p>
                Withdrawals are processed at the next NAV calculation.
                Actual amount received may vary based on market conditions.
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
                ? 'bg-red-500 hover:bg-red-600 text-white'
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
                <ArrowUpRight className="w-5 h-5" />
                Withdraw {estimatedValue > 0 ? `~${formatCurrency(estimatedValue)}` : ''}
              </>
            )}
          </button>
        </div>
      )}
    </div>
  )
}
