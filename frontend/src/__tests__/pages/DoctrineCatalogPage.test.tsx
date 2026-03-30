import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { renderWithProviders } from '../helpers'
import { DoctrineCatalogPage } from '../../pages/doctrines/DoctrineCatalogPage'

const MOCK_DOCTRINES = [
  { name: 'nato_standard', category: 'nato', display_name: 'NATO Standard' },
  { name: 'deep_operations', category: 'russian', display_name: 'Deep Operations' },
  { name: 'guerrilla_hit_and_run', category: 'unconventional', display_name: 'Guerrilla Hit & Run' },
]

beforeEach(() => {
  vi.restoreAllMocks()
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(JSON.stringify(MOCK_DOCTRINES), { status: 200 }),
  )
})

describe('DoctrineCatalogPage', () => {
  it('renders doctrine cards', async () => {
    renderWithProviders(<DoctrineCatalogPage />)
    await waitFor(() => {
      expect(screen.getByText('NATO Standard')).toBeInTheDocument()
    })
    expect(screen.getByText('Deep Operations')).toBeInTheDocument()
    expect(screen.getByText('Guerrilla Hit & Run')).toBeInTheDocument()
  })

  it('renders search input', async () => {
    renderWithProviders(<DoctrineCatalogPage />)
    await waitFor(() => {
      expect(screen.getByPlaceholderText('Search doctrines...')).toBeInTheDocument()
    })
  })

  it('shows empty state when no doctrines match', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify([]), { status: 200 }),
    )
    renderWithProviders(<DoctrineCatalogPage />)
    await waitFor(() => {
      expect(screen.getByText('No doctrines match your search.')).toBeInTheDocument()
    })
  })
})
