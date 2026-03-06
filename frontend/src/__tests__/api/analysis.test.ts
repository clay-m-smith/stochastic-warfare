import { describe, it, expect, vi, beforeEach } from 'vitest'
import { runCompare, runSweep } from '../../api/analysis'

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('runCompare', () => {
  it('posts compare request', async () => {
    const resp = { a: { kills: 5 }, b: { kills: 3 } }
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(resp), { status: 200 }),
    )
    const result = await runCompare({ scenario: 'test', label_a: 'A', label_b: 'B' })
    expect(result).toEqual(resp)
    expect(fetch).toHaveBeenCalledWith('/api/analysis/compare', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scenario: 'test', label_a: 'A', label_b: 'B' }),
    })
  })
})

describe('runSweep', () => {
  it('posts sweep request', async () => {
    const resp = { '100': { mean: 5, std: 1 }, '200': { mean: 8, std: 2 } }
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(resp), { status: 200 }),
    )
    const result = await runSweep({
      scenario: 'test',
      parameter_name: 'range',
      values: [100, 200],
    })
    expect(result).toEqual(resp)
  })
})
