import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { screen, waitFor, fireEvent } from '@testing-library/react'
import { renderWithProviders } from '../helpers'
import { Layout } from '../../components/Layout'
import { Routes, Route } from 'react-router-dom'

beforeEach(() => {
  vi.restoreAllMocks()
  localStorage.removeItem('sw-theme')
  document.documentElement.classList.remove('dark')
  // Mock matchMedia for useTheme
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
    new Response(JSON.stringify({ status: 'ok', version: '0.1.0', scenario_count: 10, unit_count: 50 }), { status: 200 }),
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
        <Route path="/units" element={<div>Unit Page</div>} />
      </Route>
    </Routes>,
    { route },
  )
}

describe('Layout', () => {
  it('renders sidebar with nav links', async () => {
    renderLayout()
    expect(screen.getByText('Scenarios')).toBeInTheDocument()
    expect(screen.getByText('Units')).toBeInTheDocument()
    expect(screen.getByText('Runs')).toBeInTheDocument()
    expect(screen.getByText('Analysis')).toBeInTheDocument()
  })

  it('renders child route content', () => {
    renderLayout('/scenarios')
    expect(screen.getByText('Scenario Page')).toBeInTheDocument()
  })

  it('shows health status when API is reachable', async () => {
    renderLayout()
    await waitFor(() => {
      expect(screen.getByText(/10 scenarios/)).toBeInTheDocument()
    })
  })

  it('renders theme toggle button', () => {
    renderLayout()
    expect(screen.getByText('Dark Mode')).toBeInTheDocument()
  })

  it('clicking theme toggle switches to dark mode', () => {
    renderLayout()
    const toggleBtn = screen.getByText('Dark Mode')
    fireEvent.click(toggleBtn)
    expect(document.documentElement.classList.contains('dark')).toBe(true)
    expect(screen.getByText('Light Mode')).toBeInTheDocument()
  })
})
