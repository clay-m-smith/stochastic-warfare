import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { UnitPicker } from '../../../pages/editor/UnitPicker'

const MOCK_UNITS = [
  { unit_type: 'm1a2_abrams', display_name: 'M1A2 Abrams', domain: 'ground', era: 'modern', category: 'armor', max_speed: 67, crew_size: 4 },
  { unit_type: 'f15_eagle', display_name: 'F-15 Eagle', domain: 'air', era: 'modern', category: 'fighter', max_speed: 2650, crew_size: 1 },
  { unit_type: 't72b3', display_name: 'T-72B3', domain: 'ground', era: 'modern', category: 'armor', max_speed: 60, crew_size: 3 },
]

function renderPicker(onSelect: (t: string) => void, onClose: () => void) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(JSON.stringify(MOCK_UNITS), { status: 200 }),
  )
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <UnitPicker era="modern" onSelect={onSelect} onClose={onClose} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('UnitPicker', () => {
  it('renders search input and title', async () => {
    renderPicker(vi.fn(), vi.fn())
    await waitFor(() => {
      expect(screen.getByText('Add Unit')).toBeInTheDocument()
    })
    expect(screen.getByPlaceholderText('Search units...')).toBeInTheDocument()
  })

  it('displays units from API', async () => {
    renderPicker(vi.fn(), vi.fn())
    await waitFor(() => {
      expect(screen.getByText('M1A2 Abrams')).toBeInTheDocument()
    })
    expect(screen.getByText('F-15 Eagle')).toBeInTheDocument()
  })

  it('calls onSelect when unit clicked', async () => {
    const onSelect = vi.fn()
    renderPicker(onSelect, vi.fn())
    await waitFor(() => {
      expect(screen.getByText('M1A2 Abrams')).toBeInTheDocument()
    })
    fireEvent.click(screen.getByText('M1A2 Abrams'))
    expect(onSelect).toHaveBeenCalledWith('m1a2_abrams')
  })
})
