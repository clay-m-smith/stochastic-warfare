import type { EventItem } from '../types/api'
import type { ReplayFrame, EngagementArc } from '../types/map'

/**
 * Build engagement arcs by matching engagement events to the nearest frame
 * to get attacker/target positions.
 */
export function buildEngagementArcs(
  events: EventItem[],
  frames: ReplayFrame[],
): EngagementArc[] {
  if (frames.length === 0) return []

  const engagementEvents = events.filter(
    (e) => e.event_type === 'HitEvent' || e.event_type === 'MissEvent',
  )

  const arcs: EngagementArc[] = []

  for (const evt of engagementEvents) {
    const attackerId = evt.data.attacker_id as string | undefined
    const targetId = evt.data.target_id as string | undefined
    if (!attackerId || !targetId) continue

    // Find nearest frame
    const frame = findNearestFrame(frames, evt.tick)
    if (!frame) continue

    const attacker = frame.units.find((u) => u.id === attackerId)
    const target = frame.units.find((u) => u.id === targetId)
    if (!attacker || !target) continue

    arcs.push({
      attackerX: attacker.x,
      attackerY: attacker.y,
      targetX: target.x,
      targetY: target.y,
      hit: evt.event_type === 'HitEvent',
      tick: evt.tick,
    })
  }

  return arcs
}

function findNearestFrame(frames: ReplayFrame[], tick: number): ReplayFrame | null {
  let best: ReplayFrame | null = null
  let bestDist = Infinity

  for (const f of frames) {
    const dist = Math.abs(f.tick - tick)
    if (dist < bestDist) {
      bestDist = dist
      best = f
    }
    // Frames are sorted by tick, so once distance starts increasing we can break
    if (f.tick > tick && dist > bestDist) break
  }

  return best
}
