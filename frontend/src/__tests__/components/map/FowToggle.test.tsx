import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { TacticalMap } from '../../../components/map/TacticalMap'
import type { TerrainData, ReplayFrame } from '../../../types/map'

// Mock ResizeObserver
vi.stubGlobal('ResizeObserver', class {
  observe() {}
  unobserve() {}
  disconnect() {}
})

// Mock canvas
beforeEach(() => {
  vi.restoreAllMocks()
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

const FRAMES_NO_FOW: ReplayFrame[] = [
  {
    tick: 0,
    units: [
      { id: 'u1', side: 'blue', x: 100, y: 200, domain: 0, status: 0, heading: 90, type: 'tank' },
    ],
  },
]

const FRAMES_WITH_FOW: ReplayFrame[] = [
  {
    tick: 0,
    units: [
      { id: 'b1', side: 'blue', x: 100, y: 200, domain: 0, status: 0, heading: 90, type: 'tank' },
      { id: 'r1', side: 'red', x: 500, y: 500, domain: 0, status: 0, heading: 270, type: 'bmp' },
    ],
    detected: { blue: ['r1'], red: [] },
  },
]

describe('FOW Toggle', () => {
  it('renders FOW toggle checkbox', () => {
    render(<TacticalMap terrain={TERRAIN} frames={FRAMES_WITH_FOW} />)
    expect(screen.getByText('FOW')).toBeInTheDocument()
  })

  it('FOW toggle is disabled without detection data', () => {
    render(<TacticalMap terrain={TERRAIN} frames={FRAMES_NO_FOW} />)
    const fowLabel = screen.getByText('FOW')
    const checkbox = fowLabel.parentElement?.querySelector('input[type="checkbox"]')
    expect(checkbox).toBeDisabled()
  })

  it('FOW toggle is enabled with detection data', () => {
    render(<TacticalMap terrain={TERRAIN} frames={FRAMES_WITH_FOW} />)
    const fowLabel = screen.getByText('FOW')
    const checkbox = fowLabel.parentElement?.querySelector('input[type="checkbox"]')
    expect(checkbox).not.toBeDisabled()
  })

  it('shows side selector when FOW is active', () => {
    render(<TacticalMap terrain={TERRAIN} frames={FRAMES_WITH_FOW} />)
    const fowLabel = screen.getByText('FOW')
    const checkbox = fowLabel.parentElement?.querySelector('input[type="checkbox"]')
    fireEvent.click(checkbox!)
    expect(screen.getByLabelText('FOW side')).toBeInTheDocument()
  })

  it('hides side selector when FOW is inactive', () => {
    render(<TacticalMap terrain={TERRAIN} frames={FRAMES_WITH_FOW} />)
    expect(screen.queryByLabelText('FOW side')).not.toBeInTheDocument()
  })
})
