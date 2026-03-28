import { apiGet } from './client'
import type {
  AnalyticsSummary,
  CasualtyAnalytics,
  EngagementAnalytics,
  MoraleAnalytics,
  SuppressionAnalytics,
} from '../types/analytics'

export function fetchCasualtyAnalytics(
  runId: string,
  groupBy?: string,
  side?: string,
): Promise<CasualtyAnalytics> {
  const sp = new URLSearchParams()
  if (groupBy) sp.set('group_by', groupBy)
  if (side) sp.set('side', side)
  const qs = sp.toString()
  return apiGet<CasualtyAnalytics>(
    `/api/runs/${encodeURIComponent(runId)}/analytics/casualties${qs ? `?${qs}` : ''}`,
  )
}

export function fetchSuppressionAnalytics(runId: string): Promise<SuppressionAnalytics> {
  return apiGet<SuppressionAnalytics>(
    `/api/runs/${encodeURIComponent(runId)}/analytics/suppression`,
  )
}

export function fetchMoraleAnalytics(runId: string): Promise<MoraleAnalytics> {
  return apiGet<MoraleAnalytics>(
    `/api/runs/${encodeURIComponent(runId)}/analytics/morale`,
  )
}

export function fetchEngagementAnalytics(runId: string): Promise<EngagementAnalytics> {
  return apiGet<EngagementAnalytics>(
    `/api/runs/${encodeURIComponent(runId)}/analytics/engagements`,
  )
}

export function fetchAnalyticsSummary(runId: string): Promise<AnalyticsSummary> {
  return apiGet<AnalyticsSummary>(
    `/api/runs/${encodeURIComponent(runId)}/analytics/summary`,
  )
}
