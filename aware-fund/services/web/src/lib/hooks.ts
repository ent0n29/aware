'use client'

import { useCallback, useEffect, useState } from 'react'
import { api, DataFreshness } from '@/lib/api'

interface DataFreshnessState {
  freshness: DataFreshness | null
  isLoading: boolean
  error: string | null
  refetch: () => Promise<void>
}

export function useDataFreshness(refreshIntervalMs = 30000): DataFreshnessState {
  const [freshness, setFreshness] = useState<DataFreshness | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchFreshness = useCallback(async () => {
    try {
      setError(null)
      const data = await api.getDataFreshness()
      setFreshness(data)
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to load data freshness'
      setError(msg)
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    setIsLoading(true)
    fetchFreshness()

    const interval = setInterval(fetchFreshness, refreshIntervalMs)
    return () => clearInterval(interval)
  }, [fetchFreshness, refreshIntervalMs])

  return {
    freshness,
    isLoading,
    error,
    refetch: fetchFreshness,
  }
}
