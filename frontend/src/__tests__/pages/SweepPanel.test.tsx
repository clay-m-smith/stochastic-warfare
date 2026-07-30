import { beforeEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SweepPanel } from '../../pages/analysis/SweepPanel'
import { renderWithProviders } from '../helpers'
import { evidenceBatch } from '../fixtures/analysis'
import type { SweepResult } from '../../types/analysis'

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

function sweepResult(): SweepResult {
  const seeds = [42, 43, 44]
  const blueValues = [0, 0, 0]
  const firstValues = [1, 2, 3]
  const secondValues = [2, 4, 6]
  const secondBatch = evidenceBatch(
    'point-1',
    [
      ['blue_destroyed', blueValues],
      ['red_destroyed', secondValues],
    ],
    seeds,
    10000,
    { unitsPerSide: 10 },
  )
  secondBatch.config_fingerprint = '9'.repeat(64)
  for (const run of secondBatch.runs) {
    run.config_fingerprint = secondBatch.config_fingerprint
  }
  return {
    parameter_name: 'hit_probability_modifier',
    ordered_metrics: ['blue_destroyed', 'red_destroyed'],
    base_seed: 42,
    seeds,
    max_ticks: 10000,
    source_fingerprint: 'a'.repeat(64),
    data_root: '/data',
    points: [
      {
        parameter_value: 1,
        metric_results: [
          {
            metric: 'blue_destroyed',
            mean: 0,
            std: 0,
            min: 0,
            max: 0,
            values: blueValues,
          },
          {
            metric: 'red_destroyed',
            mean: 2,
            std: 1,
            min: 1,
            max: 3,
            values: firstValues,
          },
        ],
        batch: evidenceBatch(
          'point-0',
          [
            ['blue_destroyed', blueValues],
            ['red_destroyed', firstValues],
          ],
          seeds,
          10000,
          { unitsPerSide: 10 },
        ),
      },
      {
        parameter_value: 2,
        metric_results: [
          {
            metric: 'blue_destroyed',
            mean: 0,
            std: 0,
            min: 0,
            max: 0,
            values: blueValues,
          },
          {
            metric: 'red_destroyed',
            mean: 4,
            std: 2,
            min: 2,
            max: 6,
            values: secondValues,
          },
        ],
        batch: secondBatch,
      },
    ],
  }
}

function mockSweep(response?: unknown) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) => {
    const path = typeof url === 'string' ? url : url.toString()
    if (path.includes('/scenarios')) {
      return new Response(JSON.stringify(MOCK_SCENARIOS), { status: 200 })
    }
    return new Response(JSON.stringify(response), { status: 200 })
  })
}

async function fillSweepForm(values: string) {
  const user = userEvent.setup()
  await screen.findByText('73 Easting')
  await user.selectOptions(screen.getByRole('combobox'), '73_easting')
  await user.type(
    screen.getByPlaceholderText('e.g. hit_probability_modifier'),
    'hit_probability_modifier',
  )
  await user.type(
    screen.getByPlaceholderText('e.g. 100, 500, 1000, 2000'),
    values,
  )
  return user
}

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('SweepPanel', () => {
  it.each(['1,,2', '1,not-a-number,2', '1,Infinity'])(
    'rejects every malformed CSV token without sending %s',
    async (values) => {
      const fetchSpy = mockSweep()
      renderWithProviders(<SweepPanel />)
      const user = await fillSweepForm(values)

      await user.click(screen.getByRole('button', { name: 'Run Sweep' }))

      expect(
        screen.getByRole('alert'),
      ).toHaveTextContent('Every sweep value must be a non-empty finite number.')
      expect(
        fetchSpy.mock.calls.some(([url]) => String(url).includes('/analysis/sweep')),
      ).toBe(false)
    },
  )

  it('renders complete raw vectors and revision fingerprints from valid evidence', async () => {
    const response = sweepResult()
    const fetchSpy = mockSweep(response)
    renderWithProviders(<SweepPanel />)
    const user = await fillSweepForm('1,2')
    const numberInputs = screen.getAllByRole('spinbutton')
    await user.clear(numberInputs[0]!)
    await user.type(numberInputs[0]!, '3')

    await user.click(screen.getByRole('button', { name: 'Run Sweep' }))

    await screen.findByLabelText('Sweep raw vectors and provenance')
    expect(screen.getByText('red_destroyed raw: [1,2,3]')).toBeInTheDocument()
    expect(screen.getByText('red_destroyed raw: [2,4,6]')).toBeInTheDocument()
    expect(
      screen.getByText('a'.repeat(64)),
    ).toBeInTheDocument()
    expect(
      screen.getByText(`Config SHA-256: ${'6'.repeat(64)}`),
    ).toBeInTheDocument()
    expect(
      screen.getByText(`Config SHA-256: ${'9'.repeat(64)}`),
    ).toBeInTheDocument()
    expect(
      screen.getAllByText(`Worktree SHA-256: ${'f'.repeat(64)}`),
    ).toHaveLength(2)
    expect(screen.getAllByTestId('plotly-chart')).toHaveLength(2)
    expect(fetchSpy).toHaveBeenCalledWith('/api/analysis/sweep', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        scenario: '73_easting',
        parameter_name: 'hit_probability_modifier',
        values: [1, 2],
        metrics: ['blue_destroyed', 'red_destroyed'],
        num_iterations: 3,
        base_seed: 42,
        max_ticks: 10000,
      }),
    })
  })

  it('visibly rejects a response with missing metric statistics instead of plotting zeros', async () => {
    const response = sweepResult()
    const malformedMetric = response.points[0]!.metric_results[0] as unknown as {
      mean?: number
      std?: number
    }
    delete malformedMetric.mean
    delete malformedMetric.std
    mockSweep(response)
    renderWithProviders(<SweepPanel />)
    const user = await fillSweepForm('1,2')
    const numberInputs = screen.getAllByRole('spinbutton')
    await user.clear(numberInputs[0]!)
    await user.type(numberInputs[0]!, '3')

    await user.click(screen.getByRole('button', { name: 'Run Sweep' }))

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('Sweep result rejected:')
    })
    expect(
      screen.queryByLabelText('Sweep raw vectors and provenance'),
    ).not.toBeInTheDocument()
    expect(screen.queryByTestId('plotly-chart')).not.toBeInTheDocument()
  })

  it('rejects a self-consistent response produced for a different scenario', async () => {
    const response = sweepResult()
    for (const point of response.points) {
      point.batch.scenario_path = '/data/scenarios/wrong_scenario/scenario.yaml'
    }
    mockSweep(response)
    renderWithProviders(<SweepPanel />)
    const user = await fillSweepForm('1,2')
    const numberInputs = screen.getAllByRole('spinbutton')
    await user.clear(numberInputs[0]!)
    await user.type(numberInputs[0]!, '3')

    await user.click(screen.getByRole('button', { name: 'Run Sweep' }))

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(
        'scenario does not match the submitted request',
      )
    })
    expect(
      screen.queryByLabelText('Sweep raw vectors and provenance'),
    ).not.toBeInTheDocument()
  })
})
