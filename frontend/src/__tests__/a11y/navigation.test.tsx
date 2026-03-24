import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { Routes, Route } from 'react-router-dom'
import { renderWithProviders } from '../helpers'
import { Layout } from '../../components/Layout'

beforeEach(() => {
  vi.restoreAllMocks()
  localStorage.removeItem('sw-theme')
  document.documentElement.classList.remove('dark')
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  })
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(
      JSON.stringify({ status: 'ok', version: '0.1.0', scenario_count: 10, unit_count: 50 }),
      { status: 200 },
    ),
  )
})

afterEach(() => {
  localStorage.removeItem('sw-theme')
  document.documentElement.classList.remove('dark')
})

function renderLayout(route = '/scenarios') {
  return renderWithProviders(
    <Routes>
      <Route element={<Layout />}>
        <Route path="/scenarios" element={<div>Scenario Page</div>} />
      </Route>
    </Routes>,
    { route },
  )
}

describe('Layout accessibility', () => {
  it('skip link is present', () => {
    renderLayout()
    expect(screen.getByText('Skip to main content')).toBeInTheDocument()
  })

  it('skip link points to #main-content', () => {
    renderLayout()
    const link = screen.getByText('Skip to main content')
    expect(link).toHaveAttribute('href', '#main-content')
  })

  it('main element has id=main-content', () => {
    renderLayout()
    const main = screen.getByRole('main')
    expect(main).toHaveAttribute('id', 'main-content')
  })
})

describe('Sidebar accessibility', () => {
  it('health indicator has text label', async () => {
    renderLayout()
    await waitFor(() => {
      expect(screen.getByText('Connected')).toBeInTheDocument()
    })
  })

  it('health dot is aria-hidden', async () => {
    const { container } = renderLayout()
    await waitFor(() => {
      expect(screen.getByText('Connected')).toBeInTheDocument()
    })
    const dot = container.querySelector('.h-2.w-2.rounded-full')
    expect(dot).toHaveAttribute('aria-hidden', 'true')
  })
})

describe('UnitDetailModal accessibility', () => {
  it('close button has aria-label', async () => {
    vi.stubGlobal('ResizeObserver', class {
      observe() {}
      unobserve() {}
      disconnect() {}
    })
    // Import here to avoid hoisting issues
    const { UnitDetailModal } = await import('../../pages/units/UnitDetailModal')
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ definition: { name: 'M1A2 Abrams' } }), { status: 200 }),
    )
    renderWithProviders(<UnitDetailModal unitType="m1a2_abrams" onClose={vi.fn()} />)
    await waitFor(() => {
      expect(screen.getByLabelText('Close')).toBeInTheDocument()
    })
  })
})

describe('KeyboardShortcutHelp accessibility', () => {
  it('close button has aria-label', async () => {
    vi.stubGlobal('ResizeObserver', class {
      observe() {}
      unobserve() {}
      disconnect() {}
    })
    const { KeyboardShortcutHelp } = await import('../../components/KeyboardShortcutHelp')
    renderWithProviders(
      <KeyboardShortcutHelp
        open={true}
        onClose={vi.fn()}
        shortcuts={[{ key: 's', action: vi.fn(), description: 'Save' }]}
      />,
    )
    expect(screen.getByLabelText('Close keyboard shortcuts')).toBeInTheDocument()
  })
})
