import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../helpers'
import { BatchPanel } from '../../pages/analysis/BatchPanel'
import { completedBatchDetail } from '../fixtures/analysis'
import type { BatchDetail } from '../../types/api'

vi.mock('../../components/charts/PlotlyChart', () => ({
  PlotlyChart: () => <div data-testid="plotly-chart" />,
}))

const MOCK_SCENARIOS = [
  { name: '73_easting', display_name: '73 Easting', era: 'modern', duration_hours: 4, sides: ['blue', 'red'], terrain_type: 'desert', has_ew: false, has_cbrn: false, has_escalation: false, has_schools: false, has_space: false, has_dew: false },
]

beforeEach(() => {
  vi.restoreAllMocks()
  class MockWebSocket {
    onopen: (() => void) | null = null
    onmessage: (() => void) | null = null
    onclose: (() => void) | null = null
    onerror: (() => void) | null = null

    constructor(_url: string) {}

    close() {}
  }
  vi.stubGlobal('WebSocket', MockWebSocket)
})

function mockCompletedBatch(detail: BatchDetail) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) => {
    const path = typeof url === 'string' ? url : url.toString()
    if (path === '/api/scenarios') {
      return new Response(JSON.stringify(MOCK_SCENARIOS), { status: 200 })
    }
    if (path === '/api/runs/batch') {
      return new Response(JSON.stringify({ batch_id: detail.batch_id, status: 'pending' }), {
        status: 202,
      })
    }
    if (path === `/api/runs/batch/${detail.batch_id}`) {
      return new Response(JSON.stringify(detail), { status: 200 })
    }
    return new Response(JSON.stringify({ detail: 'unexpected request' }), { status: 404 })
  })
}

async function submitThreeIterationBatch() {
  const user = userEvent.setup()
  await screen.findByText('73 Easting')
  await user.selectOptions(screen.getByRole('combobox'), '73_easting')
  const numberInputs = screen.getAllByRole('spinbutton')
  await user.clear(numberInputs[0]!)
  await user.type(numberInputs[0]!, '3')
  await user.click(screen.getByRole('button', { name: 'Run Batch' }))
}

