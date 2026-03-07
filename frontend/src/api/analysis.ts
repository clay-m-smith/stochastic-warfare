import { apiPost } from './client'
import type { CompareRequest, SweepRequest } from '../types/api'
import type { CompareResult, SweepResult } from '../types/analysis'

export function runCompare(req: CompareRequest): Promise<CompareResult> {
  return apiPost<CompareResult>('/api/analysis/compare', req)
}

export function runSweep(req: SweepRequest): Promise<SweepResult> {
  return apiPost<SweepResult>('/api/analysis/sweep', req)
}
