import { apiGet, apiPost } from './client'
import type { BatchDetail, BatchSubmitRequest, BatchSubmitResponse } from '../types/api'

export function submitBatch(req: BatchSubmitRequest): Promise<BatchSubmitResponse> {
  return apiPost<BatchSubmitResponse>('/api/runs/batch', req)
}

export function fetchBatch(batchId: string): Promise<BatchDetail> {
  return apiGet<BatchDetail>(`/api/runs/batch/${encodeURIComponent(batchId)}`)
}
