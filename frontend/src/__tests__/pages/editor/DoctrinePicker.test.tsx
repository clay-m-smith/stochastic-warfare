import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { DoctrinePicker } from '../../../pages/editor/DoctrinePicker'

const MOCK_SCHOOLS = [
  { school_id: 'maneuverist', display_name: 'Maneuver Warfare', description: 'Dislocation over destruction', ooda_multiplier: 1.2, risk_tolerance: 'high' },
  { school_id: 'attrition', display_name: 'Attrition', description: 'Destroy enemy combat power', ooda_multiplier: 0.9, risk_tolerance: 'low' },
]

function renderPicker(config: Record<string, unknown> = {}, dispatch = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(JSON.stringify(MOCK_SCHOOLS), { status: 200 }),
  )
  const defaultConfig = { sides: [{ side: 'blue' }, { side: 'red' }], ...config }
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <DoctrinePicker config={defaultConfig} dispatch={dispatch} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return dispatch
}

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('DoctrinePicker', () => {
  it('renders per-side dropdowns', async () => {
    renderPicker()
    await waitFor(() => {
      expect(screen.getByLabelText('Blue School')).toBeInTheDocument()
    })
    expect(screen.getByLabelText('Red School')).toBeInTheDocument()
  })

  it('displays None option in dropdowns', async () => {
    renderPicker()
    await waitFor(() => {
      expect(screen.getByLabelText('Blue School')).toBeInTheDocument()
    })
    const options = screen.getAllByText('None')
    expect(options.length).toBeGreaterThanOrEqual(2)
  })

  it('dispatches SET_SCHOOL when school selected', async () => {
    const dispatch = renderPicker()
    await waitFor(() => {
      const select = screen.getByLabelText('Blue School') as HTMLSelectElement
      expect(select.options.length).toBeGreaterThan(1)
    })
    const select = screen.getByLabelText('Blue School') as HTMLSelectElement
    select.value = 'maneuverist'
    fireEvent.change(select)
    expect(dispatch).toHaveBeenCalledWith({
      type: 'SET_SCHOOL',
      side: 'blue',
      school_id: 'maneuverist',
    })
  })

  it('shows school description when selected', async () => {
    renderPicker({ school_config: { blue_school: 'maneuverist' } })
    await waitFor(() => {
      const select = screen.getByLabelText('Blue School') as HTMLSelectElement
      expect(select.options.length).toBeGreaterThan(1)
    })
    expect(screen.getByText('Dislocation over destruction')).toBeInTheDocument()
    expect(screen.getByText('OODA 1.2x')).toBeInTheDocument()
  })
})
