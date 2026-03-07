import { useMutation } from '@tanstack/react-query'
import { runCompare, runSweep } from '../api/analysis'
import type { CompareRequest, SweepRequest } from '../types/api'
import type { CompareResult, SweepResult } from '../types/analysis'

export function useCompare() {
  return useMutation<CompareResult, Error, CompareRequest>({
    mutationFn: runCompare,
  })
}

export function useSweep() {
  return useMutation<SweepResult, Error, SweepRequest>({
    mutationFn: runSweep,
  })
}
