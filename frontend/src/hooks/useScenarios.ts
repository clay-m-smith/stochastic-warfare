import { useQuery } from '@tanstack/react-query'
import { fetchScenario, fetchScenarios } from '../api/scenarios'
import type { ScenarioDetail, ScenarioSummary } from '../types/api'

export function useScenarios() {
  return useQuery<ScenarioSummary[]>({
    queryKey: ['scenarios'],
    queryFn: fetchScenarios,
    staleTime: 5 * 60 * 1000,
  })
}

export function useScenario(name: string) {
  return useQuery<ScenarioDetail>({
    queryKey: ['scenarios', name],
    queryFn: () => fetchScenario(name),
    staleTime: 5 * 60 * 1000,
    enabled: !!name,
  })
}
