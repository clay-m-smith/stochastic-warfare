import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fetchRun, deleteRun, fetchRunEvents, fetchRunNarrative } from '../../api/runs'

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('fetchRun', () => {
  it('returns run detail from /api/runs/:id', async () => {
    const detail = { run_id: 'r1', scenario_name: 'test', status: 'completed' }
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(detail), { status: 200 }),
    )
    const result = await fetchRun('r1')
    expect(result).toEqual(detail)
    expect(fetch).toHaveBeenCalledWith('/api/runs/r1')
  })

  it('encodes special characters in run id', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({}), { status: 200 }),
    )
    await fetchRun('run with space')
    expect(fetch).toHaveBeenCalledWith('/api/runs/run%20with%20space')
  })
})

describe('deleteRun', () => {
  it('sends DELETE to /api/runs/:id', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(null, { status: 204 }))
    await deleteRun('r1')
    expect(fetch).toHaveBeenCalledWith('/api/runs/r1', { method: 'DELETE' })
  })
})

describe('fetchRunEvents', () => {
  it('fetches events with pagination params', async () => {
    const resp = { events: [], total: 0, offset: 0, limit: 100 }
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(resp), { status: 200 }),
    )
    const result = await fetchRunEvents('r1', { offset: 10, limit: 50 })
    expect(result).toEqual(resp)
    expect(fetch).toHaveBeenCalledWith('/api/runs/r1/events?offset=10&limit=50')
  })

  it('fetches events without params', async () => {
    const resp = { events: [{ tick: 1, event_type: 'test', source: 's', data: {} }], total: 1, offset: 0, limit: 1000 }
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(resp), { status: 200 }),
    )
    const result = await fetchRunEvents('r1')
    expect(result.events).toHaveLength(1)
    expect(fetch).toHaveBeenCalledWith('/api/runs/r1/events')
  })

  it('includes event_type filter', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ events: [], total: 0, offset: 0, limit: 100 }), { status: 200 }),
    )
    await fetchRunEvents('r1', { event_type: 'HitEvent' })
    expect(fetch).toHaveBeenCalledWith('/api/runs/r1/events?event_type=HitEvent')
  })
})

describe('fetchRunNarrative', () => {
  it('fetches narrative with side and style', async () => {
    const resp = { narrative: 'The battle began...', tick_count: 100 }
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(resp), { status: 200 }),
    )
    const result = await fetchRunNarrative('r1', { side: 'blue', style: 'summary' })
    expect(result.narrative).toBe('The battle began...')
    expect(fetch).toHaveBeenCalledWith('/api/runs/r1/narrative?side=blue&style=summary')
  })

  it('fetches narrative without params', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ narrative: 'text', tick_count: 50 }), { status: 200 }),
    )
    await fetchRunNarrative('r1')
    expect(fetch).toHaveBeenCalledWith('/api/runs/r1/narrative')
  })
})
