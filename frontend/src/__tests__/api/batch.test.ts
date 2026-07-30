import { describe, it, expect, vi, beforeEach } from 'vitest'
import { submitBatch, fetchBatch } from '../../api/batch'

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('submitBatch', () => {
  it('posts batch request', async () => {
    const resp = { batch_id: 'b1', status: 'pending' }
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(resp), { status: 202 }),
    )
    const request = {
      scenario: 'test',
      num_iterations: 10,
      config_overrides: { hit_probability_modifier: 10.0 },
    }
    const result = await submitBatch(request)
    expect(result).toEqual(resp)
    expect(fetch).toHaveBeenCalledWith('/api/runs/batch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    })
  })
})

describe('fetchBatch', () => {
  it('fetches batch detail', async () => {
    const detail = { batch_id: 'b1', status: 'completed', metrics: {} }
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(detail), { status: 200 }),
    )
    const result = await fetchBatch('b1')
    expect(result).toEqual(detail)
    expect(fetch).toHaveBeenCalledWith('/api/runs/batch/b1')
  })
})
