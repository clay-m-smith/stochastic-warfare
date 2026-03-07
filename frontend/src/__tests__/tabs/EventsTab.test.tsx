import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { EventsTab } from '../../pages/runs/tabs/EventsTab'
import { renderWithProviders } from '../helpers'

beforeEach(() => {
  vi.restoreAllMocks()
  // Virtualizer needs layout dimensions that jsdom doesn't provide
  Object.defineProperty(HTMLElement.prototype, 'offsetHeight', { configurable: true, value: 600 })
  Object.defineProperty(HTMLElement.prototype, 'scrollHeight', { configurable: true, value: 600 })
})

const EVENTS_RESPONSE = {
  events: Array.from({ length: 10 }, (_, i) => ({
    tick: i * 5,
    event_type: 'EngagementEvent',
    source: `unit_${i}`,
    data: { hit: true },
  })),
  total: 10,
  offset: 0,
  limit: 100,
}

describe('EventsTab', () => {
  it('renders virtualized event rows', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(EVENTS_RESPONSE), { status: 200 }),
    )
    renderWithProviders(<EventsTab runId="r1" />)
    await waitFor(() => {
      expect(screen.getByText('10 total events')).toBeInTheDocument()
    })
    const rows = screen.getAllByTestId('event-row')
    expect(rows.length).toBeGreaterThan(0)
    expect(rows.length).toBeLessThanOrEqual(10)
  })

  it('shows pagination when total exceeds page size', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ ...EVENTS_RESPONSE, total: 200 }), { status: 200 }),
    )
    renderWithProviders(<EventsTab runId="r1" />)
    await waitFor(() => {
      expect(screen.getByText('Previous')).toBeInTheDocument()
    })
    expect(screen.getByText('Next')).toBeInTheDocument()
  })
})
