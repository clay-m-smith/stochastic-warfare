import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  deleteRun,
  fetchRun,
  fetchRunEvents,
  fetchRunNarrative,
  fetchRuns,
  submitRun,
} from '../api/runs'
import type {
  EventsResponse,
  NarrativeResponse,
  RunDetail,
  RunSubmitRequest,
  RunSubmitResponse,
  RunSummary,
} from '../types/api'

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

export function useRun(runId: string) {
  return useQuery<RunDetail>({
    queryKey: ['runs', runId],
    queryFn: () => fetchRun(runId),
    enabled: !!runId,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      if (status === 'pending' || status === 'running') return 5000
      return false
    },
  })
}

export function useDeleteRun() {
  const queryClient = useQueryClient()
  return useMutation<void, Error, string>({
    mutationFn: deleteRun,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['runs'] })
    },
  })
}

export function useRunEvents(
  runId: string,
  params?: { offset?: number; limit?: number; event_type?: string },
) {
  return useQuery<EventsResponse>({
    queryKey: ['runs', runId, 'events', params],
    queryFn: () => fetchRunEvents(runId, params),
    enabled: !!runId,
  })
}

export function useRunNarrative(
  runId: string,
  params?: { side?: string; style?: string },
  options?: { enabled?: boolean },
) {
  return useQuery<NarrativeResponse>({
    queryKey: ['runs', runId, 'narrative', params],
    queryFn: () => fetchRunNarrative(runId, params),
    enabled: options?.enabled !== false && !!runId,
  })
}
