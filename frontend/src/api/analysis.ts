import { apiPost } from './client'
import type { CompareRequest, SweepRequest } from '../types/api'

export function runCompare(req: CompareRequest): Promise<Record<string, unknown>> {
  return apiPost<Record<string, unknown>>('/api/analysis/compare', req)
}

export function runSweep(req: SweepRequest): Promise<Record<string, unknown>> {
  return apiPost<Record<string, unknown>>('/api/analysis/sweep', req)
}