describe('BatchPanel', () => {
  it('renders the form', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(MOCK_SCENARIOS), { status: 200 }),
    )
    renderWithProviders(<BatchPanel />)
    await waitFor(() => {
      expect(screen.getByText('Monte Carlo Batch')).toBeInTheDocument()
    })
    expect(screen.getByText('Run Batch')).toBeInTheDocument()
  })

  it('disables submit when no scenario selected', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(MOCK_SCENARIOS), { status: 200 }),
    )
    renderWithProviders(<BatchPanel />)
    await waitFor(() => {
      expect(screen.getByText('Run Batch')).toBeDisabled()
    })
  })

  it('enables submit when scenario is selected', async () => {
    const user = userEvent.setup()
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(MOCK_SCENARIOS), { status: 200 }),
    )
    renderWithProviders(<BatchPanel />)
    await waitFor(() => {
      expect(screen.getByText('73 Easting')).toBeInTheDocument()
    })
    // Button is disabled before selection
    expect(screen.getByText('Run Batch')).toBeDisabled()
    // Select scenario
    const selects = screen.getAllByRole('combobox')
    await user.selectOptions(selects[0]!, '73_easting')
    // Button should now be enabled
    await waitFor(() => {
      expect(screen.getByText('Run Batch')).not.toBeDisabled()
    })
  })

  it('shows iterations and seed inputs', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(MOCK_SCENARIOS), { status: 200 }),
    )
    renderWithProviders(<BatchPanel />)
    await waitFor(() => {
      expect(screen.getByText('Iterations')).toBeInTheDocument()
    })
    expect(screen.getByText('Base Seed')).toBeInTheDocument()
    expect(screen.getByText('Max Ticks')).toBeInTheDocument()
  })

  it('plots and exposes the completed batch raw vectors and provenance', async () => {
    const detail = completedBatchDetail()
    const fetchMock = mockCompletedBatch(detail)
    renderWithProviders(<BatchPanel />)

    await submitThreeIterationBatch()

    await screen.findByLabelText('Batch provenance')
    expect(screen.getByText('raw: [1,2,3]')).toBeInTheDocument()
    expect(screen.getAllByTestId('plotly-chart')).toHaveLength(4)
    expect(screen.getByText('42, 43, 44')).toBeInTheDocument()
    expect(screen.getByText('1'.repeat(40), { exact: false })).toBeInTheDocument()
    expect(screen.getByText('6'.repeat(64))).toBeInTheDocument()
    expect(screen.getByText('7'.repeat(64))).toBeInTheDocument()
    expect(screen.getByText('8'.repeat(64))).toBeInTheDocument()
    const submittedRequest = fetchMock.mock.calls.find(([url]) => (
      (typeof url === 'string' ? url : url.toString()) === '/api/runs/batch'
    ))
    expect(JSON.parse(String(submittedRequest?.[1]?.body))).toMatchObject({
      scenario: '73_easting',
      metrics: [
        'blue_active',
        'blue_destroyed',
        'red_active',
        'red_destroyed',
      ],
    })
  })

  it('visibly rejects a completed response missing raw evidence', async () => {
    const detail = completedBatchDetail()
    detail.raw_metrics = null
    mockCompletedBatch(detail)
    renderWithProviders(<BatchPanel />)

    await submitThreeIterationBatch()

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(
        'Completed batch rejected: completed batch is missing raw-vector or provenance evidence',
      )
    })
    expect(screen.queryByText('Distribution')).not.toBeInTheDocument()
  })

  it('visibly rejects a completed response with a partial raw vector', async () => {
    const detail = completedBatchDetail()
    detail.raw_metrics!.red_destroyed = [1, 2]
    mockCompletedBatch(detail)
    renderWithProviders(<BatchPanel />)

    await submitThreeIterationBatch()

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(
        'raw metric red_destroyed must contain exactly 3 values',
      )
    })
    expect(screen.queryByText('Distribution')).not.toBeInTheDocument()
  })

  it('rejects provenance with the submitted scenario directory but a wrong filename', async () => {
    const detail = completedBatchDetail()
    detail.provenance!.scenario_path = (
      '/data/scenarios/73_easting/not-the-scenario.yaml'
    )
    mockCompletedBatch(detail)
    renderWithProviders(<BatchPanel />)

    await submitThreeIterationBatch()

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(
        'Completed batch rejected: completed batch provenance identity is inconsistent',
      )
    })
    expect(screen.queryByText('Distribution')).not.toBeInTheDocument()
  })

  it('rejects a bare submitted scenario ID as resolved provenance', async () => {
    const detail = completedBatchDetail()
    detail.provenance!.scenario_path = '73_easting'
    mockCompletedBatch(detail)
    renderWithProviders(<BatchPanel />)

    await submitThreeIterationBatch()

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(
        'Completed batch rejected: completed batch provenance identity is inconsistent',
      )
    })
    expect(screen.queryByText('Distribution')).not.toBeInTheDocument()
  })

  it('rejects a self-consistent metric subset that differs from the submitted contract', async () => {
    const detail = completedBatchDetail()
    detail.ordered_metrics = ['red_destroyed']
    detail.metrics = { red_destroyed: detail.metrics!.red_destroyed! }
    detail.raw_metrics = { red_destroyed: detail.raw_metrics!.red_destroyed! }
    detail.provenance!.ordered_metrics = ['red_destroyed']
    mockCompletedBatch(detail)
    renderWithProviders(<BatchPanel />)

    await submitThreeIterationBatch()

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(
        'Completed batch rejected: completed batch does not match the submitted request',
      )
    })
    expect(screen.queryByText('Distribution')).not.toBeInTheDocument()
  })

  it('accepts additive reinforcement assignments with new IDs on authored sides', async () => {
    const detail = completedBatchDetail()
    for (const run of detail.provenance!.runs) {
      run.runtime_provenance.arriving_unit_assignments = [{
        unit_id: `blue-reinforcement-${run.seed}`,
        side: 'blue',
        commander_profile_id: 'joint_campaign',
        doctrine_school_id: 'maneuverist',
      }]
    }
    mockCompletedBatch(detail)
    renderWithProviders(<BatchPanel />)

    await submitThreeIterationBatch()

    await screen.findByLabelText('Batch provenance')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.getByText('raw: [1,2,3]')).toBeInTheDocument()
  })

  it('rejects zero-tick evidence for a supposedly terminal run', async () => {
    const detail = completedBatchDetail()
    detail.provenance!.runs[0]!.ticks_executed = 0
    mockCompletedBatch(detail)
    renderWithProviders(<BatchPanel />)

    await submitThreeIterationBatch()

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(
        'Completed batch rejected: batch run 0 is incomplete',
      )
    })
  })

  it('rejects an unsupported terminal condition', async () => {
    const detail = completedBatchDetail()
    detail.provenance!.runs[0]!.condition_type = 'fabricated_terminal'
    mockCompletedBatch(detail)
    renderWithProviders(<BatchPanel />)

    await submitThreeIterationBatch()

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(
        'Completed batch rejected: batch run 0 is incomplete',
      )
    })
  })
})
