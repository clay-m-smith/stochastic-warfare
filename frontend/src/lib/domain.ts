const DOMAIN_DISPLAY: Record<string, string> = {
  land: 'Land',
  air: 'Air',
  naval: 'Naval',
  submarine: 'Submarine',
  space: 'Space',
}

const DOMAIN_BADGE_COLOR: Record<string, string> = {
  land: 'bg-green-600 text-white',
  air: 'bg-sky-500 text-white',
  naval: 'bg-blue-700 text-white',
  submarine: 'bg-indigo-700 text-white',
  space: 'bg-gray-700 text-white',
}

export function domainDisplayName(domain: string): string {
  return DOMAIN_DISPLAY[domain] ?? domain
}

export function domainBadgeColor(domain: string): string {
  return DOMAIN_BADGE_COLOR[domain] ?? 'bg-gray-500 text-white'
}
