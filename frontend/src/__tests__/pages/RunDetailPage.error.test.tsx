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

const BASE_RUN = {
  run_id: 'r1',
  scenario_name: '73 Easting',
  scenario_path: 'scenarios/73_easting',
  seed: 42,
  max_ticks: 10000,
  config_overrides: {},
  created_at: '2025-01-01T00:00:00Z',
  started_at: '2025-01-01T00:00:01Z',
  completed_at: '2025-01-01T00:01:00Z',
  result: null,
}

beforeEach(() => {
  vi.restoreAllMocks()
  vi.stubGlobal('WebSocket', class { close() {} })
})

describe('RunDetailPage error/cancelled states', () => {
  it('shows cancelled badge for cancelled run', async () => {
    renderRunDetailPage('r1', { ...BASE_RUN, status: 'cancelled' })
    await waitFor(() => {
      expect(screen.getByText('cancelled')).toBeInTheDocument()
    })
  })

  it('displays multi-line traceback in formatted pre block', async () => {
    const traceback = 'Traceback (most recent call last):\n  File "engine.py", line 42\nValueError: bad config'
    renderRunDetailPage('r1', {
      ...BASE_RUN,
      status: 'failed',
      error_message: traceback,
    })
    await waitFor(() => {
      const pre = document.querySelector('pre')
      expect(pre).toBeInTheDocument()
      expect(pre?.textContent).toContain('Traceback')
      expect(pre?.textContent).toContain('ValueError')
    })
  })
})
