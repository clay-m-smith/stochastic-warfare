import { describe, it, expect } from 'vitest'
import { buildForceTimeSeries } from '../../lib/eventProcessing'
import type { EventItem, RunResult } from '../../types/api'

const makeEvent = (
  tick: number,
  event_type: string,
  data: Record<string, unknown> = {},
): EventItem => ({
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
    blue: { total: 10, active: 8, destroyed: 2 },
    red: { total: 8, active: 3, destroyed: 5 },
  },
}

describe('buildForceTimeSeries with reinforcements', () => {
  it('increments count on ReinforcementArrivedEvent', () => {
    const events = [
      makeEvent(10, 'ReinforcementArrivedEvent', { side: 'blue', unit_count: 3 }),
    ]
    const points = buildForceTimeSeries(events, MOCK_RESULT)
    expect(points).toHaveLength(2)
    expect(points[0]).toEqual({ tick: 0, time_s: 0, blue: 10, red: 8 })
    expect(points[1]).toEqual({ tick: 10, time_s: 1, blue: 13, red: 8 })
  })

  it('handles reinforcement_arrived snake_case variant', () => {
    const events = [
      makeEvent(5, 'reinforcement_arrived', { side: 'red', unit_count: 2 }),
    ]
    const points = buildForceTimeSeries(events, MOCK_RESULT)
    expect(points).toHaveLength(2)
    expect(points[1]).toEqual({ tick: 5, time_s: 0.5, blue: 10, red: 10 })
  })

  it('mixed reinforcements and destructions in correct order', () => {
    const events = [
      makeEvent(5, 'UnitDestroyedEvent', { side: 'blue' }),
      makeEvent(10, 'ReinforcementArrivedEvent', { side: 'blue', unit_count: 5 }),
      makeEvent(15, 'UnitDestroyedEvent', { side: 'blue' }),
    ]
    const points = buildForceTimeSeries(events, MOCK_RESULT)
    // tick 0:  blue=10, red=8
    // tick 5:  blue=9  (destroyed)
    // tick 10: blue=14 (reinforced +5)
    // tick 15: blue=13 (destroyed)
    expect(points).toHaveLength(4)
    expect(points[1]!.blue).toBe(9)
    expect(points[2]!.blue).toBe(14)
    expect(points[3]!.blue).toBe(13)
  })

  it('ignores reinforcement for unknown side', () => {
    const events = [
      makeEvent(5, 'ReinforcementArrivedEvent', { side: 'green', unit_count: 3 }),
    ]
    const points = buildForceTimeSeries(events, MOCK_RESULT)
    // Only the initial point
    expect(points).toHaveLength(1)
  })

  it('defaults unit_count to 1 when missing', () => {
    const events = [
      makeEvent(5, 'ReinforcementArrivedEvent', { side: 'red' }),
    ]
    const points = buildForceTimeSeries(events, MOCK_RESULT)
    expect(points).toHaveLength(2)
    expect(points[1]!.red).toBe(9)
  })
})
