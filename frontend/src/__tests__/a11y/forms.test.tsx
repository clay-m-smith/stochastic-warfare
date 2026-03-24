import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { axe } from 'jest-axe'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { GeneralSection } from '../../pages/editor/GeneralSection'
import { RunConfigPage } from '../../pages/runs/RunConfigPage'
import { SearchInput } from '../../components/SearchInput'

function renderWithProviders(ui: React.ReactElement, route = '/') {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('GeneralSection accessibility', () => {
  const mockDispatch = vi.fn()
  const mockConfig = { name: 'Test', duration_hours: 4, era: 'modern', date: '2025-01-01' }

  beforeEach(() => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify([{ name: 'Modern', value: 'modern' }]), { status: 200 }),
    )
  })

  it('all inputs have associated labels', () => {
    renderWithProviders(<GeneralSection config={mockConfig} dispatch={mockDispatch} />)
    expect(screen.getByLabelText('Name')).toBeInTheDocument()
    expect(screen.getByLabelText('Duration (hours)')).toBeInTheDocument()
    expect(screen.getByLabelText('Era')).toBeInTheDocument()
    expect(screen.getByLabelText('Date')).toBeInTheDocument()
  })

  it('axe scan passes', async () => {
    const { container } = renderWithProviders(
      <GeneralSection config={mockConfig} dispatch={mockDispatch} />,
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})

describe('RunConfigPage accessibility', () => {
  beforeEach(() => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          name: 'test_scenario',
          config: { name: 'Test', era: 'modern' },
          force_summary: {},
        }),
        { status: 200 },
      ),
    )
  })

  it('required fields have aria-required', async () => {
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={['/runs/new?scenario=test_scenario']}>
          <Routes>
            <Route path="/runs/new" element={<RunConfigPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )
    await waitFor(() => {
      expect(screen.getByLabelText('Random Seed')).toBeInTheDocument()
    })
    expect(screen.getByLabelText('Random Seed')).toHaveAttribute('aria-required', 'true')
    expect(screen.getByLabelText('Max Ticks')).toHaveAttribute('aria-required', 'true')
  })

  it('required fields have required attribute', async () => {
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={['/runs/new?scenario=test_scenario']}>
          <Routes>
            <Route path="/runs/new" element={<RunConfigPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )
    await waitFor(() => {
      expect(screen.getByLabelText('Random Seed')).toBeInTheDocument()
    })
    expect(screen.getByLabelText('Random Seed')).toBeRequired()
    expect(screen.getByLabelText('Max Ticks')).toBeRequired()
  })
})

describe('ScenarioEditorPage accessibility', () => {
  beforeEach(() => {
    HTMLCanvasElement.prototype.getContext = vi.fn().mockReturnValue({
      fillRect: vi.fn(), clearRect: vi.fn(), beginPath: vi.fn(), arc: vi.fn(),
      stroke: vi.fn(), fill: vi.fn(), save: vi.fn(), restore: vi.fn(),
      rotate: vi.fn(), translate: vi.fn(), fillText: vi.fn(),
      set fillStyle(_v: string) {}, set strokeStyle(_v: string) {},
      set lineWidth(_v: number) {}, set font(_v: string) {}, set textAlign(_v: string) {},
    })
    Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } })
  })

  it('validation errors have role=alert', async () => {
    const { fireEvent } = await import('@testing-library/react')
    const scenarioData = {
      name: 'test_scenario',
      config: { name: 'Test', era: 'modern', duration_hours: 4, terrain: {}, sides: [] },
      force_summary: {},
    }
    const erasData = [{ name: 'Modern', value: 'modern' }]
    const healthData = { status: 'ok', version: '0.1.0', scenario_count: 1, unit_count: 1 }

    // Multiple concurrent fetches: scenario, eras, health, then validate
    vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
      const url = typeof input === 'string' ? input : (input as Request).url
      if (url.includes('/validate')) {
        return Promise.resolve(new Response(JSON.stringify({ valid: false, errors: ['Missing sides'] }), { status: 200 }))
      }
      if (url.includes('/eras')) {
        return Promise.resolve(new Response(JSON.stringify(erasData), { status: 200 }))
      }
      if (url.includes('/health')) {
        return Promise.resolve(new Response(JSON.stringify(healthData), { status: 200 }))
      }
      return Promise.resolve(new Response(JSON.stringify(scenarioData), { status: 200 }))
    })

    const { ScenarioEditorPage } = await import('../../pages/editor/ScenarioEditorPage')
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={['/scenarios/test_scenario/edit']}>
          <Routes>
            <Route path="/scenarios/:name/edit" element={<ScenarioEditorPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )

    await waitFor(() => {
      expect(screen.getByText('Validate')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Validate'))

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })
    expect(screen.getByRole('alert')).toHaveAttribute('aria-live', 'assertive')
  })
})

describe('SearchInput accessibility', () => {
  it('input has aria-label', () => {
    render(<SearchInput value="" onChange={vi.fn()} placeholder="Search..." />)
    expect(screen.getByLabelText('Search...')).toBeInTheDocument()
  })

  it('SVG icon is aria-hidden', () => {
    const { container } = render(<SearchInput value="" onChange={vi.fn()} />)
    const svg = container.querySelector('svg')
    expect(svg).toHaveAttribute('aria-hidden', 'true')
  })
})
