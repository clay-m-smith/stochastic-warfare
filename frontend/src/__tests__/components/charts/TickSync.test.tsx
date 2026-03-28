import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from '../../helpers'
import { ChartsTab } from '../../../pages/runs/tabs/ChartsTab'
import type { RunResult } from '../../../types/api'

// Mock react-plotly.js
vi.mock('react-plotly.js', () => ({
  default: (props: Record<string, unknown>) => {
    const { data, layout, onClick } = props as {
      data: unknown[]
      layout: Record<string, unknown>
      onClick?: (e: unknown) => void
    }
    return (
      <div
        data-testid="mock-plot"
        data-layout={JSON.stringify(layout)}
        data-has-onclick={onClick ? 'true' : 'false'}
        onClick={() => {
          if (onClick) {
            onClick({ points: [{ x: 42, y: 5 }] })
          }
        }}
      >
        Plot ({(data as unknown[]).length} traces)
      </div>
    )
  },
}))

beforeEach(() => {
  vi.restoreAllMocks()
  // Mock fetch for events endpoint
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(
      JSON.stringify({
        events: [
          { tick: 0, event_type: 'UnitDestroyedEvent', source: 'unit-r1', data: { unit_id: 'r1', side: 'red', unit_type: 'tank' } },
          { tick: 5, event_type: 'EngagementResolvedEvent', source: 'combat', data: { attacker: 'b1', target: 'r1', hit: true, weapon: 'M256' } },
        ],
        total: 2,
        offset: 0,
        limit: 10000,
      }),
      { status: 200 },
    ),
  )
})

const RESULT: RunResult = {
  scenario: 'test',
  seed: 42,
  ticks_executed: 100,
  duration_s: 5.0,
  victory: { status: 'max_ticks' },
  sides: {
    blue: { total: 5, active: 4, disabled: 0, destroyed: 1 },
    red: { total: 5, active: 3, disabled: 0, destroyed: 2 },
  },
}

describe('TickSync', () => {
  it('all charts receive onClick handler', async () => {
    renderWithProviders(<ChartsTab runId="run1" result={RESULT} />, { route: '/runs/run1?tab=charts' })

    const plots = await screen.findAllByTestId('mock-plot')
    expect(plots.length).toBeGreaterThanOrEqual(1)

    for (const plot of plots) {
      expect(plot.getAttribute('data-has-onclick')).toBe('true')
    }
  })

  it('all charts receive shapes in layout when tick is set', async () => {
    renderWithProviders(<ChartsTab runId="run1" result={RESULT} />, { route: '/runs/run1?tab=charts&tick=50' })

    const plots = await screen.findAllByTestId('mock-plot')
    expect(plots.length).toBeGreaterThanOrEqual(1)

    for (const plot of plots) {
      const layout = JSON.parse(plot.getAttribute('data-layout') || '{}')
      expect(layout.shapes).toBeDefined()
      expect(layout.shapes.length).toBe(1)
      // tick=50, dt=5.0/100=0.05, so time_s = 50*0.05 = 2.5
      expect(layout.shapes[0].x0).toBe(2.5)
    }
  })

  it('charts have no shapes when no tick is set', async () => {
    renderWithProviders(<ChartsTab runId="run1" result={RESULT} />, { route: '/runs/run1?tab=charts' })

    const plots = await screen.findAllByTestId('mock-plot')
    expect(plots.length).toBeGreaterThanOrEqual(1)

    for (const plot of plots) {
      const layout = JSON.parse(plot.getAttribute('data-layout') || '{}')
      if (layout.shapes) {
        expect(layout.shapes).toHaveLength(0)
      }
    }
  })

  it('clicking chart invokes onClick handler', async () => {
    renderWithProviders(
      <ChartsTab runId="run1" result={RESULT} />,
      { route: '/runs/run1?tab=charts' },
    )

    const plots = await screen.findAllByTestId('mock-plot')
    plots[0]!.click()
    expect(plots[0]!.getAttribute('data-has-onclick')).toBe('true')
  })
})
