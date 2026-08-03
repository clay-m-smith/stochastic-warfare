/** Maps terrain_type strings to display colors for the terrain preview. */
export const TERRAIN_TYPE_COLORS: Record<string, string> = {
  flat_desert: '#EDC9AF',
  open_ocean: '#87CEEB',
  hilly_defense: '#8B8682',
  trench_warfare: '#8B7355',
  open_field: '#90EE90',
}

export function terrainTypeColor(type: string): string {
  return TERRAIN_TYPE_COLORS[type] ?? '#D2B48C'
}
