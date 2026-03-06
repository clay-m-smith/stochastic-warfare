import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fetchRunTerrain, fetchRunFrames } from '../../api/map'

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('fetchRunTerrain', () => {
  it('fetches terrain from /api/runs/:id/terrain', async () => {
    const terrain = { width_cells: 10, height_cells: 10, cell_size: 100 }
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(terrain), { status: 200 }),
    )
    const result = await fetchRunTerrain('r1')
    expect(result).toEqual(terrain)
    expect(fetch).toHaveBeenCalledWith('/api/runs/r1/terrain')
  })

  it('encodes special characters in run id', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({}), { status: 200 }),
    )
    await fetchRunTerrain('run with space')
    expect(fetch).toHaveBeenCalledWith('/api/runs/run%20with%20space/terrain')
  })
})

describe('fetchRunFrames', () => {
  it('fetches frames from /api/runs/:id/frames', async () => {
    const frames = { frames: [], total_frames: 0 }
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(frames), { status: 200 }),
    )
    const result = await fetchRunFrames('r1')
    expect(result).toEqual(frames)
    expect(fetch).toHaveBeenCalledWith('/api/runs/r1/frames')
  })

  it('passes tick range params', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ frames: [], total_frames: 0 }), { status: 200 }),
    )
    await fetchRunFrames('r1', { start_tick: 10, end_tick: 50 })
    expect(fetch).toHaveBeenCalledWith('/api/runs/r1/frames?start_tick=10&end_tick=50')
  })

  it('omits unset params', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ frames: [], total_frames: 0 }), { status: 200 }),
    )
    await fetchRunFrames('r1', { start_tick: 5 })
    expect(fetch).toHaveBeenCalledWith('/api/runs/r1/frames?start_tick=5')
  })
})
