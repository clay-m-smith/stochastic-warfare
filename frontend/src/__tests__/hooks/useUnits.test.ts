import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useUnits, useUnit } from '../../hooks/useUnits'
import type { UnitSummary } from '../../types/api'
import { createElement } from 'react'

const MOCK_UNITS: UnitSummary[] = [
  {
    unit_type: 'm1a1_abrams',
    display_name: 'M1A1 Abrams',
    domain: 'land',
    category: 'armor',
    era: 'modern',
    max_speed: 20,
    crew_size: 4,
  },
]

function createWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) =>
    createElement(QueryClientProvider, { client: qc }, children)
}

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('useUnits', () => {
  it('fetches all units', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(MOCK_UNITS), { status: 200 }),
    )
    const { result } = renderHook(() => useUnits(), { wrapper: createWrapper() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual(MOCK_UNITS)
  })

  it('includes query params from filters', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify([]), { status: 200 }),
    )
    const { result } = renderHook(() => useUnits({ domain: 'land', era: 'modern' }), {
      wrapper: createWrapper(),
    })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('domain=land'))
  })
})

describe('useUnit', () => {
  it('fetches single unit detail', async () => {
    const detail = { unit_type: 'm1a1_abrams', definition: { name: 'M1A1 Abrams' } }
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(detail), { status: 200 }),
    )
    const { result } = renderHook(() => useUnit('m1a1_abrams'), { wrapper: createWrapper() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual(detail)
  })
})
