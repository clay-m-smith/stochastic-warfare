import { describe, it, expect, vi, beforeEach } from 'vitest'
import { apiGet, apiPost, apiDelete, ApiError } from '../../api/client'

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('apiGet', () => {
  it('returns parsed JSON on success', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ name: 'test' }), { status: 200 }),
    )
    const result = await apiGet<{ name: string }>('/api/test')
    expect(result).toEqual({ name: 'test' })
    expect(fetch).toHaveBeenCalledWith('/api/test')
  })

  it('throws ApiError with detail on failure', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Not found' }), { status: 404 }),
    )
    await expect(apiGet('/api/missing')).rejects.toThrow(ApiError)
  })

  it('includes detail message from response body', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Not found' }), { status: 404 }),
    )
    try {
      await apiGet('/api/missing')
    } catch (e) {
      expect((e as ApiError).detail).toBe('Not found')
    }
  })

  it('uses statusText when body has no detail', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('', { status: 500, statusText: 'Internal Server Error' }),
    )
    try {
      await apiGet('/api/fail')
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError)
      expect((e as ApiError).status).toBe(500)
    }
  })
})

describe('apiPost', () => {
  it('sends JSON body and returns response', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ run_id: 'abc' }), { status: 202 }),
    )
    const result = await apiPost<{ run_id: string }>('/api/runs', { scenario: 'test' })
    expect(result).toEqual({ run_id: 'abc' })
    const call = vi.mocked(fetch).mock.calls[0]!
    expect(call[0]).toBe('/api/runs')
    const init = call[1] as RequestInit
    expect(init.method).toBe('POST')
    expect(init.headers).toEqual({ 'Content-Type': 'application/json' })
  })

  it('throws ApiError on failure', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Bad request' }), { status: 400 }),
    )
    await expect(apiPost('/api/runs', {})).rejects.toThrow('Bad request')
  })
})

describe('apiDelete', () => {
  it('sends DELETE request', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(null, { status: 204 }))
    await apiDelete('/api/runs/abc')
    const call = vi.mocked(fetch).mock.calls[0]!
    expect((call[1] as RequestInit).method).toBe('DELETE')
  })

  it('throws on non-ok response', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Not found' }), { status: 404 }),
    )
    await expect(apiDelete('/api/runs/xyz')).rejects.toThrow(ApiError)
  })
})
