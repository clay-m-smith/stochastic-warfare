import { describe, it, expect } from 'vitest'
import {
  buildForceTimeSeries,
  buildEngagementData,
  buildMoraleTimeSeries,
  buildEventCounts,
} from '../../lib/eventProcessing'
import type { EventItem, RunResult } from '../../types/api'

const makeEvent = (tick: number, event_type: string, data: Record<string, unknown> = {}): EventItem => ({
  tick,
  event_type,
  source: 'test',
  data,
})

const MOCK_RESULT: RunResult = {
  scenario: 'test',
  seed: 42,
  ticks_executed: 100,
  duration_s: 10,
  victory: { status: 'decisive', winner: 'blue' },
  sides: {
    blue: { total: 10, active: 8, disabled: 0, destroyed: 2 },
    red: { total: 8, active: 3, disabled: 0, destroyed: 5 },
  },
}

describe('buildForceTimeSeries', () => {
  it('returns empty array when no result', () => {
    expect(buildForceTimeSeries([], null)).toEqual([])
  })

  it('starts with total counts at tick 0', () => {
    const points = buildForceTimeSeries([], MOCK_RESULT)
    expect(points).toHaveLength(1)
    expect(points[0]).toEqual({ tick: 0, time_s: 0, blue: 10, red: 8 })
  })

  it('decrements on destruction events', () => {
    const events = [
      makeEvent(5, 'UnitDestroyedEvent', { side: 'red' }),
      makeEvent(10, 'unit_destroyed', { side: 'red' }),
      makeEvent(15, 'UnitDestroyedEvent', { side: 'blue' }),
    ]
    const points = buildForceTimeSeries(events, MOCK_RESULT)
    expect(points).toHaveLength(4)
    expect(points[1]).toEqual({ tick: 5, time_s: 0.5, blue: 10, red: 7 })
    expect(points[2]).toEqual({ tick: 10, time_s: 1, blue: 10, red: 6 })
    expect(points[3]).toEqual({ tick: 15, time_s: 1.5, blue: 9, red: 6 })
  })

  it('does not go below zero', () => {
    const events = Array.from({ length: 20 }, (_, i) =>
      makeEvent(i, 'UnitDestroyedEvent', { side: 'red' }),
    )
    const points = buildForceTimeSeries(events, MOCK_RESULT)
    const lastPoint = points[points.length - 1]!
    expect(lastPoint.red).toBe(0)
  })

  it('ignores non-destruction events', () => {
    const events = [makeEvent(5, 'MoraleStateChangeEvent', { side: 'red' })]
    const points = buildForceTimeSeries(events, MOCK_RESULT)
    expect(points).toHaveLength(1)
  })
})

describe('buildEngagementData', () => {
  it('returns empty for no engagement events', () => {
    const events = [makeEvent(1, 'MoraleStateChangeEvent')]
    expect(buildEngagementData(events, MOCK_RESULT)).toEqual([])
  })

  it('extracts engagement data', () => {
    const events = [
      makeEvent(5, 'EngagementEvent', {
        range: 1500,
        hit: true,
        attacker: 'tank1',
        target: 'bmp1',
        weapon: 'M256',
      }),
      makeEvent(10, 'HitEvent', {
        range: 800,
        hit: false,
        attacker: 'inf1',
        target: 'tank2',
        weapon: 'RPG',
      }),
    ]
    const result = buildEngagementData(events, MOCK_RESULT)
    expect(result).toHaveLength(2)
    expect(result[0]).toEqual({
      tick: 5,
      time_s: 0.5,
      range: 1500,
      hit: true,
      attacker: 'tank1',
      target: 'bmp1',
      weapon: 'M256',
    })
    expect(result[1]!.hit).toBe(false)
  })

  it('handles missing fields gracefully', () => {
    const events = [makeEvent(1, 'EngagementEvent', {})]
    const result = buildEngagementData(events, MOCK_RESULT)
    expect(result).toHaveLength(1)
    expect(result[0]!.attacker).toBe('test')
    expect(result[0]!.target).toBe('')
  })
})

describe('buildMoraleTimeSeries', () => {
  it('returns empty for no morale events', () => {
    expect(buildMoraleTimeSeries([], MOCK_RESULT)).toEqual([])
  })

  it('extracts morale changes', () => {
    const events = [
      makeEvent(5, 'MoraleStateChangeEvent', {
        unit_id: 'u1',
        old_state: 'steady',
        new_state: 'shaken',
      }),
      makeEvent(10, 'morale_state_change', {
        unit_id: 'u2',
        old_state: 'shaken',
        new_state: 'broken',
      }),
    ]
    const result = buildMoraleTimeSeries(events, MOCK_RESULT)
    expect(result).toHaveLength(2)
    expect(result[0]).toEqual({ tick: 5, time_s: 0.5, unit_id: 'u1', old_state: 'steady', new_state: 'shaken' })
  })
})

describe('buildEventCounts', () => {
  it('returns empty for no events', () => {
    expect(buildEventCounts([], MOCK_RESULT)).toEqual([])
  })

  it('bins events correctly', () => {
    const events = [
      makeEvent(0, 'a'),
      makeEvent(3, 'b'),
      makeEvent(5, 'c'),
      makeEvent(10, 'd'),
      makeEvent(15, 'e'),
      makeEvent(19, 'f'),
    ]
    const result = buildEventCounts(events, MOCK_RESULT, 10)
    expect(result).toHaveLength(2)
    expect(result[0]).toEqual({ tick: 0, time_s: 0, count: 3 })
    expect(result[1]).toEqual({ tick: 10, time_s: 1, count: 3 })
  })

  it('uses custom bin size', () => {
    const events = [
      makeEvent(0, 'a'),
      makeEvent(4, 'b'),
      makeEvent(5, 'c'),
      makeEvent(9, 'd'),
    ]
    const result = buildEventCounts(events, MOCK_RESULT, 5)
    expect(result).toHaveLength(2)
    expect(result[0]).toEqual({ tick: 0, time_s: 0, count: 2 })
    expect(result[1]).toEqual({ tick: 5, time_s: 0.5, count: 2 })
  })
})
