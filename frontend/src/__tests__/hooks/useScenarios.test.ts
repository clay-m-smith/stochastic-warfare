import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useScenarios, useScenario } from '../../hooks/useScenarios'
import type { ScenarioSummary } from '../../types/api'
import { createElement } from 'react'

const MOCK_SCENARIOS: ScenarioSummary[] = [
  {
    name: '73_easting',
    display_name: '73 Easting',
    era: 'modern',
    duration_hours: 4,
    sides: ['blue', 'red'],
    terrain_type: 'desert',
    has_ew: false,
    has_cbrn: false,
    has_escalation: false,
    has_schools: false,
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

describe('useScenarios', () => {
  it('fetches scenarios list', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(MOCK_SCENARIOS), { status: 200 }),
    )
    const { result } = renderHook(() => useScenarios(), { wrapper: createWrapper() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual(MOCK_SCENARIOS)
  })
})

describe('useScenario', () => {
  it('fetches single scenario', async () => {
    const detail = { name: '73_easting', config: {}, force_summary: {} }
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(detail), { status: 200 }),
    )
    const { result } = renderHook(() => useScenario('73_easting'), { wrapper: createWrapper() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual(detail)
  })

  it('does not fetch when name is empty', () => {
    vi.spyOn(globalThis, 'fetch')
    renderHook(() => useScenario(''), { wrapper: createWrapper() })
    expect(fetch).not.toHaveBeenCalled()
  })
})
