import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { renderWithProviders } from '../helpers'
import { Layout } from '../../components/Layout'
import { Routes, Route } from 'react-router-dom'

beforeEach(() => {
  vi.restoreAllMocks()
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(JSON.stringify({ status: 'ok', version: '0.1.0', scenario_count: 10, unit_count: 50 }), { status: 200 }),
  )
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
})
