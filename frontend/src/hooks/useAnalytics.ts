import { useQuery } from '@tanstack/react-query'
import {
  fetchAnalyticsSummary,
  fetchCasualtyAnalytics,
  fetchEngagementAnalytics,
  fetchMoraleAnalytics,
  fetchSuppressionAnalytics,
} from '../api/analytics'
import type {
  AnalyticsSummary,
  CasualtyAnalytics,
  EngagementAnalytics,
  MoraleAnalytics,
  SuppressionAnalytics,
} from '../types/analytics'

export function useAnalyticsSummary(runId: string) {
  return useQuery<AnalyticsSummary>({
    queryKey: ['runs', runId, 'analytics', 'summary'],
    queryFn: () => fetchAnalyticsSummary(runId),
    enabled: !!runId,
    staleTime: 30_000,
  })
}

export function useCasualtyAnalytics(runId: string, groupBy?: string, side?: string) {
  return useQuery<CasualtyAnalytics>({
    queryKey: ['runs', runId, 'analytics', 'casualties', groupBy, side],
    queryFn: () => fetchCasualtyAnalytics(runId, groupBy, side),
    enabled: !!runId,
    staleTime: 30_000,
  })
}

export function useSuppressionAnalytics(runId: string) {
  return useQuery<SuppressionAnalytics>({
    queryKey: ['runs', runId, 'analytics', 'suppression'],
    queryFn: () => fetchSuppressionAnalytics(runId),
    enabled: !!runId,
    staleTime: 30_000,
  })
}

export function useMoraleAnalytics(runId: string) {
  return useQuery<MoraleAnalytics>({
    queryKey: ['runs', runId, 'analytics', 'morale'],
    queryFn: () => fetchMoraleAnalytics(runId),
    enabled: !!runId,
    staleTime: 30_000,
  })
}

export function useEngagementAnalytics(runId: string) {
  return useQuery<EngagementAnalytics>({
    queryKey: ['runs', runId, 'analytics', 'engagements'],
    queryFn: () => fetchEngagementAnalytics(runId),
    enabled: !!runId,
    staleTime: 30_000,
  })
}
