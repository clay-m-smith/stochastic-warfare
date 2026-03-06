import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { renderWithProviders } from '../helpers'
import { ScenarioDetailPage } from '../../pages/scenarios/ScenarioDetailPage'
import { Routes, Route } from 'react-router-dom'

const MOCK_DETAIL = {
  name: '73_easting',
  config: {
    name: '73 Easting',
    era: 'modern',
    duration_hours: 4,
    terrain: { terrain_type: 'desert', width_m: 5000, height_m: 5000 },
    ew_config: {},
    documented_outcomes: [
      { metric: 'Blue casualties', value: '1 KIA', source: 'Bourque 2001' },
    ],
  },
  force_summary: {
    blue: { unit_count: 3, unit_types: ['m1a1_abrams', 'm3_bradley'] },
    red: { unit_count: 5, unit_types: ['t72', 'bmp2'] },
  },
}

beforeEach(() => {
  vi.restoreAllMocks()
})

function renderDetail() {
  return renderWithProviders(
    <Routes>
      <Route path="/scenarios/:name" element={<ScenarioDetailPage />} />
    </Routes>,
    { route: '/scenarios/73_easting' },
  )
}

describe('ScenarioDetailPage', () => {
  it('renders scenario name and era badge', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(MOCK_DETAIL), { status: 200 }),
    )
    renderDetail()
    await waitFor(() => {
      expect(screen.getByText('73 Easting')).toBeInTheDocument()
    })
    expect(screen.getByText('Modern')).toBeInTheDocument()
  })

  it('displays force table', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(MOCK_DETAIL), { status: 200 }),
    )
    renderDetail()
    await waitFor(() => {
      expect(screen.getByText('blue')).toBeInTheDocument()
    })
    expect(screen.getByText('red')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByText('5')).toBeInTheDocument()
  })

  it('shows config badges (EW present)', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(MOCK_DETAIL), { status: 200 }),
    )
    renderDetail()
    await waitFor(() => {
      expect(screen.getByText('Electronic Warfare')).toBeInTheDocument()
    })
  })

  it('shows terrain info', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(MOCK_DETAIL), { status: 200 }),
    )
    renderDetail()
    await waitFor(() => {
      expect(screen.getByText('desert')).toBeInTheDocument()
    })
  })

  it('shows documented outcomes table', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(MOCK_DETAIL), { status: 200 }),
    )
    renderDetail()
    await waitFor(() => {
      expect(screen.getByText('Blue casualties')).toBeInTheDocument()
    })
    expect(screen.getByText('Bourque 2001')).toBeInTheDocument()
  })

  it('shows Run This Scenario button', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(MOCK_DETAIL), { status: 200 }),
    )
    renderDetail()
    await waitFor(() => {
      expect(screen.getByText('Run This Scenario')).toBeInTheDocument()
    })
  })
})
