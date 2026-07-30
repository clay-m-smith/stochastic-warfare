import { beforeEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ComparePanel } from '../../pages/analysis/ComparePanel'
import { compareResult } from '../fixtures/analysis'
import { renderWithProviders } from '../helpers'
import type { CompareResult } from '../../types/analysis'

vi.mock('../../components/charts/PlotlyChart', () => ({
  PlotlyChart: () => <div data-testid="plotly-chart" />,
}))

const MOCK_SCENARIOS = [
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
    has_space: false,
    has_dew: false,
  },
]

function mockCompare(response: CompareResult) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) => {
    const path = typeof url === 'string' ? url : url.toString()
    if (path.includes('/scenarios')) {
      return new Response(JSON.stringify(MOCK_SCENARIOS), { status: 200 })
    }
    return new Response(JSON.stringify(response), { status: 200 })
  })
}

async function submitComparison() {
  const user = userEvent.setup()
  await screen.findByText('73 Easting')
  await user.selectOptions(screen.getByRole('combobox'), '73_easting')
  await user.click(screen.getByRole('button', { name: 'Run Comparison' }))
}

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('ComparePanel', () => {
  it('binds response labels, metrics, seeds, and raw production evidence to the request', async () => {
    const fetchSpy = mockCompare(compareResult())
    renderWithProviders(<ComparePanel />)

    await submitComparison()

    await screen.findByLabelText('Comparison raw vectors and provenance')
    expect(
      screen.getByText('Config A raw red_destroyed: [1,2,3,4,5,6,7,8,9,10]'),
    ).toBeInTheDocument()
    expect(
      screen.getByText('Config B raw red_destroyed: [2,3,4,5,6,7,8,9,10,11]'),
    ).toBeInTheDocument()
    expect(screen.getByText('Common seeds: 42, 43, 44, 45, 46, 47, 48, 49, 50, 51')).toBeInTheDocument()

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith('/api/analysis/compare', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scenario: '73_easting',
          overrides_a: {},
          overrides_b: {},
          label_a: 'Config A',
          label_b: 'Config B',
          metrics: ['blue_destroyed', 'red_destroyed'],
          num_iterations: 10,
          base_seed: 42,
          max_ticks: 10000,
          alpha: 0.05,
        }),
      })
    })
  })

  it('visibly rejects a self-consistent response with the wrong request label', async () => {
    const response = compareResult()
    response.label_a = 'Stale label'
    mockCompare(response)
    renderWithProviders(<ComparePanel />)

    await submitComparison()

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(
        'Comparison result rejected: comparison response does not match the submitted request',
      )
    })
    expect(
      screen.queryByLabelText('Comparison raw vectors and provenance'),
    ).not.toBeInTheDocument()
  })
})
