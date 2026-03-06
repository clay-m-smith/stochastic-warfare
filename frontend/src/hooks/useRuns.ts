import { useMutation, useQuery } from '@tanstack/react-query'
import { fetchRuns, submitRun } from '../api/runs'
import type { RunSubmitRequest, RunSubmitResponse, RunSummary } from '../types/api'

export function useRuns(params?: {
  limit?: number
  offset?: number
  scenario?: string
  status?: string
}) {
  return useQuery<RunSummary[]>({
    queryKey: ['runs', params],
    queryFn: () => fetchRuns(params),
    staleTime: 30 * 1000,
  })
}

export function useSubmitRun() {
  return useMutation<RunSubmitResponse, Error, RunSubmitRequest>({
    mutationFn: submitRun,
  })
}
