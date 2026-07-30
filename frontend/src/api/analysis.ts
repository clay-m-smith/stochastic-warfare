import { apiPost } from './client'
import type { CalibrationOverrides, CompareRequest, SweepRequest } from '../types/api'
import type { CompareResult, DoctrineCompareResult, SweepResult } from '../types/analysis'

export function runCompare(req: CompareRequest): Promise<CompareResult> {
  return apiPost<CompareResult>('/api/analysis/compare', req)
}

export function runSweep(req: SweepRequest): Promise<SweepResult> {
  return apiPost<SweepResult>('/api/analysis/sweep', req)
}

export interface DoctrineCompareRequest {
  scenario: string
  variants: Array<{
    variant_id: string
    calibration_patch?: CalibrationOverrides
    assignments: Array<{
      side: string
      school_id: string
    }>
  }>
  metrics?: string[]
  num_iterations?: number
  base_seed?: number
  max_ticks?: number
}

export function runDoctrineCompare(req: DoctrineCompareRequest): Promise<DoctrineCompareResult> {
  return apiPost<DoctrineCompareResult>('/api/analysis/doctrine-compare', req)
}
