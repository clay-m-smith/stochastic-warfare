import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { CommanderPicker } from '../../../pages/editor/CommanderPicker'

const MOCK_COMMANDERS = [
  { profile_id: 'joint_commander', display_name: 'Joint Commander', description: 'Balanced joint ops', traits: { aggression: 0.6, caution: 0.5, flexibility: 0.7 } },
  { profile_id: 'conventional_commander', display_name: 'Conventional Commander', description: 'By-the-book approach', traits: { aggression: 0.4, caution: 0.8 } },
]

function renderPicker(config: Record<string, unknown> = {}, dispatch = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(JSON.stringify(MOCK_COMMANDERS), { status: 200 }),
  )
  const defaultConfig = { sides: [{ side: 'blue' }, { side: 'red' }], ...config }
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <CommanderPicker config={defaultConfig} dispatch={dispatch} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return dispatch
}

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('CommanderPicker', () => {
  it('renders per-side dropdowns', async () => {
    renderPicker()
    await waitFor(() => {
      expect(screen.getByLabelText('Blue Commander')).toBeInTheDocument()
    })
    expect(screen.getByLabelText('Red Commander')).toBeInTheDocument()
  })

  it('displays None option in dropdowns', async () => {
    renderPicker()
    await waitFor(() => {
      expect(screen.getByLabelText('Blue Commander')).toBeInTheDocument()
    })
    const options = screen.getAllByText('None')
    expect(options.length).toBeGreaterThanOrEqual(2)
  })

  it('dispatches SET_COMMANDER when commander selected', async () => {
    const dispatch = renderPicker()
    await waitFor(() => {
      const select = screen.getByLabelText('Blue Commander') as HTMLSelectElement
      expect(select.options.length).toBeGreaterThan(1)
    })
    const select = screen.getByLabelText('Blue Commander') as HTMLSelectElement
    select.value = 'joint_commander'
    fireEvent.change(select)
    expect(dispatch).toHaveBeenCalledWith({
      type: 'SET_COMMANDER',
      side: 'blue',
      profile_id: 'joint_commander',
    })
  })

  it('shows trait card when commander selected', async () => {
    renderPicker({ commander_config: { side_defaults: { blue: 'joint_commander' } } })
    await waitFor(() => {
      const select = screen.getByLabelText('Blue Commander') as HTMLSelectElement
      expect(select.options.length).toBeGreaterThan(1)
    })
    expect(screen.getByText('aggression')).toBeInTheDocument()
    expect(screen.getByText('0.6')).toBeInTheDocument()
    expect(screen.getByText('flexibility')).toBeInTheDocument()
  })
})
