import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { renderWithProviders } from '../helpers'
import { ChartsTab } from '../../pages/runs/tabs/ChartsTab'
import type { RunResult } from '../../types/api'

vi.mock('../../components/charts/PlotlyChart', () => ({
  PlotlyChart: () => <div data-testid="plotly-chart" />,
}))

const MOCK_RESULT: RunResult = {
  scenario: 'test',
  seed: 42,
  ticks_executed: 100,
  duration_s: 10,
  victory: { status: 'decisive', winner: 'blue' },
  sides: {
    blue: { total: 10, active: 8, destroyed: 2 },
    red: { total: 8, active: 3, destroyed: 5 },
  },
}

const MOCK_EVENTS = {
  events: [
    { tick: 1, event_type: 'EngagementEvent', source: 't1', data: { hit: true } },
    { tick: 5, event_type: 'UnitDestroyedEvent', source: 'b1', data: { side: 'red' } },
    { tick: 10, event_type: 'MoraleStateChangeEvent', source: 'u1', data: { unit_id: 'u1', new_state: 'shaken', old_state: 'steady' } },
  ],
  total: 3,
  offset: 0,
  limit: 10000,
}

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('ChartsTab', () => {
  it('renders charts when events are available', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(MOCK_EVENTS), { status: 200 }),
    )
    renderWithProviders(<ChartsTab runId="r1" result={MOCK_RESULT} />)
    await waitFor(() => {
      expect(screen.getAllByTestId('plotly-chart').length).toBeGreaterThan(0)
    })
  })

  it('shows empty state when no events', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ events: [], total: 0, offset: 0, limit: 10000 }), { status: 200 }),
    )
    renderWithProviders(<ChartsTab runId="r1" result={MOCK_RESULT} />)
    await waitFor(() => {
      expect(screen.getByText('No events recorded for this run.')).toBeInTheDocument()
    })
  })

  it('shows loading spinner while fetching', () => {
    vi.spyOn(globalThis, 'fetch').mockReturnValue(new Promise(() => {}))
    renderWithProviders(<ChartsTab runId="r1" result={MOCK_RESULT} />)
    expect(document.querySelector('.animate-spin')).toBeInTheDocument()
  })
})
