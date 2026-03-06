import { describe, it, expect, vi, beforeEach } from 'vitest'
import { submitRunFromConfig, validateConfig } from '../../api/editor'

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('submitRunFromConfig', () => {
  it('POSTs to /api/runs/from-config', async () => {
    const response = { run_id: 'abc123', status: 'pending' }
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(response), { status: 202 }),
    )
    const result = await submitRunFromConfig({ config: { name: 'test' }, seed: 42 })
    expect(result).toEqual(response)
    expect(fetch).toHaveBeenCalledWith('/api/runs/from-config', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ config: { name: 'test' }, seed: 42 }),
    }))
  })
})

describe('validateConfig', () => {
  it('POSTs config to /api/scenarios/validate', async () => {
    const response = { valid: true, errors: [] }
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(response), { status: 200 }),
    )
    const result = await validateConfig({ name: 'test' })
    expect(result.valid).toBe(true)
    expect(fetch).toHaveBeenCalledWith('/api/scenarios/validate', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ config: { name: 'test' } }),
    }))
  })

  it('returns errors for invalid config', async () => {
    const response = { valid: false, errors: ['name is required'] }
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(response), { status: 200 }),
    )
    const result = await validateConfig({})
    expect(result.valid).toBe(false)
    expect(result.errors).toHaveLength(1)
  })
})
