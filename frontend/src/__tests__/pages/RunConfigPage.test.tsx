import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../helpers'
import { RunConfigPage } from '../../pages/runs/RunConfigPage'

const MOCK_DETAIL = {
  name: '73_easting',
  config: { name: '73 Easting', era: 'modern' },
  force_summary: {},
}

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('RunConfigPage', () => {
  it('shows error when no scenario specified', () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('[]', { status: 200 }))
    renderWithProviders(<RunConfigPage />, { route: '/runs/new' })
    expect(screen.getByText(/No scenario specified/)).toBeInTheDocument()
  })

  it('renders scenario name and form fields', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(MOCK_DETAIL), { status: 200 }),
    )
    renderWithProviders(<RunConfigPage />, { route: '/runs/new?scenario=73_easting' })
    await waitFor(() => {
      expect(screen.getByText('73 Easting')).toBeInTheDocument()
    })
    expect(screen.getByLabelText('Random Seed')).toBeInTheDocument()
    expect(screen.getByLabelText('Max Ticks')).toBeInTheDocument()
  })

  it('has default seed of 42 and max_ticks of 10000', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(MOCK_DETAIL), { status: 200 }),
    )
    renderWithProviders(<RunConfigPage />, { route: '/runs/new?scenario=73_easting' })
    await waitFor(() => {
      expect(screen.getByLabelText('Random Seed')).toHaveValue(42)
    })
    expect(screen.getByLabelText('Max Ticks')).toHaveValue(10000)
  })

  it('submits run and calls API', async () => {
    const user = userEvent.setup()
    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify(MOCK_DETAIL), { status: 200 }))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ run_id: 'run-123', status: 'pending' }), { status: 202 }),
      )
    renderWithProviders(<RunConfigPage />, { route: '/runs/new?scenario=73_easting' })
    await waitFor(() => {
      expect(screen.getByText('Start Run')).toBeInTheDocument()
    })
    await user.click(screen.getByText('Start Run'))
    await waitFor(() => {
      expect(fetch).toHaveBeenCalledTimes(2)
    })
  })

  it('shows error message on submit failure', async () => {
    const user = userEvent.setup()
    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify(MOCK_DETAIL), { status: 200 }))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: 'Scenario not found' }), { status: 404 }),
      )
    renderWithProviders(<RunConfigPage />, { route: '/runs/new?scenario=73_easting' })
    await waitFor(() => {
      expect(screen.getByText('Start Run')).toBeInTheDocument()
    })
    await user.click(screen.getByText('Start Run'))
    await waitFor(() => {
      expect(screen.getByText(/Scenario not found/)).toBeInTheDocument()
    })
  })
})
