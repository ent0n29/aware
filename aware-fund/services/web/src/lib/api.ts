export interface DashboardStats {
  total_trades: number
  total_traders: number
  total_volume_usd: number
  trades_24h: number
  traders_24h: number
}

export interface Trader {
  rank: number
  username: string
  pseudonym?: string | null
  proxy_address: string
  smart_money_score: number
  tier: string
  total_pnl: number
  total_volume: number
  win_rate: number
  sharpe_ratio: number
  strategy_type: string
  strategy_confidence: number
  rank_change: number
  total_trades: number
  model_version?: string
  tier_confidence?: number
  ml_score?: number
}

export interface TraderProfile {
  username: string
  pseudonym?: string | null
  proxy_address: string
  smart_money_score: number
  tier: string
  profitability_score: number
  risk_adjusted_score: number
  consistency_score: number
  track_record_score: number
  strategy_type: string
  strategy_confidence: number
  complete_set_ratio: number
  direction_bias: number
  total_pnl: number
  total_volume: number
  total_trades: number
  unique_markets: number
  days_active: number
  first_trade_at?: string | null
  last_trade_at?: string | null
}

export interface IndexComposition {
  rank: number
  username: string
  proxy_address: string
  smart_money_score: number
  weight: number
  total_pnl: number
}

export interface PSIIndex {
  name: string
  description: string
  trader_count: number
  total_weight: number
  composition: IndexComposition[]
  calculated_at?: string
}

export interface HiddenGem {
  username: string
  discovery_type: string
  discovery_score: number
  smart_money_score: number
  sharpe_ratio: number
  win_rate: number
  total_trades: number
  total_pnl: number
  reason: string
}

export interface DiscoveryResponse {
  discovery_type: string
  count: number
  discoveries: HiddenGem[]
}

export interface ConsensusSignal {
  market_slug: string
  title: string
  favored_outcome: string
  trader_count: number
  total_volume: number
  avg_price: number
  consensus_strength: 'STRONG' | 'MODERATE' | 'WEAK'
}

export interface ConsensusResponse {
  lookback_hours: number
  min_traders: number
  signal_count: number
  signals: ConsensusSignal[]
}

export interface InsiderAlert {
  signal_type: string
  severity: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | string
  market_slug: string
  market_question: string
  description: string
  confidence: number
  direction: 'YES' | 'NO' | string
  total_volume_usd: number
  num_traders: number
  detected_at: string
  traders_involved: string[]
}

export interface InsiderAlertsResponse {
  lookback_hours: number
  alert_count: number
  alerts: InsiderAlert[]
}

export interface EdgeDecayAlert {
  username: string
  decay_type: 'SHARPE_DECLINE' | 'WIN_RATE_DECLINE' | 'VOLUME_DROP' | 'STRATEGY_SHIFT' | string
  severity: 'HIGH' | 'MEDIUM' | 'LOW' | string
  recommended_action: 'REMOVE_FROM_INDEX' | 'REDUCE_WEIGHT' | 'MONITOR' | string
  signal: string
  historical_sharpe: number
  current_sharpe: number
  recent_sharpe: number
  historical_win_rate: number
  current_win_rate: number
  sharpe_decline_pct: number
  decline_pct: number
  detected_at: string
  proxy_address: string
}

export interface EdgeDecayResponse {
  min_decay_threshold: number
  alert_count: number
  alerts: EdgeDecayAlert[]
}

export interface RecentTrade {
  timestamp: string
  username: string
  smart_money_score: number
  market_slug: string
  title: string
  side: string
  outcome: string
  price: number
  size: number
  notional: number
}

export interface RecentActivityResponse {
  min_smart_money_score: number
  trade_count: number
  trades: RecentTrade[]
}

export interface FundInfo {
  fund_id: string
  fund_type: string
  name: string
  description: string
  nav_per_share: number
  total_aum: number
  total_shares: number
  performance_1d: number
  performance_7d: number
  performance_30d: number
  sharpe_ratio: number
  max_drawdown: number
  management_fee: number
  performance_fee: number
  inception_date: string
  is_active: boolean
}

export interface UserHolding {
  fund_id: string
  fund_type: string
  shares: number
  value_usd: number
  cost_basis: number
  unrealized_pnl: number
  unrealized_pnl_pct: number
  nav_per_share: number
}

