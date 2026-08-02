import { createElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useRunFrames } from '../../hooks/useMap'
import type { PrivilegedFramesData, SideFowFramesData } from '../../types/map'

const PRIVILEGED_FRAMES: PrivilegedFramesData = {
  scope: 'PRIVILEGED_ENGINE',
  viewer_side: null,
  frames: [],
  total_frames: 0,
}

const SIDE_FOW_FRAMES: SideFowFramesData = {
  scope: 'SIDE_FOW',
  viewer_side: 'blue',
  frames: [],
  total_frames: 0,
}

function createWrapper(queryClient: QueryClient) {
  return ({ children }: { children: React.ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children)
}

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('useRunFrames', () => {
  it('isolates privileged and SIDE_FOW responses in separate query keys', async () => {
    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(
        new Response(JSON.stringify(PRIVILEGED_FRAMES), { status: 200 }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify(SIDE_FOW_FRAMES), { status: 200 }),
      )
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    const wrapper = createWrapper(queryClient)

    const privileged = renderHook(() => useRunFrames('r1'), { wrapper })
    await waitFor(() => expect(privileged.result.current.isSuccess).toBe(true))

    const side = renderHook(
      () => useRunFrames('r1', { scope: 'SIDE_FOW', side: 'blue' }),
      { wrapper },
    )
    await waitFor(() => expect(side.result.current.isSuccess).toBe(true))

    expect(privileged.result.current.data?.scope).toBe('PRIVILEGED_ENGINE')
    expect(side.result.current.data?.scope).toBe('SIDE_FOW')
    expect(fetch).toHaveBeenNthCalledWith(1, '/api/runs/r1/frames')
    expect(fetch).toHaveBeenNthCalledWith(
      2,
      '/api/runs/r1/frames?scope=SIDE_FOW&side=blue',
    )
  })
})
