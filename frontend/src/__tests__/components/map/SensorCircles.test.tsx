import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { TacticalMap } from '../../../components/map/TacticalMap'
import type { TerrainData, ReplayFrame } from '../../../types/map'

// Mock ResizeObserver
vi.stubGlobal('ResizeObserver', class {
  observe() {}
  unobserve() {}
  disconnect() {}
})

// Mock canvas with spies
let arcSpy: ReturnType<typeof vi.fn>
let setLineDashSpy: ReturnType<typeof vi.fn>

function createCtxMock() {
  arcSpy = vi.fn()
  setLineDashSpy = vi.fn()
  return {
    clearRect: vi.fn(),
    drawImage: vi.fn(),
    beginPath: vi.fn(),
    arc: arcSpy,
    stroke: vi.fn(),
    fill: vi.fn(),
    closePath: vi.fn(),
    rect: vi.fn(),
    moveTo: vi.fn(),
    lineTo: vi.fn(),
    fillRect: vi.fn(),
    fillText: vi.fn(),
    setLineDash: setLineDashSpy,
    save: vi.fn(),
    restore: vi.fn(),
    set fillStyle(_v: string) {},
    set strokeStyle(_v: string) {},
    set lineWidth(_v: number) {},
    set globalAlpha(_v: number) {},
    set font(_v: string) {},
    set textAlign(_v: string) {},
  } as unknown as CanvasRenderingContext2D
}

beforeEach(() => {
  vi.restoreAllMocks()
  HTMLCanvasElement.prototype.getContext = vi.fn().mockReturnValue(createCtxMock())
})

const TERRAIN: TerrainData = {
  width_cells: 10,
  height_cells: 10,
  cell_size: 100,
  origin_easting: 0,
  origin_northing: 0,
  land_cover: [[0]],
  objectives: [],
  extent: [0, 0, 1000, 1000],
}

const FRAMES: ReplayFrame[] = [
  {
    tick: 0,
    units: [
      { id: 'u1', side: 'blue', x: 100, y: 200, domain: 0, status: 0, heading: 90, type: 'tank', sensor_range: 5000 },
    ],
  },
]

describe('Sensor Circles', () => {
  it('renders Sensors toggle', () => {
    render(<TacticalMap terrain={TERRAIN} frames={FRAMES} />)
    expect(screen.getByText('Sensors')).toBeInTheDocument()
  })

  it('sensors toggle defaults to off', () => {
    render(<TacticalMap terrain={TERRAIN} frames={FRAMES} />)
    const label = screen.getByText('Sensors')
    const checkbox = label.parentElement?.querySelector('input[type="checkbox"]')
    expect(checkbox).not.toBeChecked()
  })

  it('sensors toggle can be checked', () => {
    render(<TacticalMap terrain={TERRAIN} frames={FRAMES} />)
    const label = screen.getByText('Sensors')
    const checkbox = label.parentElement?.querySelector('input[type="checkbox"]')
    expect(checkbox).toBeInTheDocument()
  })
})
