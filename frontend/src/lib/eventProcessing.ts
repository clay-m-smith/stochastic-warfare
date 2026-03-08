import type { EventItem, RunResult, SideForces } from '../types/api'

/**
 * Compute seconds-per-tick from a RunResult.
 * Falls back to 5s if data is missing.
 */
export function tickToSeconds(result: RunResult | null): number {
  if (!result || !result.ticks_executed || result.ticks_executed === 0) return 5
  return result.duration_s / result.ticks_executed
}

/**
 * Format elapsed seconds as a human-readable time label.
 */
export function formatElapsed(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  return `${h}h ${m}m`
}

export interface ForceTimePoint {
  tick: number
  time_s: number
  [side: string]: number
}

export interface EngagementPoint {
  tick: number
  time_s: number
  range?: number
  hit: boolean
  attacker: string
  target: string
  weapon: string
}

export interface MoraleChange {
  tick: number
  time_s: number
  unit_id: string
  old_state: string
  new_state: string
}

export interface EventCountBin {
  tick: number
  time_s: number
  count: number
}

export const CASUALTY_EVENTS = new Set([
  'UnitDestroyedEvent',
  'UnitKilledEvent',
  'UnitDisabledEvent',
  'unit_destroyed',
  'unit_killed',
  'unit_disabled',
])

export const DESTRUCTION_EVENTS = new Set([
  'UnitDestroyedEvent',
  'UnitKilledEvent',
  'unit_destroyed',
  'unit_killed',
])

export const REINFORCEMENT_EVENTS = new Set([
  'ReinforcementArrivedEvent',
  'reinforcement_arrived',
])

export function buildForceTimeSeries(
  events: EventItem[],
  result: RunResult | null,
): ForceTimePoint[] {
  if (!result?.sides) return []

  const dt = tickToSeconds(result)
  const sides = Object.keys(result.sides)
  const activeCounts: Record<string, number> = {}
  for (const side of sides) {
    const sf = result.sides[side] as SideForces | undefined
    activeCounts[side] = sf ? sf.total : 0
  }

  const points: ForceTimePoint[] = [{ tick: 0, time_s: 0, ...activeCounts }]

  const sorted = [...events].sort((a, b) => a.tick - b.tick)
  for (const ev of sorted) {
    if (CASUALTY_EVENTS.has(ev.event_type)) {
      const side = (ev.data.side as string | undefined) ?? ''
      if (side && activeCounts[side] != null) {
        activeCounts[side] = Math.max(0, activeCounts[side]! - 1)
        points.push({ tick: ev.tick, time_s: ev.tick * dt, ...activeCounts })
      }
    } else if (REINFORCEMENT_EVENTS.has(ev.event_type)) {
      const side = (ev.data.side as string | undefined) ?? ''
      const count = (ev.data.unit_count as number | undefined) ?? 1
      if (side && activeCounts[side] != null) {
        activeCounts[side] = activeCounts[side]! + count
        points.push({ tick: ev.tick, time_s: ev.tick * dt, ...activeCounts })
      }
    }
  }

  return points
}

export const ENGAGEMENT_EVENTS = new Set([
  'EngagementEvent',
  'HitEvent',
  'engagement',
  'hit',
  'engagement_result',
])

export const MORALE_EVENTS = new Set([
  'MoraleStateChangeEvent',
  'morale_state_change',
  'morale_change',
])

export function buildEngagementData(events: EventItem[], result: RunResult | null): EngagementPoint[] {
  const dt = tickToSeconds(result)
  return events
    .filter((ev) => ENGAGEMENT_EVENTS.has(ev.event_type))
    .map((ev) => ({
      tick: ev.tick,
      time_s: ev.tick * dt,
      range: ev.data.range as number | undefined,
      hit: (ev.data.hit as boolean | undefined) ?? (ev.data.result as string) === 'hit',
      attacker: (ev.data.attacker as string | undefined) ?? (ev.data.source as string | undefined) ?? ev.source,
      target: (ev.data.target as string | undefined) ?? '',
      weapon: (ev.data.weapon as string | undefined) ?? (ev.data.weapon_type as string | undefined) ?? '',
    }))
}

export function buildMoraleTimeSeries(events: EventItem[], result: RunResult | null): MoraleChange[] {
  const dt = tickToSeconds(result)
  return events
    .filter((ev) => MORALE_EVENTS.has(ev.event_type))
    .map((ev) => ({
      tick: ev.tick,
      time_s: ev.tick * dt,
      unit_id: (ev.data.unit_id as string | undefined) ?? ev.source,
      old_state: (ev.data.old_state as string | undefined) ?? '',
      new_state: (ev.data.new_state as string | undefined) ?? '',
    }))
}

export function buildEventCounts(events: EventItem[], result: RunResult | null, binSize = 10): EventCountBin[] {
  if (events.length === 0) return []

  const dt = tickToSeconds(result)
  const maxTick = Math.max(...events.map((e) => e.tick))
  const numBins = Math.ceil((maxTick + 1) / binSize)
  const bins = new Array<number>(numBins).fill(0)

  for (const ev of events) {
    const idx = Math.min(Math.floor(ev.tick / binSize), numBins - 1)
    bins[idx]!++
  }

  return bins.map((count, i) => ({
    tick: i * binSize,
    time_s: i * binSize * dt,
    count,
  }))
}