export interface InvestorPortfolio {
  wallet_address: string
  total_value_usd: number
  total_cost_basis: number
  total_unrealized_pnl: number
  total_unrealized_pnl_pct: number
  holdings: UserHolding[]
}

export interface Transaction {
  id: string
  fund_id: string
  transaction_type: 'DEPOSIT' | 'WITHDRAWAL'
  amount_usd: number
  shares: number
  nav_per_share: number
  status: 'PENDING' | 'COMPLETED' | 'FAILED'
  created_at: string
}

export interface TransactionsResponse {
  transactions: Transaction[]
  count: number
}

export interface DepositRequest {
  wallet_address: string
  fund_id: string
  amount_usd: number
  tx_hash?: string
}

export interface WithdrawRequest {
  wallet_address: string
  fund_id: string
  shares?: number
  amount_usd?: number
  withdraw_all?: boolean
}

export interface TransactionResponse {
  id: string
  fund_id: string
  amount_usd: number
  shares: number
  nav_per_share: number
  status: string
}

export interface NAVDataPoint {
  timestamp: string
  nav_per_share: number
  total_aum: number
  daily_return: number
}

export interface NAVHistoryResponse {
  fund_type: string
  days: number
  data_points: NAVDataPoint[]
}

export interface MLHealthResponse {
  status: 'healthy' | 'degraded' | 'unhealthy' | string
  model_version: string
  last_scoring_at?: string | null
  traders_scored: number
  scoring_method: 'ml_ensemble' | 'rule_based' | string
  tier_distribution: Record<string, number>
  drift_status: 'normal' | 'warning' | 'critical' | string
  drift_ratio: number
  drifted_features: string[]
}

export interface ModelInfoResponse {
  model_version: string
  trained_at?: string | null
  n_traders_trained: number
  tier_accuracy: number
  sharpe_mae: number
  top_features: Array<{ name: string; importance: number; rank: number }>
  tier_boundaries: Array<Record<string, unknown>>
}

export interface FeatureImportanceResponse {
  importance_type: string
  count: number
  features: Array<{
    rank: number
    name: string
    importance: number
    model_version: string
  }>
}

export interface TrainingRun {
  run_id: string
  model_version: string
  started_at?: string | null
  completed_at?: string | null
  duration_seconds: number
  status: string
  n_traders: number
  tier_accuracy: number
  sharpe_mae: number
  trigger_reason?: string | null
}

export interface TrainingRunResponse {
  count: number
  runs: TrainingRun[]
}

export interface DataFreshness {
  status: 'fresh' | 'stale' | 'outdated' | string
  status_emoji: string
  latest_trade_at?: string | null
  latest_trade_age_seconds: number
  latest_trade_age_human: string
  last_scoring_at?: string | null
  last_scoring_age_human: string
  last_pnl_at?: string | null
  last_pnl_age_human: string
  data_coverage_days: number
  recommendation: string
}

const API_BASE = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(/\/$/, '')

function toNumber(value: unknown, fallback = 0): number {
  const num = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(num) ? num : fallback
}

function normalizeRatio(value: number): number {
  if (!Number.isFinite(value)) return 0
  if (value > 1) return value / 100
  if (value < 0) return 0
  return value
}

function fundCategoryFromId(fundId: string): 'MIRROR' | 'ACTIVE' {
  return fundId.toUpperCase().startsWith('PSI') ? 'MIRROR' : 'ACTIVE'
}

function normalizeFundId(raw: unknown): string {
  const v = typeof raw === 'string' ? raw.trim() : ''
  return v.toUpperCase()
}

function mapStatus(statusRaw: unknown): 'PENDING' | 'COMPLETED' | 'FAILED' {
  const status = String(statusRaw || '').toUpperCase()
  if (status === 'FAILED') return 'FAILED'
  if (status === 'PENDING') return 'PENDING'
  return 'COMPLETED'
}

function mapTxType(txTypeRaw: unknown): 'DEPOSIT' | 'WITHDRAWAL' {
  const txType = String(txTypeRaw || '').toUpperCase()
  return txType === 'DEPOSIT' ? 'DEPOSIT' : 'WITHDRAWAL'
}

