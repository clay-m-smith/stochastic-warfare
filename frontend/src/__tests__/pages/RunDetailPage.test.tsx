import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { RunDetailPage } from '../../pages/runs/RunDetailPage'
import { Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

function renderRunDetailPage(runId: string, mockData: Record<string, unknown>) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(JSON.stringify(mockData), { status: 200 }),
  )
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/runs/${runId}`]}>
        <Routes>
          <Route path="/runs/:runId" element={<RunDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const COMPLETED_RUN = {
  run_id: 'r1',
  scenario_name: '73 Easting',
  scenario_path: 'scenarios/73_easting',
  seed: 42,
  max_ticks: 10000,
  config_overrides: {},
  status: 'completed',
  created_at: '2025-01-01T00:00:00Z',
  started_at: '2025-01-01T00:00:01Z',
  completed_at: '2025-01-01T00:01:00Z',
  result: {
    scenario: '73_easting',
    seed: 42,
    ticks_executed: 5000,
    duration_s: 59,
    victory: { status: 'decisive', winner: 'blue' },
    sides: {
      blue: { total: 10, active: 8, destroyed: 2 },
      red: { total: 8, active: 2, destroyed: 6 },
    },
  },
  error_message: null,
}

const PENDING_RUN = {
  ...COMPLETED_RUN,
  run_id: 'r2',
  status: 'pending',
  completed_at: null,
  result: null,
}

beforeEach(() => {
  vi.restoreAllMocks()
  // Mock WebSocket to prevent errors
  vi.stubGlobal('WebSocket', class { close() {} })
})

describe('RunDetailPage', () => {
  it('shows loading spinner initially', () => {
    vi.spyOn(globalThis, 'fetch').mockReturnValue(new Promise(() => {}))
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={['/runs/r1']}>
          <Routes>
            <Route path="/runs/:runId" element={<RunDetailPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )
    expect(document.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('displays scenario name and status for completed run', async () => {
    renderRunDetailPage('r1', COMPLETED_RUN)
    await waitFor(() => {
      expect(screen.getByText('73 Easting')).toBeInTheDocument()
    })
    expect(screen.getByText('completed')).toBeInTheDocument()
  })

  it('shows tabs for completed run', async () => {
    renderRunDetailPage('r1', COMPLETED_RUN)
    await waitFor(() => {
      expect(screen.getByText('Results')).toBeInTheDocument()
    })
    expect(screen.getByText('Charts')).toBeInTheDocument()
    expect(screen.getByText('Narrative')).toBeInTheDocument()
    expect(screen.getByText('Events')).toBeInTheDocument()
  })

  it('shows progress panel for pending run', async () => {
    renderRunDetailPage('r2', PENDING_RUN)
    await waitFor(() => {
      expect(screen.getByText('Live Progress')).toBeInTheDocument()
    })
  })

  it('shows error message for failed run', async () => {
    const failedRun = {
      ...COMPLETED_RUN,
      status: 'failed',
      result: null,
      error_message: 'Scenario file not found',
    }
    renderRunDetailPage('r3', failedRun)
    await waitFor(() => {
      expect(screen.getByText('Scenario file not found')).toBeInTheDocument()
    })
  })

  it('shows run metadata', async () => {
    renderRunDetailPage('r1', COMPLETED_RUN)
    await waitFor(() => {
      expect(screen.getByText('Seed:')).toBeInTheDocument()
    })
    expect(screen.getByText('Max Ticks:')).toBeInTheDocument()
  })
})
