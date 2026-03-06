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
  {
    tick: 10,
    units: [
      { id: 'u1', side: 'blue', x: 110, y: 210, domain: 0, status: 0, heading: 90, type: 'tank' },
      { id: 'u2', side: 'red', x: 790, y: 690, domain: 0, status: 3, heading: 270, type: 'bmp' },
    ],
  },
]

beforeEach(() => {
  vi.restoreAllMocks()
  // Re-mock canvas after restore
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

describe('TacticalMap', () => {
  it('renders canvas element', () => {
    render(<TacticalMap terrain={TERRAIN} frames={FRAMES} />)
    const canvas = document.querySelector('canvas')
    expect(canvas).toBeInTheDocument()
  })

  it('renders playback controls', () => {
    render(<TacticalMap terrain={TERRAIN} frames={FRAMES} />)
    expect(screen.getByLabelText('Play')).toBeInTheDocument()
    expect(screen.getByLabelText('Timeline scrubber')).toBeInTheDocument()
  })

  it('renders map controls', () => {
    render(<TacticalMap terrain={TERRAIN} frames={FRAMES} />)
    expect(screen.getByText('Labels')).toBeInTheDocument()
    expect(screen.getByText('Destroyed')).toBeInTheDocument()
    expect(screen.getByText('Fit')).toBeInTheDocument()
  })

  it('renders legend', () => {
    render(<TacticalMap terrain={TERRAIN} frames={FRAMES} />)
    expect(screen.getByText('Terrain')).toBeInTheDocument()
    expect(screen.getByText('Sides')).toBeInTheDocument()
  })

  it('shows frame count in playback', () => {
    render(<TacticalMap terrain={TERRAIN} frames={FRAMES} />)
    expect(screen.getByText(/Frame 1\/2/)).toBeInTheDocument()
  })
})