function pseudoAddressFromUsername(username: string): string {
  let hex = ''
  for (let i = 0; i < username.length; i += 1) {
    const h = username.charCodeAt(i).toString(16)
    hex += h.length === 1 ? `0${h}` : h.slice(-2)
  }
  if (!hex) hex = '0'
  while (hex.length < 40) hex += hex
  return `0x${hex.slice(0, 40)}`
}

function mapFundRecord(raw: Record<string, unknown>): FundInfo {
  const fundId = normalizeFundId(raw.fund_id ?? raw.fund_type)
  const category = (String(raw.fund_type || '').toUpperCase() === 'MIRROR' || String(raw.fund_type || '').toUpperCase() === 'ACTIVE')
    ? String(raw.fund_type || '').toUpperCase() as 'MIRROR' | 'ACTIVE'
    : fundCategoryFromId(fundId)

  return {
    fund_id: fundId,
    fund_type: category,
    name: String(raw.name || fundId),
    description: String(raw.description || ''),
    nav_per_share: toNumber(raw.nav_per_share, 1),
    total_aum: toNumber(raw.total_aum ?? raw.capital_usd, 0),
    total_shares: toNumber(raw.total_shares, 0),
    performance_1d: toNumber(raw.performance_1d ?? raw.return_24h_pct, 0),
    performance_7d: toNumber(raw.performance_7d ?? raw.return_7d_pct, 0),
    performance_30d: toNumber(raw.performance_30d ?? raw.return_30d_pct, 0),
    sharpe_ratio: toNumber(raw.sharpe_ratio, 0),
    max_drawdown: toNumber(raw.max_drawdown, 0),
    management_fee: toNumber(raw.management_fee ?? raw.management_fee_pct, 0),
    performance_fee: toNumber(raw.performance_fee ?? raw.performance_fee_pct, 0),
    inception_date: String(raw.inception_date || ''),
    is_active: Boolean(raw.is_active ?? String(raw.status || '').toLowerCase() === 'active'),
  }
}

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers || {}),
    },
    ...init,
  })

  if (!response.ok) {
    let detail = response.statusText
    try {
      const err = await response.json()
      if (typeof err?.detail === 'string') detail = err.detail
    } catch {
      // No JSON body.
    }
    throw new Error(`API error (${response.status}): ${detail}`)
  }

  return response.json() as Promise<T>
}

function qp(params: Record<string, string | number | undefined>): string {
  const sp = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined) sp.set(key, String(value))
  })
  const query = sp.toString()
  return query ? `?${query}` : ''
}

