import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  fetchAnalyticsSummary,
  fetchCasualtyAnalytics,
  fetchEngagementAnalytics,
  fetchMoraleAnalytics,
  fetchSuppressionAnalytics,
} from '../../api/analytics'

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('fetchCasualtyAnalytics', () => {
  it('fetches casualties with default params', async () => {
    const resp = { groups: [{ label: 'm256', count: 3, side: 'red' }], total: 3 }
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(resp), { status: 200 }),
    )
    const result = await fetchCasualtyAnalytics('run1')
    expect(result).toEqual(resp)
    expect(fetch).toHaveBeenCalledWith('/api/runs/run1/analytics/casualties')
  })

  it('appends group_by and side query params', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ groups: [], total: 0 }), { status: 200 }),
    )
    await fetchCasualtyAnalytics('run1', 'side', 'blue')
    const url = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls[0]![0] as string
    expect(url).toContain('group_by=side')
    expect(url).toContain('side=blue')
  })
})

describe('fetchSuppressionAnalytics', () => {
  it('fetches suppression data', async () => {
    const resp = { peak_suppressed: 5, peak_tick: 10, rout_cascades: 1, timeline: [] }
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(resp), { status: 200 }),
    )
    const result = await fetchSuppressionAnalytics('run1')
    expect(result).toEqual(resp)
  })
})

describe('fetchMoraleAnalytics', () => {
  it('fetches morale data', async () => {
    const resp = { timeline: [{ tick: 1, steady: 5, shaken: 2, broken: 0, routed: 0, surrendered: 0 }] }
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(resp), { status: 200 }),
    )
    const result = await fetchMoraleAnalytics('run1')
    expect(result.timeline).toHaveLength(1)
  })
})

describe('fetchEngagementAnalytics', () => {
  it('fetches engagement data', async () => {
    const resp = { by_type: [{ type: 'DIRECT_FIRE', count: 10, hit_rate: 0.3 }], total: 10 }
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(resp), { status: 200 }),
    )
    const result = await fetchEngagementAnalytics('run1')
    expect(result.total).toBe(10)
  })
})

describe('fetchAnalyticsSummary', () => {
  it('fetches combined summary', async () => {
    const resp = {
      casualties: { groups: [], total: 0 },
      suppression: { peak_suppressed: 0, peak_tick: 0, rout_cascades: 0, timeline: [] },
      morale: { timeline: [] },
      engagements: { by_type: [], total: 0 },
    }
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(resp), { status: 200 }),
    )
    const result = await fetchAnalyticsSummary('run1')
    expect(result.casualties).toBeDefined()
    expect(result.engagements).toBeDefined()
  })
})
