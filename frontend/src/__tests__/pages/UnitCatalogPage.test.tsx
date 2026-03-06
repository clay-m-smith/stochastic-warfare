import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../helpers'
import { UnitCatalogPage } from '../../pages/units/UnitCatalogPage'
import type { UnitSummary } from '../../types/api'

const MOCK_UNITS: UnitSummary[] = [
  {
    unit_type: 'm1a1_abrams',
    display_name: 'M1A1 Abrams',
    domain: 'land',
    category: 'armor',
    era: 'modern',
    max_speed: 20,
    crew_size: 4,
  },
  {
    unit_type: 'f16_falcon',
    display_name: 'F-16 Falcon',
    domain: 'air',
    category: 'fighter',
    era: 'modern',
    max_speed: 600,
    crew_size: 1,
  },
  {
    unit_type: 'tiger_i',
    display_name: 'Tiger I',
    domain: 'land',
    category: 'armor',
    era: 'ww2',
    max_speed: 12,
    crew_size: 5,
  },
]

beforeEach(() => {
  vi.restoreAllMocks()
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(JSON.stringify(MOCK_UNITS), { status: 200 }),
  )
})

describe('UnitCatalogPage', () => {
  it('renders unit cards', async () => {
    renderWithProviders(<UnitCatalogPage />)
    await waitFor(() => {
      expect(screen.getByText('M1A1 Abrams')).toBeInTheDocument()
    })
    expect(screen.getByText('F-16 Falcon')).toBeInTheDocument()
    expect(screen.getByText('Tiger I')).toBeInTheDocument()
  })

  it('filters by domain', async () => {
    const user = userEvent.setup()
    renderWithProviders(<UnitCatalogPage />)
    await waitFor(() => {
      expect(screen.getByText('M1A1 Abrams')).toBeInTheDocument()
    })
    const domainSelect = screen.getAllByRole('combobox')[0]!
    await user.selectOptions(domainSelect, 'air')
    expect(screen.queryByText('M1A1 Abrams')).not.toBeInTheDocument()
    expect(screen.getByText('F-16 Falcon')).toBeInTheDocument()
  })

  it('filters by era', async () => {
    const user = userEvent.setup()
    renderWithProviders(<UnitCatalogPage />)
    await waitFor(() => {
      expect(screen.getByText('Tiger I')).toBeInTheDocument()
    })
    const eraSelect = screen.getAllByRole('combobox')[1]!
    await user.selectOptions(eraSelect, 'ww2')
    expect(screen.queryByText('M1A1 Abrams')).not.toBeInTheDocument()
    expect(screen.getByText('Tiger I')).toBeInTheDocument()
  })

  it('filters by search text', async () => {
    const user = userEvent.setup()
    renderWithProviders(<UnitCatalogPage />)
    await waitFor(() => {
      expect(screen.getByText('M1A1 Abrams')).toBeInTheDocument()
    })
    const searchInput = screen.getByPlaceholderText('Search units...')
    await user.type(searchInput, 'tiger')
    await waitFor(() => {
      expect(screen.queryByText('M1A1 Abrams')).not.toBeInTheDocument()
    })
    expect(screen.getByText('Tiger I')).toBeInTheDocument()
  })

  it('opens unit detail modal on card click', async () => {
    const user = userEvent.setup()
    // Mock fetch to return units list, then unit detail
    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify(MOCK_UNITS), { status: 200 }))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ unit_type: 'm1a1_abrams', definition: { name: 'M1A1 Abrams', crew: 4 } }),
          { status: 200 },
        ),
      )
    renderWithProviders(<UnitCatalogPage />)
    await waitFor(() => {
      expect(screen.getByText('M1A1 Abrams')).toBeInTheDocument()
    })
    await user.click(screen.getAllByText('M1A1 Abrams')[0]!)
    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })
  })

  it('shows empty state when no units match', async () => {
    const user = userEvent.setup()
    renderWithProviders(<UnitCatalogPage />)
    await waitFor(() => {
      expect(screen.getByText('M1A1 Abrams')).toBeInTheDocument()
    })
    const searchInput = screen.getByPlaceholderText('Search units...')
    await user.type(searchInput, 'zzzznotfound')
    await waitFor(() => {
      expect(screen.getByText('No units match your filters.')).toBeInTheDocument()
    })
  })
})