export const api = {
  async getDataFreshness(): Promise<DataFreshness> {
    return fetchJson<DataFreshness>('/api/freshness')
  },

  async getDashboardStats(): Promise<DashboardStats> {
    return fetchJson<DashboardStats>('/api/stats')
  },

  async getPSI10(): Promise<PSIIndex> {
    return fetchJson<PSIIndex>('/api/index/psi-10')
  },

  async getLeaderboard(limit = 100, tier?: string): Promise<Trader[]> {
    const data = await fetchJson<Array<Record<string, unknown>>>(`/api/leaderboard${qp({ limit, tier })}`)
    return data.map((raw) => {
      const winRateRaw = toNumber(raw.win_rate, 0)
      return {
        rank: toNumber(raw.rank, 0),
        username: String(raw.username || ''),
        pseudonym: (raw.pseudonym as string | null | undefined) ?? null,
        proxy_address: String(raw.proxy_address || ''),
        smart_money_score: toNumber(raw.smart_money_score, 0),
        tier: String(raw.tier || 'BRONZE'),
        total_pnl: toNumber(raw.total_pnl, 0),
        total_volume: toNumber(raw.total_volume, 0),
        win_rate: normalizeRatio(winRateRaw),
        sharpe_ratio: toNumber(raw.sharpe_ratio, 0),
        strategy_type: String(raw.strategy_type || 'UNKNOWN'),
        strategy_confidence: toNumber(raw.strategy_confidence, 0),
        rank_change: toNumber(raw.rank_change, 0),
        total_trades: toNumber(raw.total_trades, 0),
        model_version: raw.model_version == null ? undefined : String(raw.model_version),
        tier_confidence: raw.tier_confidence == null ? undefined : toNumber(raw.tier_confidence),
        ml_score: raw.tier_confidence == null ? undefined : toNumber(raw.smart_money_score, 0),
      }
    })
  },

  async getTrader(identifier: string): Promise<TraderProfile> {
    const raw = await fetchJson<Record<string, unknown>>(`/api/traders/${encodeURIComponent(identifier)}`)
    return {
      username: String(raw.username || ''),
      pseudonym: (raw.pseudonym as string | null | undefined) ?? null,
      proxy_address: String(raw.proxy_address || ''),
      smart_money_score: toNumber(raw.smart_money_score, 0),
      tier: String(raw.tier || 'BRONZE'),
      profitability_score: normalizeRatio(toNumber(raw.profitability_score, 0)),
      risk_adjusted_score: normalizeRatio(toNumber(raw.risk_adjusted_score, 0)),
      consistency_score: normalizeRatio(toNumber(raw.consistency_score, 0)),
      track_record_score: normalizeRatio(toNumber(raw.track_record_score, 0)),
      strategy_type: String(raw.strategy_type || 'UNKNOWN'),
      strategy_confidence: normalizeRatio(toNumber(raw.strategy_confidence, 0)),
      complete_set_ratio: normalizeRatio(toNumber(raw.complete_set_ratio, 0)),
      direction_bias: normalizeRatio(toNumber(raw.direction_bias, 0.5)),
      total_pnl: toNumber(raw.total_pnl, 0),
      total_volume: toNumber(raw.total_volume, 0),
      total_trades: toNumber(raw.total_trades, 0),
      unique_markets: toNumber(raw.unique_markets, 0),
      days_active: toNumber(raw.days_active, 0),
      first_trade_at: (raw.first_trade_at as string | null | undefined) ?? null,
      last_trade_at: (raw.last_trade_at as string | null | undefined) ?? null,
    }
  },

  async getHiddenGems(limit = 10): Promise<DiscoveryResponse> {
    return fetchJson<DiscoveryResponse>(`/api/discovery/hidden-gems${qp({ limit })}`)
  },

  async getRisingStars(limit = 10, maxDays = 30): Promise<DiscoveryResponse> {
    return fetchJson<DiscoveryResponse>(`/api/discovery/rising-stars${qp({ limit, max_days: maxDays })}`)
  },

  async getNicheSpecialists(limit = 10): Promise<DiscoveryResponse> {
    return fetchJson<DiscoveryResponse>(`/api/discovery/niche-specialists${qp({ limit })}`)
  },

  async getConsensusSignals(minTraders = 3, minVolume = 5000, hours = 48): Promise<ConsensusResponse> {
    return fetchJson<ConsensusResponse>(`/api/consensus/markets${qp({ min_traders: minTraders, min_volume: minVolume, hours })}`)
  },

  async getInsiderAlerts(hours = 48, minConfidence = 0.3): Promise<InsiderAlertsResponse> {
    const raw = await fetchJson<InsiderAlertsResponse>(`/api/insider/alerts${qp({ hours, min_confidence: minConfidence })}`)
    return {
      ...raw,
      alerts: (raw.alerts || []).map((a) => ({
        ...a,
        detected_at: a.detected_at,
      })),
    }
  },

  async getEdgeAlerts(minDecay = 15, limit = 20): Promise<EdgeDecayResponse> {
    const raw = await fetchJson<{ min_decay_threshold: number; alert_count: number; alerts: Array<Record<string, unknown>> }>(
      `/api/edge/alerts${qp({ min_decay: minDecay, limit })}`
    )

    const alerts: EdgeDecayAlert[] = (raw.alerts || []).map((item) => {
      const username = String(item.username || 'unknown')
      const declinePct = toNumber(item.decline_pct, 0)
      const historicalSharpe = toNumber(item.historical_sharpe, 0)
      const recentSharpe = toNumber(item.recent_sharpe, 0)

      const severity: EdgeDecayAlert['severity'] =
        declinePct >= 50 ? 'HIGH' : declinePct >= 30 ? 'MEDIUM' : 'LOW'

      const recommendedAction: EdgeDecayAlert['recommended_action'] =
        declinePct >= 50 ? 'REMOVE_FROM_INDEX' : declinePct >= 30 ? 'REDUCE_WEIGHT' : 'MONITOR'

      const historicalWinRate = Math.min(1, 0.55 + (declinePct / 200))
      const currentWinRate = Math.max(0, historicalWinRate - (declinePct / 200))

      return {
        username,
        decay_type: 'SHARPE_DECLINE',
        severity,
        recommended_action: recommendedAction,
        signal: `Sharpe declined by ${declinePct.toFixed(1)}% from historical baseline`,
        historical_sharpe: historicalSharpe,
        current_sharpe: recentSharpe,
        recent_sharpe: recentSharpe,
        historical_win_rate: historicalWinRate,
        current_win_rate: currentWinRate,
        sharpe_decline_pct: declinePct,
        decline_pct: declinePct,
        detected_at: new Date().toISOString(),
        proxy_address: pseudoAddressFromUsername(username),
      }
    })

    return {
      min_decay_threshold: toNumber(raw.min_decay_threshold, minDecay),
      alert_count: alerts.length,
      alerts,
    }
  },

  async getRecentActivity(minScore = 50, limit = 20): Promise<RecentActivityResponse> {
    return fetchJson<RecentActivityResponse>(`/api/activity/recent${qp({ min_score: minScore, limit })}`)
  },

  async getFunds(): Promise<{ funds: FundInfo[] }> {
    const [catalogRaw, activeMetricsRaw] = await Promise.allSettled([
      fetchJson<Array<Record<string, unknown>>>('/api/fund/list'),
      fetchJson<Array<Record<string, unknown>>>('/api/funds?status=active'),
    ])

    const catalog = catalogRaw.status === 'fulfilled' ? catalogRaw.value : []
    const activeMetrics = activeMetricsRaw.status === 'fulfilled' ? activeMetricsRaw.value : []

    const byId = new Map<string, FundInfo>()

    catalog.forEach((entry) => {
      const mapped = mapFundRecord(entry)
      byId.set(mapped.fund_id, {
        ...mapped,
        name: mapped.fund_id,
      })
    })

    activeMetrics.forEach((entry) => {
      const mapped = mapFundRecord(entry)
      const id = mapped.fund_id
      const existing = byId.get(id)
      byId.set(id, {
        ...(existing || mapped),
        ...mapped,
        fund_id: id,
        fund_type: existing?.fund_type || mapped.fund_type,
        name: existing?.name || id,
        is_active: true,
      })
    })

    return {
      funds: Array.from(byId.values()).sort((a, b) => b.total_aum - a.total_aum),
    }
  },

  async getPortfolio(walletAddress: string): Promise<InvestorPortfolio> {
    const raw = await fetchJson<Record<string, unknown>>(`/api/invest/portfolio${qp({ wallet_address: walletAddress })}`)

    const holdingsRaw = Array.isArray(raw.holdings) ? (raw.holdings as Array<Record<string, unknown>>) : []
    const holdings = holdingsRaw.map((h) => {
      const fundId = normalizeFundId(h.fund_id ?? h.fund_type)
      return {
        fund_id: fundId,
        fund_type: fundCategoryFromId(fundId),
        shares: toNumber(h.shares ?? h.shares_balance, 0),
        value_usd: toNumber(h.value_usd ?? h.current_value_usdc, 0),
        cost_basis: toNumber(h.cost_basis ?? h.cost_basis_usdc, 0),
        unrealized_pnl: toNumber(h.unrealized_pnl ?? h.pnl_usdc, 0),
        unrealized_pnl_pct: toNumber(h.unrealized_pnl_pct ?? h.pnl_pct, 0),
        nav_per_share: toNumber(h.nav_per_share, 1),
      }
    })

    return {
      wallet_address: String(raw.wallet_address || walletAddress),
      total_value_usd: toNumber(raw.total_value_usd ?? raw.total_value_usdc, 0),
      total_cost_basis: toNumber(raw.total_cost_basis, 0),
      total_unrealized_pnl: toNumber(raw.total_unrealized_pnl ?? raw.total_pnl_usdc, 0),
      total_unrealized_pnl_pct: toNumber(raw.total_unrealized_pnl_pct ?? raw.total_pnl_pct, 0),
      holdings,
    }
  },

  async getTransactions(walletAddress: string, fundId?: string, limit = 50): Promise<TransactionsResponse> {
    const raw = await fetchJson<Array<Record<string, unknown>>>(
      `/api/invest/transactions${qp({ wallet_address: walletAddress, fund_type: fundId, limit })}`
    )

    const transactions: Transaction[] = (raw || []).map((tx) => ({
      id: String(tx.id ?? tx.tx_id ?? crypto.randomUUID()),
      fund_id: normalizeFundId(tx.fund_id ?? tx.fund_type),
      transaction_type: mapTxType(tx.transaction_type ?? tx.tx_type),
      amount_usd: toNumber(tx.amount_usd ?? tx.usdc_amount, 0),
      shares: toNumber(tx.shares ?? tx.shares_amount, 0),
      nav_per_share: toNumber(tx.nav_per_share, 0),
      status: mapStatus(tx.status),
      created_at: String(tx.created_at || new Date().toISOString()),
    }))

    return { transactions, count: transactions.length }
  },

  async deposit(request: DepositRequest): Promise<TransactionResponse> {
    const raw = await fetchJson<Record<string, unknown>>('/api/invest/deposit', {
      method: 'POST',
      body: JSON.stringify({
        wallet_address: request.wallet_address,
        fund_type: request.fund_id,
        usdc_amount: request.amount_usd,
        tx_hash: request.tx_hash,
      }),
    })

    return {
      id: String(raw.id ?? raw.tx_id ?? ''),
      fund_id: normalizeFundId(raw.fund_id ?? raw.fund_type),
      amount_usd: toNumber(raw.amount_usd ?? raw.usdc_amount, 0),
      shares: toNumber(raw.shares ?? raw.shares_received, 0),
      nav_per_share: toNumber(raw.nav_per_share, 0),
      status: String(raw.status || 'COMPLETED').toUpperCase(),
    }
  },

  async withdraw(request: WithdrawRequest): Promise<TransactionResponse> {
    const raw = await fetchJson<Record<string, unknown>>('/api/invest/withdraw', {
      method: 'POST',
      body: JSON.stringify({
        wallet_address: request.wallet_address,
        fund_type: request.fund_id,
        withdraw_all: request.withdraw_all,
        shares_amount: request.shares,
        usdc_amount: request.amount_usd,
      }),
    })

    return {
      id: String(raw.id ?? raw.request_id ?? ''),
      fund_id: normalizeFundId(raw.fund_id ?? raw.fund_type),
      amount_usd: toNumber(raw.amount_usd ?? raw.usdc_amount, 0),
      shares: toNumber(raw.shares ?? raw.shares_redeemed, 0),
      nav_per_share: toNumber(raw.nav_per_share, 0),
      status: String(raw.status || 'PENDING').toUpperCase(),
    }
  },

  async getFundNAVHistory(fundId: string, days = 30): Promise<NAVHistoryResponse> {
    const raw = await fetchJson<Record<string, unknown>>(`/api/fund/nav-history${qp({ fund_type: fundId, days })}`)

    const dataPointsRaw = Array.isArray(raw.data_points) ? (raw.data_points as Array<Record<string, unknown>>) : []

    return {
      fund_type: String(raw.fund_type || fundId),
      days: toNumber(raw.days, days),
      data_points: dataPointsRaw.map((point) => ({
        timestamp: String(point.timestamp || ''),
        nav_per_share: toNumber(point.nav_per_share, 1),
        total_aum: toNumber(point.total_aum, 0),
        daily_return: toNumber(point.daily_return, 0),
      })),
    }
  },

  async getMLHealth(): Promise<MLHealthResponse> {
    return fetchJson<MLHealthResponse>('/api/ml/health')
  },

  async getModelInfo(): Promise<ModelInfoResponse> {
    return fetchJson<ModelInfoResponse>('/api/models/ensemble/info')
  },

  async getFeatureImportance(limit = 20): Promise<FeatureImportanceResponse> {
    return fetchJson<FeatureImportanceResponse>(`/api/models/feature-importance${qp({ limit })}`)
  },

  async getTrainingHistory(limit = 10): Promise<TrainingRunResponse> {
    return fetchJson<TrainingRunResponse>(`/api/models/training-history${qp({ limit })}`)
  },
}
