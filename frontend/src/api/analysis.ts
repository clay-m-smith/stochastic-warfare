import { apiPost } from './client'
import type {
  CompareRequest,
  DoctrineCompareRequest,
  SweepRequest,
} from '../types/api'
import type { CompareResult, DoctrineCompareResult, SweepResult } from '../types/analysis'

export function runCompare(req: CompareRequest): Promise<CompareResult> {
  return apiPost<CompareResult>('/api/analysis/compare', req)
}

export function runSweep(req: SweepRequest): Promise<SweepResult> {
  return apiPost<SweepResult>('/api/analysis/sweep', req)
}

export function runDoctrineCompare(req: DoctrineCompareRequest): Promise<DoctrineCompareResult> {
  return apiPost<DoctrineCompareResult>('/api/analysis/doctrine-compare', req)
}
