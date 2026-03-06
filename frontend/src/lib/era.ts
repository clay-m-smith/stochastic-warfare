const ERA_DISPLAY: Record<string, string> = {
  modern: 'Modern',
  ww2: 'WW2',
  ww1: 'WW1',
  napoleonic: 'Napoleonic',
  ancient_medieval: 'Ancient & Medieval',
}

const ERA_BADGE_COLOR: Record<string, string> = {
  modern: 'bg-era-modern text-white',
  ww2: 'bg-era-ww2 text-gray-900',
  ww1: 'bg-era-ww1 text-gray-900',
  napoleonic: 'bg-era-napoleonic text-white',
  ancient_medieval: 'bg-era-ancient text-white',
}

const ERA_ORDER: Record<string, number> = {
  modern: 0,
  ww2: 1,
  ww1: 2,
  napoleonic: 3,
  ancient_medieval: 4,
}

export function eraDisplayName(era: string): string {
  return ERA_DISPLAY[era] ?? era
}

export function eraBadgeColor(era: string): string {
  return ERA_BADGE_COLOR[era] ?? 'bg-gray-500 text-white'
}

export function eraOrder(era: string): number {
  return ERA_ORDER[era] ?? 99
}
