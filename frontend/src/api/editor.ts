import { apiPost } from './client'
import type { RunSubmitResponse } from '../types/api'
import type { RunFromConfigRequest, ValidateConfigResponse } from '../types/editor'

export function submitRunFromConfig(req: RunFromConfigRequest): Promise<RunSubmitResponse> {
  return apiPost<RunSubmitResponse>('/api/runs/from-config', req)
}

export function validateConfig(config: Record<string, unknown>): Promise<ValidateConfigResponse> {
  return apiPost<ValidateConfigResponse>('/api/scenarios/validate', { config })
}
