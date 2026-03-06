import { describe, it, expect } from 'vitest'
import { buildEngagementArcs } from '../../lib/engagementProcessing'
import type { EventItem } from '../../types/api'
import type { ReplayFrame } from '../../types/map'

describe('buildEngagementArcs', () => {
  const frames: ReplayFrame[] = [
    {
      tick: 0,
      units: [
        { id: 'a1', side: 'blue', x: 100, y: 200, domain: 0, status: 0, heading: 0, type: 'tank' },
        { id: 't1', side: 'red', x: 500, y: 600, domain: 0, status: 0, heading: 180, type: 'bmp' },
      ],
    },
    {
      tick: 10,
      units: [
        { id: 'a1', side: 'blue', x: 110, y: 210, domain: 0, status: 0, heading: 0, type: 'tank' },
        { id: 't1', side: 'red', x: 490, y: 590, domain: 0, status: 0, heading: 180, type: 'bmp' },
      ],
    },
  ]

  it('builds arcs from hit events', () => {
    const events: EventItem[] = [
      {
        tick: 5,
        event_type: 'HitEvent',
        source: 'combat',
        data: { attacker_id: 'a1', target_id: 't1' },
      },
    ]

    const arcs = buildEngagementArcs(events, frames)
    expect(arcs).toHaveLength(1)
    expect(arcs[0]!.hit).toBe(true)
    expect(arcs[0]!.tick).toBe(5)
    // Should use nearest frame (tick 0, closer to tick 5 than tick 10)
    expect(arcs[0]!.attackerX).toBe(100)
    expect(arcs[0]!.targetX).toBe(500)
  })

  it('builds arcs from miss events', () => {
    const events: EventItem[] = [
      {
        tick: 5,
        event_type: 'MissEvent',
        source: 'combat',
        data: { attacker_id: 'a1', target_id: 't1' },
      },
    ]

    const arcs = buildEngagementArcs(events, frames)
    expect(arcs).toHaveLength(1)
    expect(arcs[0]!.hit).toBe(false)
  })

  it('returns empty array with no frames', () => {
    const events: EventItem[] = [
      { tick: 5, event_type: 'HitEvent', source: 'combat', data: { attacker_id: 'a1', target_id: 't1' } },
    ]
    expect(buildEngagementArcs(events, [])).toEqual([])
  })

  it('skips events without attacker/target ids', () => {
    const events: EventItem[] = [
      { tick: 5, event_type: 'HitEvent', source: 'combat', data: {} },
    ]
    expect(buildEngagementArcs(events, frames)).toEqual([])
  })

  it('ignores non-engagement events', () => {
    const events: EventItem[] = [
      { tick: 5, event_type: 'MoveEvent', source: 'movement', data: { unit_id: 'a1' } },
    ]
    expect(buildEngagementArcs(events, frames)).toEqual([])
  })
})
