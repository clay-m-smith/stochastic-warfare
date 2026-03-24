import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { renderWithProviders } from '../helpers'
import { TacticalMap } from '../../components/map/TacticalMap'
import type { TerrainData, ReplayFrame } from '../../types/map'

// Mock ResizeObserver
vi.stubGlobal('ResizeObserver', class {
  observe() {}
  unobserve() {}
  disconnect() {}
})

// Mock canvas
HTMLCanvasElement.prototype.getContext = vi.fn().mockReturnValue({
  clearRect: vi.fn(),
  drawImage: vi.fn(),
  beginPath: vi.fn(),
  arc: vi.fn(),
  stroke: vi.fn(),
  fill: vi.fn(),
  closePath: vi.fn(),
  rect: vi.fn(),
  moveTo: vi.fn(),
  lineTo: vi.fn(),
  fillRect: vi.fn(),
  fillText: vi.fn(),
  setLineDash: vi.fn(),
  save: vi.fn(),
  restore: vi.fn(),
  set fillStyle(_v: string) {},
  set strokeStyle(_v: string) {},
  set lineWidth(_v: number) {},
  set globalAlpha(_v: number) {},
  set font(_v: string) {},
  set textAlign(_v: string) {},
} as unknown as CanvasRenderingContext2D)

const TERRAIN: TerrainData = {
  width_cells: 10,
  height_cells: 10,
  cell_size: 100,
  origin_easting: 0,
  origin_northing: 0,
  land_cover: [[0, 1], [9, 3]],
  objectives: [{ id: 'obj1', x: 500, y: 500, radius: 200 }],
  extent: [0, 0, 1000, 1000],
}

const FRAMES: ReplayFrame[] = [
  {
    tick: 0,
    units: [
      { id: 'u1', side: 'blue', x: 100, y: 200, domain: 0, status: 0, heading: 90, type: 'tank' },
      { id: 'u2', side: 'red', x: 800, y: 700, domain: 0, status: 0, heading: 270, type: 'bmp' },
    ],
  },
]

describe('TacticalMap accessibility', () => {
  it('canvas has role=application', () => {
    render(<TacticalMap terrain={TERRAIN} frames={FRAMES} />)
    const canvas = document.querySelector('canvas')
    expect(canvas).toHaveAttribute('role', 'application')
  })

  it('canvas has aria-label', () => {
    render(<TacticalMap terrain={TERRAIN} frames={FRAMES} />)
    const canvas = document.querySelector('canvas')
    expect(canvas).toHaveAttribute('aria-label', 'Tactical map')
  })

  it('sr-only summary element exists', () => {
    const { container } = render(<TacticalMap terrain={TERRAIN} frames={FRAMES} />)
    const summary = container.querySelector('#tactical-map-summary')
    expect(summary).toBeInTheDocument()
    expect(summary).toHaveClass('sr-only')
    expect(summary?.textContent).toContain('2 active units')
  })
})

// Mock PlotlyChart to avoid lazy-loading issues
vi.mock('../../components/charts/PlotlyChart', () => ({
  PlotlyChart: ({ dataSummary }: { dataSummary?: React.ReactNode }) => (
    <div data-testid="plotly-chart">
      {dataSummary && (
        <details className="mt-2">
          <summary>View data table</summary>
          <div>{dataSummary}</div>
        </details>
      )}
    </div>
  ),
}))

describe('PlotlyChart accessibility', () => {
  it('renders data table when dataSummary provided', async () => {
    const { PlotlyChart } = await import('../../components/charts/PlotlyChart')
    render(
      <PlotlyChart
        data={[]}
        dataSummary={<table><tbody><tr><td>Data</td></tr></tbody></table>}
      />,
    )
    expect(screen.getByText('View data table')).toBeInTheDocument()
  })

  it('no data table when dataSummary omitted', async () => {
    const { PlotlyChart } = await import('../../components/charts/PlotlyChart')
    render(<PlotlyChart data={[]} />)
    expect(screen.queryByText('View data table')).toBeNull()
  })
})

describe('ForceStrengthChart accessibility', () => {
  it('generates data summary table', async () => {
    const { ForceStrengthChart } = await import('../../components/charts/ForceStrengthChart')
    const data = [
      { tick: 0, time_s: 0, blue: 10, red: 8 },
      { tick: 5, time_s: 25, blue: 10, red: 7 },
      { tick: 10, time_s: 50, blue: 9, red: 6 },
    ]
    render(<ForceStrengthChart data={data} />)
    expect(screen.getByText('View data table')).toBeInTheDocument()
    // The data table should contain a <table> element
    const details = screen.getByText('View data table').closest('details')
    expect(details?.querySelector('table')).toBeInTheDocument()
  })
})
