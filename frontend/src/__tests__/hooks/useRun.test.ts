import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createElement } from 'react'
import { useRun, useDeleteRun } from '../../hooks/useRuns'

function createWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) =>
    createElement(QueryClientProvider, { client: qc }, children)
}

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('useRun', () => {
  it('fetches run detail', async () => {
    const detail = { run_id: 'r1', scenario_name: 'test', status: 'completed', seed: 42 }
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(detail), { status: 200 }),
    )
    const { result } = renderHook(() => useRun('r1'), { wrapper: createWrapper() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual(detail)
  })

  it('does not fetch when runId is empty', () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{}', { status: 200 }))
    renderHook(() => useRun(''), { wrapper: createWrapper() })
    expect(fetch).not.toHaveBeenCalled()
  })
})

describe('useDeleteRun', () => {
  it('calls delete endpoint', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(null, { status: 204 }))
    const { result } = renderHook(() => useDeleteRun(), { wrapper: createWrapper() })
    result.current.mutate('r1')
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(fetch).toHaveBeenCalledWith('/api/runs/r1', { method: 'DELETE' })
  })
})
