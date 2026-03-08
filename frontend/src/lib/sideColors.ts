/**
 * Side-to-color mapping for scenarios using arbitrary side names
 * (e.g., "english", "french") alongside the standard "red"/"blue".
 *
 * Supports multi-faction scenarios (3+ sides) with a palette of
 * 8 distinct colors. Standard "blue"/"red" get fixed slots; all
 * other side names are assigned colors in encounter order.
 */

/** 8-color palette — distinguishable, colorblind-friendly */
const COLOR_PALETTE = [
  '#4477AA', // blue
  '#CC6677', // red/rose
  '#228B22', // green
  '#AA7744', // brown/tan
  '#AA44AA', // purple
  '#44AAAA', // teal
  '#DDAA33', // gold
  '#888888', // gray
] as const

/** Tailwind border classes indexed to palette */
const BORDER_PALETTE = [
  'border-l-4 border-l-blue-500',
  'border-l-4 border-l-red-500',
  'border-l-4 border-l-green-600',
  'border-l-4 border-l-amber-700',
  'border-l-4 border-l-purple-500',
  'border-l-4 border-l-teal-500',
  'border-l-4 border-l-yellow-500',
  'border-l-4 border-l-gray-500',
] as const

/** Fixed index assignments for standard and historical side names */
const FIXED_INDICES: Record<string, number> = {
  // Standard NATO sides
  blue: 0,
  red: 1,
  green: 2,
  neutral: 7,
  // Western / Allied factions → blue
  british: 0,
  english: 0,
  usn: 0,
  us: 0,
  coalition: 0,
  greek: 0,
  roman: 0,
  saxon: 2,
  // Eastern / Opposing factions → red/rose
  soviet: 1,
  ijn: 1,
  // Historical factions → distinct colors
  german: 3,         // brown/tan — feldgrau
  french: 5,         // teal
  franco_spanish: 5, // teal (Trafalgar)
  carthaginian: 4,   // purple — Tyrian purple
  persian: 6,        // gold
  norman: 6,         // gold
}

/** Track assignment order for dynamically-named sides */
const _assigned: Record<string, number> = {}
let _nextIndex = 0

/**
 * Reset side ordering — call when switching between runs/scenarios.
 */
export function resetSideOrder(): void {
  for (const key of Object.keys(_assigned)) {
    delete _assigned[key]
  }
  _nextIndex = 0
}

function resolveIndex(side: string): number {
  const lower = side.toLowerCase()
  if (lower in FIXED_INDICES) return FIXED_INDICES[lower]!
  if (lower in _assigned) return _assigned[lower]!

  // Find next available index (skip fixed ones)
  const fixedSet = new Set(Object.values(FIXED_INDICES))
  while (fixedSet.has(_nextIndex) && _nextIndex < COLOR_PALETTE.length) {
    _nextIndex++
  }
  const idx = _nextIndex < COLOR_PALETTE.length ? _nextIndex : COLOR_PALETTE.length - 1
  _assigned[lower] = idx
  _nextIndex++
  return idx
}

/**
 * Initialize colors for a set of sides, ensuring no two share the same color.
 * Call this when loading a new scenario/run to reset dynamic assignments
 * and resolve any collisions in fixed mappings.
 */
export function initSidesForScenario(sides: string[]): void {
  resetSideOrder()
  if (sides.length < 2) return

  // Check for collisions among fixed mappings
  const indexToSides = new Map<number, string[]>()
  for (const side of sides) {
    const idx = resolveIndex(side.toLowerCase())
    const existing = indexToSides.get(idx) ?? []
    existing.push(side.toLowerCase())
    indexToSides.set(idx, existing)
  }

  // Resolve collisions: keep first side at its index, bump others
  const usedIndices = new Set<number>()
  for (const [idx, group] of indexToSides) {
    usedIndices.add(idx)
    for (let i = 1; i < group.length; i++) {
      // Find nearest unused index
      let newIdx = -1
      for (let j = 0; j < COLOR_PALETTE.length; j++) {
        if (!usedIndices.has(j)) {
          newIdx = j
          break
        }
      }
      if (newIdx >= 0) {
        _assigned[group[i]!] = newIdx
        usedIndices.add(newIdx)
      }
    }
  }
}

/** Get hex color for a side name (for canvas/Plotly). */
export function getSideColor(side: string): string {
  return COLOR_PALETTE[resolveIndex(side)] ?? '#888888'
}

/** Get Tailwind border class for a side name (for cards). */
export function getSideBorderClass(side: string): string {
  return BORDER_PALETTE[resolveIndex(side)] ?? 'border-l-4 border-l-gray-500'
}

/** Capitalize side name for display. */
export function formatSideName(side: string): string {
  if (!side) return 'Unknown'
  return side.charAt(0).toUpperCase() + side.slice(1)
}

/**
 * SIDE_COLORS record for backward compatibility.
 * Uses a Proxy to dynamically resolve unknown side names.
 */
export const SIDE_COLORS: Record<string, string> = new Proxy(
  {
    blue: COLOR_PALETTE[0],
    red: COLOR_PALETTE[1],
    green: COLOR_PALETTE[2],
    neutral: COLOR_PALETTE[7],
  } as Record<string, string>,
  {
    get(target, prop: string) {
      if (prop in target) return target[prop]
      return getSideColor(prop)
    },
  },
)
