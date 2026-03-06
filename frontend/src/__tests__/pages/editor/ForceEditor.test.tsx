import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { ForceEditor } from '../../../pages/editor/ForceEditor'
import type { EditorAction } from '../../../types/editor'

function renderForceEditor(config: Record<string, unknown>, dispatch: (a: EditorAction) => void) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ForceEditor config={config} dispatch={dispatch} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.restoreAllMocks()
})

const CONFIG = {
  era: 'modern',
  sides: [
    { side: 'blue', units: [{ unit_type: 'm1a2_abrams', count: 2 }] },
    { side: 'red', units: [{ unit_type: 't72b3', count: 3 }] },
  ],
}

describe('ForceEditor', () => {
  it('renders side names', () => {
    const dispatch = vi.fn()
    renderForceEditor(CONFIG, dispatch)
    expect(screen.getByText('blue')).toBeInTheDocument()
    expect(screen.getByText('red')).toBeInTheDocument()
  })

  it('renders unit types', () => {
    const dispatch = vi.fn()
    renderForceEditor(CONFIG, dispatch)
    expect(screen.getByText('m1a2_abrams')).toBeInTheDocument()
    expect(screen.getByText('t72b3')).toBeInTheDocument()
  })

  it('dispatches REMOVE_UNIT on remove click', () => {
    const dispatch = vi.fn()
    renderForceEditor(CONFIG, dispatch)
    const removeButtons = screen.getAllByText('Remove')
    fireEvent.click(removeButtons[0]!)
    expect(dispatch).toHaveBeenCalledWith({ type: 'REMOVE_UNIT', sideIndex: 0, unitIndex: 0 })
  })

  it('dispatches SET_UNIT_COUNT on + click', () => {
    const dispatch = vi.fn()
    renderForceEditor(CONFIG, dispatch)
    const plusButtons = screen.getAllByText('+')
    fireEvent.click(plusButtons[0]!)
    expect(dispatch).toHaveBeenCalledWith({ type: 'SET_UNIT_COUNT', sideIndex: 0, unitIndex: 0, count: 3 })
  })
})
