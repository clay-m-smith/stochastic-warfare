import { useQuery } from '@tanstack/react-query'
import { fetchCommanders, fetchEras, fetchHealth, fetchSchools } from '../api/meta'
import type { CommanderInfo, EraInfo, HealthResponse, SchoolInfo } from '../types/api'

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

export function useSchools() {
  return useQuery<SchoolInfo[]>({
    queryKey: ['schools'],
    queryFn: fetchSchools,
    staleTime: 10 * 60 * 1000,
  })
}

export function useCommanders() {
  return useQuery<CommanderInfo[]>({
    queryKey: ['commanders'],
    queryFn: fetchCommanders,
    staleTime: 10 * 60 * 1000,
  })
}
