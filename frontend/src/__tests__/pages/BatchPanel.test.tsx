import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../helpers'
import { BatchPanel } from '../../pages/analysis/BatchPanel'

const MOCK_SCENARIOS = [
  { name: '73_easting', display_name: '73 Easting', era: 'modern', duration_hours: 4, sides: ['blue', 'red'], terrain_type: 'desert', has_ew: false, has_cbrn: false, has_escalation: false, has_schools: false, has_space: false, has_dew: false },
]

beforeEach(() => {
  vi.restoreAllMocks()
})

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
})
