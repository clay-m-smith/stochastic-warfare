import type { ReplayFrame, MapUnitFrame } from '../types/map'

const TARGET_MIN_FRAMES = 300

/**
 * When a run has few captured frames (e.g. strategic-tick campaigns),
 * generate interpolated intermediate frames for smooth playback.
 */
export function interpolateFrames(frames: ReplayFrame[]): ReplayFrame[] {
  if (frames.length >= TARGET_MIN_FRAMES || frames.length < 2) return frames

  const expansionFactor = Math.ceil(TARGET_MIN_FRAMES / (frames.length - 1))
  const result: ReplayFrame[] = []

  for (let i = 0; i < frames.length - 1; i++) {
    const f0 = frames[i]!
    const f1 = frames[i + 1]!

    for (let s = 0; s < expansionFactor; s++) {
      const t = s / expansionFactor
      result.push(lerpFrame(f0, f1, t))
    }
  }

  // Always include the final frame exactly
  result.push(frames[frames.length - 1]!)
  return result
}

function lerpFrame(a: ReplayFrame, b: ReplayFrame, t: number): ReplayFrame {
  // Build a lookup for the target frame's units
  const bMap = new Map<string, MapUnitFrame>()
  for (const u of b.units) {
    bMap.set(u.id, u)
  }

  const units: MapUnitFrame[] = a.units.map((au) => {
    const bu = bMap.get(au.id)
    if (!bu) return au

    // Use destination status if unit becomes destroyed partway through
    const status = t > 0.5 ? bu.status : au.status

    return {
      ...au,
      x: au.x + (bu.x - au.x) * t,
      y: au.y + (bu.y - au.y) * t,
      heading: bu.heading, // snap heading
      status,
    }
  })

  // Include units that appear only in frame b (reinforcements mid-interval)
  if (t > 0.5) {
    for (const bu of b.units) {
      if (!a.units.some((au) => au.id === bu.id)) {
        units.push(bu)
      }
    }
  }

  return {
    tick: Math.round(a.tick + (b.tick - a.tick) * t),
    units,
    detected: t > 0.5 ? b.detected : a.detected,
  }
}
