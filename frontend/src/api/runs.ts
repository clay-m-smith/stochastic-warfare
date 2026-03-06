import { apiGet, apiPost, apiDelete } from './client'
import type {
  EventsResponse,
  NarrativeResponse,
  RunDetail,
  RunSubmitRequest,
  RunSubmitResponse,
  RunSummary,
} from '../types/api'

export function submitRun(req: RunSubmitRequest): Promise<RunSubmitResponse> {
  return apiPost<RunSubmitResponse>('/api/runs', req)
}

export function fetchRuns(params?: {
  limit?: number
  offset?: number
  scenario?: string
  status?: string
}): Promise<RunSummary[]> {
  const sp = new URLSearchParams()
  if (params?.limit) sp.set('limit', String(params.limit))
  if (params?.offset) sp.set('offset', String(params.offset))
  if (params?.scenario) sp.set('scenario', params.scenario)
  if (params?.status) sp.set('status', params.status)
  const qs = sp.toString()
  return apiGet<RunSummary[]>(`/api/runs${qs ? `?${qs}` : ''}`)
}

export function fetchRun(runId: string): Promise<RunDetail> {
  return apiGet<RunDetail>(`/api/runs/${encodeURIComponent(runId)}`)
}

export function deleteRun(runId: string): Promise<void> {
  return apiDelete(`/api/runs/${encodeURIComponent(runId)}`)
}

export function fetchRunEvents(
  runId: string,
  params?: { offset?: number; limit?: number; event_type?: string },
): Promise<EventsResponse> {
  const sp = new URLSearchParams()
  if (params?.offset != null) sp.set('offset', String(params.offset))
  if (params?.limit != null) sp.set('limit', String(params.limit))
  if (params?.event_type) sp.set('event_type', params.event_type)
  const qs = sp.toString()
  return apiGet<EventsResponse>(
    `/api/runs/${encodeURIComponent(runId)}/events${qs ? `?${qs}` : ''}`,
  )
}

export function fetchRunNarrative(
  runId: string,
  params?: { side?: string; style?: string },
): Promise<NarrativeResponse> {
  const sp = new URLSearchParams()
  if (params?.side) sp.set('side', params.side)
  if (params?.style) sp.set('style', params.style)
  const qs = sp.toString()
  return apiGet<NarrativeResponse>(
    `/api/runs/${encodeURIComponent(runId)}/narrative${qs ? `?${qs}` : ''}`,
  )
}
