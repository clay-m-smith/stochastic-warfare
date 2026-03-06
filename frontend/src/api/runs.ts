import { apiGet, apiPost } from './client'
import type { RunSubmitRequest, RunSubmitResponse, RunSummary } from '../types/api'

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
