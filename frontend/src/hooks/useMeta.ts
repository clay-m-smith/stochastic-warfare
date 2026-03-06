import { useQuery } from '@tanstack/react-query'
import { fetchEras, fetchHealth } from '../api/meta'
import type { EraInfo, HealthResponse } from '../types/api'

export function useHealth() {
  return useQuery<HealthResponse>({
    queryKey: ['health'],
    queryFn: fetchHealth,
    staleTime: 30 * 1000,
    retry: 1,
  })
}

export function useEras() {
  return useQuery<EraInfo[]>({
    queryKey: ['eras'],
    queryFn: fetchEras,
    staleTime: 10 * 60 * 1000,
  })
}
