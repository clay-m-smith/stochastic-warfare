import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { MapTab } from '../../pages/runs/tabs/MapTab'
import { renderWithProviders } from '../helpers'

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

const TERRAIN = {
  width_cells: 10,
  height_cells: 10,
  cell_size: 100,
  origin_easting: 0,
  origin_northing: 0,
  land_cover: [[0]],
  objectives: [],
  extent: [0, 0, 1000, 1000],
}

const FRAMES = {
  frames: [
    {
      tick: 0,
      units: [{ id: 'u1', side: 'blue', x: 100, y: 200, domain: 0, status: 0, heading: 0, type: 'tank' }],
    },
  ],
  total_frames: 1,
}

const EVENTS = { events: [], total: 0, offset: 0, limit: 100 }

beforeEach(() => {
  vi.restoreAllMocks()
  HTMLCanvasElement.prototype.getContext = vi.fn().mockReturnValue({
    clearRect: vi.fn(), drawImage: vi.fn(), beginPath: vi.fn(),
    arc: vi.fn(), stroke: vi.fn(), fill: vi.fn(), closePath: vi.fn(),
    rect: vi.fn(), moveTo: vi.fn(), lineTo: vi.fn(), fillRect: vi.fn(),
    fillText: vi.fn(), setLineDash: vi.fn(), save: vi.fn(), restore: vi.fn(),
    set fillStyle(_v: string) {}, set strokeStyle(_v: string) {},
    set lineWidth(_v: number) {}, set globalAlpha(_v: number) {},
    set font(_v: string) {}, set textAlign(_v: string) {},
  } as unknown as CanvasRenderingContext2D)
})

describe('MapTab', () => {
  it('shows loading spinner while fetching', () => {
    vi.spyOn(globalThis, 'fetch').mockReturnValue(new Promise(() => {}))
    renderWithProviders(<MapTab runId="r1" />)
    expect(document.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('shows empty state when no frames', async () => {
    let callCount = 0
    vi.spyOn(globalThis, 'fetch').mockImplementation(() => {
      callCount++
      if (callCount <= 1) {
        return Promise.resolve(new Response(JSON.stringify(TERRAIN), { status: 200 }))
      }
      if (callCount === 2) {
        return Promise.resolve(
          new Response(JSON.stringify({ frames: [], total_frames: 0 }), { status: 200 }),
        )
      }
      return Promise.resolve(new Response(JSON.stringify(EVENTS), { status: 200 }))
    })

    renderWithProviders(<MapTab runId="r1" />)
    await waitFor(() => {
      expect(screen.getByText('Map data not available for this run.')).toBeInTheDocument()
    })
  })

  it('renders tactical map when data available', async () => {
    let callCount = 0
    vi.spyOn(globalThis, 'fetch').mockImplementation(() => {
      callCount++
      if (callCount <= 1) {
        return Promise.resolve(new Response(JSON.stringify(TERRAIN), { status: 200 }))
      }
      if (callCount === 2) {
        return Promise.resolve(new Response(JSON.stringify(FRAMES), { status: 200 }))
      }
      return Promise.resolve(new Response(JSON.stringify(EVENTS), { status: 200 }))
    })

    renderWithProviders(<MapTab runId="r1" />)
    await waitFor(() => {
      const canvas = document.querySelector('canvas')
      expect(canvas).toBeInTheDocument()
    })
  })
})
