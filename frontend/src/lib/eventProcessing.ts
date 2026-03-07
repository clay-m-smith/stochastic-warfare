import type { EventItem, RunResult, SideForces } from '../types/api'

export interface ForceTimePoint {
  tick: number
  [side: string]: number
}

export interface EngagementPoint {
  tick: number
  range?: number
  hit: boolean
  attacker: string
  target: string
  weapon: string
}

export interface MoraleChange {
  tick: number
  unit_id: string
  old_state: string
  new_state: string
}

export interface EventCountBin {
  tick: number
  count: number
}

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

  const sides = Object.keys(result.sides)
  const activeCounts: Record<string, number> = {}
  for (const side of sides) {
    const sf = result.sides[side] as SideForces | undefined
    activeCounts[side] = sf ? sf.total : 0
  }

  const points: ForceTimePoint[] = [{ tick: 0, ...activeCounts }]

  const sorted = [...events].sort((a, b) => a.tick - b.tick)
  for (const ev of sorted) {
    if (DESTRUCTION_EVENTS.has(ev.event_type)) {
      const side = (ev.data.side as string | undefined) ?? ''
      if (side && activeCounts[side] != null) {
        activeCounts[side] = Math.max(0, activeCounts[side]! - 1)
        points.push({ tick: ev.tick, ...activeCounts })
      }
    } else if (REINFORCEMENT_EVENTS.has(ev.event_type)) {
      const side = (ev.data.side as string | undefined) ?? ''
      const count = (ev.data.unit_count as number | undefined) ?? 1
      if (side && activeCounts[side] != null) {
        activeCounts[side] = activeCounts[side]! + count
        points.push({ tick: ev.tick, ...activeCounts })
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

export function buildEngagementData(events: EventItem[]): EngagementPoint[] {
  return events
    .filter((ev) => ENGAGEMENT_EVENTS.has(ev.event_type))
    .map((ev) => ({
      tick: ev.tick,
      range: ev.data.range as number | undefined,
      hit: (ev.data.hit as boolean | undefined) ?? (ev.data.result as string) === 'hit',
      attacker: (ev.data.attacker as string | undefined) ?? (ev.data.source as string | undefined) ?? ev.source,
      target: (ev.data.target as string | undefined) ?? '',
      weapon: (ev.data.weapon as string | undefined) ?? (ev.data.weapon_type as string | undefined) ?? '',
    }))
}

export function buildMoraleTimeSeries(events: EventItem[]): MoraleChange[] {
  return events
    .filter((ev) => MORALE_EVENTS.has(ev.event_type))
    .map((ev) => ({
      tick: ev.tick,
      unit_id: (ev.data.unit_id as string | undefined) ?? ev.source,
      old_state: (ev.data.old_state as string | undefined) ?? '',
      new_state: (ev.data.new_state as string | undefined) ?? '',
    }))
}

export function buildEventCounts(events: EventItem[], binSize = 10): EventCountBin[] {
  if (events.length === 0) return []

  const maxTick = Math.max(...events.map((e) => e.tick))
  const numBins = Math.ceil((maxTick + 1) / binSize)
  const bins = new Array<number>(numBins).fill(0)

  for (const ev of events) {
    const idx = Math.min(Math.floor(ev.tick / binSize), numBins - 1)
    bins[idx]!++
  }

  return bins.map((count, i) => ({
    tick: i * binSize,
    count,
  }))
}
