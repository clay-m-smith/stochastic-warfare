import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { renderWithProviders } from '../helpers'
import { EventsTab } from '../../pages/runs/tabs/EventsTab'

const MOCK_EVENTS = {
  events: [
    { tick: 1, event_type: 'EngagementEvent', source: 'tank1', data: { hit: true } },
    { tick: 2, event_type: 'MoraleStateChangeEvent', source: 'inf1', data: { new_state: 'shaken' } },
    { tick: 3, event_type: 'UnitDestroyedEvent', source: 'bmp1', data: { side: 'red' } },
  ],
  total: 3,
  offset: 0,
  limit: 100,
}

beforeEach(() => {
  vi.restoreAllMocks()
  // Virtualizer needs layout dimensions that jsdom doesn't provide
  Object.defineProperty(HTMLElement.prototype, 'offsetHeight', { configurable: true, value: 600 })
  Object.defineProperty(HTMLElement.prototype, 'scrollHeight', { configurable: true, value: 600 })
})

describe('EventsTab', () => {
  it('renders virtualized event rows', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(MOCK_EVENTS), { status: 200 }),
    )
    renderWithProviders(<EventsTab runId="r1" />)
    await waitFor(() => {
      const rows = screen.getAllByTestId('event-row')
      expect(rows.length).toBeGreaterThan(0)
    })
  })

  it('shows total event count', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(MOCK_EVENTS), { status: 200 }),
    )
    renderWithProviders(<EventsTab runId="r1" />)
    await waitFor(() => {
      expect(screen.getByText('3 total events')).toBeInTheDocument()
    })
  })

  it('shows empty state when no events', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ events: [], total: 0, offset: 0, limit: 100 }), { status: 200 }),
    )
    renderWithProviders(<EventsTab runId="r1" />)
    await waitFor(() => {
      expect(screen.getByText('No events found.')).toBeInTheDocument()
    })
  })

  it('has filter input', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(MOCK_EVENTS), { status: 200 }),
    )
    renderWithProviders(<EventsTab runId="r1" />)
    await waitFor(() => {
      expect(screen.getByPlaceholderText('Filter by event type...')).toBeInTheDocument()
    })
  })
})
