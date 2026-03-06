/** Maps terrain_type strings to display colors for the terrain preview. */
export const TERRAIN_TYPE_COLORS: Record<string, string> = {
  flat_desert: '#EDC9AF',
  desert: '#C2B280',
  grassland: '#90EE90',
  forest: '#228B22',
  mixed: '#8FBC8F',
  urban: '#A9A9A9',
  coastal: '#87CEEB',
  mountain: '#8B8682',
  arctic: '#FFFAFA',
  jungle: '#006400',
}

export function terrainTypeColor(type: string): string {
  return TERRAIN_TYPE_COLORS[type] ?? '#D2B48C'
}
