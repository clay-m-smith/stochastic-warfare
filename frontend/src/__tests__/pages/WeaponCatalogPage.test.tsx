import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { renderWithProviders } from '../helpers'
import { WeaponCatalogPage } from '../../pages/weapons/WeaponCatalogPage'

const MOCK_WEAPONS = [
  { weapon_id: 'm256_120mm', display_name: 'M256 120mm', category: 'gun', max_range_m: 4000, caliber_mm: 120 },
  { weapon_id: 'agm88_harm', display_name: 'AGM-88 HARM', category: 'missile', max_range_m: 150000, caliber_mm: 0 },
  { weapon_id: 'mk54_torpedo', display_name: 'Mk 54 Torpedo', category: 'torpedo', max_range_m: 9000, caliber_mm: 324 },
]

beforeEach(() => {
  vi.restoreAllMocks()
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(JSON.stringify(MOCK_WEAPONS), { status: 200 }),
  )
})

describe('WeaponCatalogPage', () => {
  it('renders weapon cards', async () => {
    renderWithProviders(<WeaponCatalogPage />)
    await waitFor(() => {
      expect(screen.getByText('M256 120mm')).toBeInTheDocument()
    })
    expect(screen.getByText('AGM-88 HARM')).toBeInTheDocument()
    expect(screen.getByText('Mk 54 Torpedo')).toBeInTheDocument()
  })

  it('renders search input', async () => {
    renderWithProviders(<WeaponCatalogPage />)
    await waitFor(() => {
      expect(screen.getByPlaceholderText('Search weapons...')).toBeInTheDocument()
    })
  })

  it('shows empty state when no weapons match', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify([]), { status: 200 }),
    )
    renderWithProviders(<WeaponCatalogPage />)
    await waitFor(() => {
      expect(screen.getByText('No weapons match your filters.')).toBeInTheDocument()
    })
  })

  it('renders page header', async () => {
    renderWithProviders(<WeaponCatalogPage />)
    await waitFor(() => {
      expect(screen.getByText('Weapon Catalog')).toBeInTheDocument()
    })
  })
})
