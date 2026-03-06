import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { ScenarioEditorPage } from '../../pages/editor/ScenarioEditorPage'

const MOCK_SCENARIO = {
  name: 'test_scenario',
  config: {
    name: 'Test Scenario',
    date: '2025-01-01',
    duration_hours: 4,
    era: 'modern',
    terrain: { width_m: 5000, height_m: 5000, terrain_type: 'mixed' },
    sides: [
      { side: 'blue', units: [{ unit_type: 'm1a2_abrams', count: 2 }] },
      { side: 'red', units: [{ unit_type: 't72b3', count: 3 }] },
    ],
  },
  force_summary: {
    blue: { unit_count: 2, unit_types: ['m1a2_abrams'] },
    red: { unit_count: 3, unit_types: ['t72b3'] },
  },
}

function renderEditor() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(
    new Response(JSON.stringify(MOCK_SCENARIO), { status: 200 }),
  )
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/scenarios/test_scenario/edit']}>
        <Routes>
          <Route path="/scenarios/:name/edit" element={<ScenarioEditorPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.restoreAllMocks()
  // Mock canvas getContext
  HTMLCanvasElement.prototype.getContext = vi.fn().mockReturnValue({
    fillRect: vi.fn(),
    clearRect: vi.fn(),
    beginPath: vi.fn(),
    arc: vi.fn(),
    stroke: vi.fn(),
    fill: vi.fn(),
    save: vi.fn(),
    restore: vi.fn(),
    rotate: vi.fn(),
    translate: vi.fn(),
    fillText: vi.fn(),
    set fillStyle(_v: string) {},
    set strokeStyle(_v: string) {},
    set lineWidth(_v: number) {},
    set font(_v: string) {},
    set textAlign(_v: string) {},
  })
  // Mock clipboard
  Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } })
})

describe('ScenarioEditorPage', () => {
  it('renders editor sections after loading', async () => {
    renderEditor()
    await waitFor(() => {
      expect(screen.getByText('General')).toBeInTheDocument()
    })
    expect(screen.getByText('Terrain')).toBeInTheDocument()
    expect(screen.getByText('Weather')).toBeInTheDocument()
    expect(screen.getByText('Forces')).toBeInTheDocument()
  })

  it('shows action buttons', async () => {
    renderEditor()
    await waitFor(() => {
      expect(screen.getByText('Validate')).toBeInTheDocument()
    })
    expect(screen.getByText('Run This Config')).toBeInTheDocument()
    expect(screen.getByText('Download YAML')).toBeInTheDocument()
  })

  it('displays YAML preview', async () => {
    renderEditor()
    await waitFor(() => {
      expect(screen.getByText('YAML Preview')).toBeInTheDocument()
    })
  })

  it('displays terrain preview', async () => {
    renderEditor()
    await waitFor(() => {
      expect(screen.getByText('Terrain Preview')).toBeInTheDocument()
    })
  })
})
