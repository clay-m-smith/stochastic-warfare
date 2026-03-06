import { useMutation, useQuery } from '@tanstack/react-query'
import { fetchBatch, submitBatch } from '../api/batch'
import type { BatchDetail, BatchSubmitRequest, BatchSubmitResponse } from '../types/api'

export function useSubmitBatch() {
  return useMutation<BatchSubmitResponse, Error, BatchSubmitRequest>({
    mutationFn: submitBatch,
  })
}

export function useBatch(batchId: string | null) {
  return useQuery<BatchDetail>({
    queryKey: ['batch', batchId],
    queryFn: () => fetchBatch(batchId!),
    enabled: !!batchId,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      if (status === 'pending' || status === 'running') return 3000
      return false
    },
  })
}
