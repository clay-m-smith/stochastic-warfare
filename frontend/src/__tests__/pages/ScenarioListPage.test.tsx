import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../helpers'
import { ScenarioListPage } from '../../pages/scenarios/ScenarioListPage'
import type { HistoricalValidationSummary, ScenarioSummary } from '../../types/api'

const CURRENT_ENGINE_REGRESSION_VALIDATION: HistoricalValidationSummary = {
  aggregate_disposition: 'unsupported',
  current_engine_regression_evidence: true,
  accepted_claim_ids: [],
  ledger_sha256: 'a'.repeat(64),
  claims: [],
}

const NO_REGRESSION_VALIDATION: HistoricalValidationSummary = {
  ...CURRENT_ENGINE_REGRESSION_VALIDATION,
  current_engine_regression_evidence: false,
}

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
    has_space: false,
    has_dew: false,
    historical_validation: CURRENT_ENGINE_REGRESSION_VALIDATION,
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
    has_space: false,
    has_dew: false,
    historical_validation: NO_REGRESSION_VALIDATION,
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
    has_space: true,
    has_dew: true,
    historical_validation: NO_REGRESSION_VALIDATION,
  },
  {
    name: 'bint_jbeil_2006',
    display_name: 'Bint Jbeil 2006',
    era: 'modern',
    duration_hours: 240,
    sides: ['blue', 'red'],
    terrain_type: 'hilly_defense',
    has_ew: false,
    has_cbrn: true,
    has_escalation: false,
    has_schools: true,
    has_space: false,
    has_dew: false,
    historical_validation: NO_REGRESSION_VALIDATION,
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

  it('shows all typed optional-subsystem badges', async () => {
    renderWithProviders(<ScenarioListPage />)
    await waitFor(() => {
      expect(screen.getByText('Taiwan Strait')).toBeInTheDocument()
    })
    expect(screen.getByText('EW')).toBeInTheDocument()
    expect(screen.getByText('Escalation')).toBeInTheDocument()
    expect(screen.getByText('Space')).toBeInTheDocument()
    expect(screen.getByText('DEW')).toBeInTheDocument()
    expect(screen.getByText('CBRN')).toBeInTheDocument()
    expect(screen.getByText('Schools')).toBeInTheDocument()
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
    // Regression-reference 73 Easting first, then Modern, then WW1 (Jutland)
    expect(cards[cards.length - 1]!.textContent).toBe('Jutland 1916')
  })

  it('groups regression references only by typed evidence', async () => {
    renderWithProviders(<ScenarioListPage />)
    await waitFor(() => {
      expect(screen.getByText('73 Easting')).toBeInTheDocument()
    })
    const regressionHeading = screen.getByRole('heading', {
      level: 2,
      name: /Current-Engine Regression References/,
    })
    const modernHeading = screen.getByRole('heading', {
      level: 2,
      name: /^Modern/,
    })
    const regressionSection = regressionHeading.closest('section')
    const modernSection = modernHeading.closest('section')

    expect(regressionSection).not.toBeNull()
    expect(modernSection).not.toBeNull()
    expect(within(regressionSection!).getByText('73 Easting')).toBeInTheDocument()
    expect(within(regressionSection!).queryByText('Bint Jbeil 2006')).not.toBeInTheDocument()
    expect(within(modernSection!).getByText('Bint Jbeil 2006')).toBeInTheDocument()
    expect(within(modernSection!).queryByText('73 Easting')).not.toBeInTheDocument()
    expect(screen.getByText(/typed current-engine regression evidence/i)).toBeInTheDocument()
    expect(screen.queryByText(/Golden Scenarios/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/historically calibrated/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/Block 11/i)).not.toBeInTheDocument()
  })

  it('shows era sections ordered Modern → WW1', async () => {
    renderWithProviders(<ScenarioListPage />)
    await waitFor(() => {
      expect(screen.getByText('73 Easting')).toBeInTheDocument()
    })
    const headings = screen.getAllByRole('heading', { level: 2 })
    const titles = headings.map((h) => h.textContent)
    const modernIdx = titles.findIndex((t) => t?.match(/Modern/))
    const ww1Idx = titles.findIndex((t) => t?.match(/WW1/))
    expect(modernIdx).toBeGreaterThan(-1)
    expect(ww1Idx).toBeGreaterThan(modernIdx)
  })
})
