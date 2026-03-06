import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../helpers'
import { ScenarioListPage } from '../../pages/scenarios/ScenarioListPage'
import type { ScenarioSummary } from '../../types/api'

const MOCK_SCENARIOS: ScenarioSummary[] = [
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
  },
  {
    name: 'jutland_1916',
    display_name: 'Jutland 1916',
    era: 'ww1',
    duration_hours: 12,
    sides: ['british', 'german'],
    terrain_type: 'coastal',
    has_ew: false,
    has_cbrn: false,
    has_escalation: false,
    has_schools: false,
  },
  {
    name: 'taiwan_strait',
    display_name: 'Taiwan Strait',
    era: 'modern',
    duration_hours: 72,
    sides: ['blue', 'red'],
    terrain_type: 'coastal',
    has_ew: true,
    has_cbrn: false,
    has_escalation: true,
    has_schools: false,
  },
]

beforeEach(() => {
  vi.restoreAllMocks()
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(JSON.stringify(MOCK_SCENARIOS), { status: 200 }),
  )
})

describe('ScenarioListPage', () => {
  it('renders scenario cards after loading', async () => {
    renderWithProviders(<ScenarioListPage />)
    await waitFor(() => {
      expect(screen.getByText('73 Easting')).toBeInTheDocument()
    })
    expect(screen.getByText('Jutland 1916')).toBeInTheDocument()
    expect(screen.getByText('Taiwan Strait')).toBeInTheDocument()
  })

  it('shows loading spinner initially', () => {
    vi.spyOn(globalThis, 'fetch').mockReturnValue(new Promise(() => {}))
    renderWithProviders(<ScenarioListPage />)
    expect(document.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('shows error message on fetch failure', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('Network error'))
    renderWithProviders(<ScenarioListPage />)
    await waitFor(() => {
      expect(screen.getByText(/Network error/)).toBeInTheDocument()
    })
  })

  it('filters by era', async () => {
    const user = userEvent.setup()
    renderWithProviders(<ScenarioListPage />)
    await waitFor(() => {
      expect(screen.getByText('73 Easting')).toBeInTheDocument()
    })
    const eraSelect = screen.getAllByRole('combobox')[0]!
    await user.selectOptions(eraSelect, 'ww1')
    expect(screen.queryByText('73 Easting')).not.toBeInTheDocument()
    expect(screen.getByText('Jutland 1916')).toBeInTheDocument()
  })

  it('filters by search text', async () => {
    const user = userEvent.setup()
    renderWithProviders(<ScenarioListPage />)
    await waitFor(() => {
      expect(screen.getByText('73 Easting')).toBeInTheDocument()
    })
    const searchInput = screen.getByPlaceholderText('Search scenarios...')
    await user.type(searchInput, 'taiwan')
    await waitFor(() => {
      expect(screen.queryByText('73 Easting')).not.toBeInTheDocument()
    })
    expect(screen.getByText('Taiwan Strait')).toBeInTheDocument()
  })

  it('shows empty state when no scenarios match', async () => {
    const user = userEvent.setup()
    renderWithProviders(<ScenarioListPage />)
    await waitFor(() => {
      expect(screen.getByText('73 Easting')).toBeInTheDocument()
    })
    const searchInput = screen.getByPlaceholderText('Search scenarios...')
    await user.type(searchInput, 'zzzznotfound')
    await waitFor(() => {
      expect(screen.getByText('No scenarios match your filters.')).toBeInTheDocument()
    })
  })

  it('shows EW and Escalation badges', async () => {
    renderWithProviders(<ScenarioListPage />)
    await waitFor(() => {
      expect(screen.getByText('Taiwan Strait')).toBeInTheDocument()
    })
    expect(screen.getByText('EW')).toBeInTheDocument()
    expect(screen.getByText('Escalation')).toBeInTheDocument()
  })

  it('sorts by era', async () => {
    const user = userEvent.setup()
    renderWithProviders(<ScenarioListPage />)
    await waitFor(() => {
      expect(screen.getByText('73 Easting')).toBeInTheDocument()
    })
    const sortSelect = screen.getAllByRole('combobox')[1]!
    await user.selectOptions(sortSelect, 'era')
    const cards = screen.getAllByRole('heading', { level: 3 })
    // Modern scenarios first (73 Easting, Taiwan Strait), then WW1 (Jutland)
    expect(cards[cards.length - 1]!.textContent).toBe('Jutland 1916')
  })
})
