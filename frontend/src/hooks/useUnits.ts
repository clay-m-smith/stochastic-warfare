import { useQuery } from '@tanstack/react-query'
import { fetchUnit, fetchUnits } from '../api/units'
import type { UnitDetail, UnitSummary } from '../types/api'

export function useUnits(filters?: { domain?: string; era?: string; category?: string }) {
  return useQuery<UnitSummary[]>({
    queryKey: ['units', filters],
    queryFn: () => fetchUnits(filters),
    staleTime: 5 * 60 * 1000,
  })
}

export function useUnit(unitType: string) {
  return useQuery<UnitDetail>({
    queryKey: ['units', unitType],
    queryFn: () => fetchUnit(unitType),
    staleTime: 5 * 60 * 1000,
    enabled: !!unitType,
  })
}
