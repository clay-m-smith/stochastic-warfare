import { useMutation } from '@tanstack/react-query'
import { runCompare, runDoctrineCompare, runSweep } from '../api/analysis'
import type { DoctrineCompareRequest } from '../api/analysis'
import type { CompareRequest, SweepRequest } from '../types/api'
import type { CompareResult, DoctrineCompareResult, SweepResult } from '../types/analysis'

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

export function useDoctrineCompare() {
  return useMutation<DoctrineCompareResult, Error, DoctrineCompareRequest>({
    mutationFn: runDoctrineCompare,
  })
}
