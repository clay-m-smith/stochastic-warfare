import { useMutation } from '@tanstack/react-query'
import { runCompare, runSweep } from '../api/analysis'
import type { CompareRequest, SweepRequest } from '../types/api'

export function useCompare() {
  return useMutation<Record<string, unknown>, Error, CompareRequest>({
    mutationFn: runCompare,
  })
}

export function useSweep() {
  return useMutation<Record<string, unknown>, Error, SweepRequest>({
    mutationFn: runSweep,
  })
}
