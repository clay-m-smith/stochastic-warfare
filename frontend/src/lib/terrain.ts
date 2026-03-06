import type { ViewportTransform, TerrainData } from '../types/map'

// LandCover codes -> CSS colors
// 0=OPEN, 1=GRASSLAND, 2=SHRUBLAND, 3-5=FOREST, 6-8=URBAN, 9=WATER,
// 10=WETLAND, 11-12=DESERT, 13=SNOW_ICE, 14=CULTIVATED
export const LAND_COVER_COLORS: Record<number, string> = {
  0: '#F5DEB3',   // OPEN - wheat
  1: '#90EE90',   // GRASSLAND - light green
  2: '#6B8E23',   // SHRUBLAND - olive drab
  3: '#228B22',   // FOREST_LIGHT - forest green
  4: '#006400',   // FOREST_MEDIUM - dark green
  5: '#004D00',   // FOREST_DENSE - very dark green
  6: '#D3D3D3',   // URBAN_LOW - light gray
  7: '#A9A9A9',   // URBAN_MEDIUM - dark gray
  8: '#696969',   // URBAN_HIGH - dim gray
  9: '#4169E1',   // WATER - royal blue
  10: '#5F9EA0',  // WETLAND - cadet blue
  11: '#EDC9AF',  // DESERT_SAND - desert sand
  12: '#C2B280',  // DESERT_ROCK - dark khaki
  13: '#FFFAFA',  // SNOW_ICE - snow
  14: '#BDB76B',  // CULTIVATED - dark khaki
}

export const LAND_COVER_NAMES: Record<number, string> = {
  0: 'Open',
  1: 'Grassland',
  2: 'Shrubland',
  3: 'Light Forest',
  4: 'Medium Forest',
  5: 'Dense Forest',
  6: 'Low Urban',
  7: 'Medium Urban',
  8: 'High Urban',
  9: 'Water',
  10: 'Wetland',
  11: 'Desert (Sand)',
  12: 'Desert (Rock)',
  13: 'Snow/Ice',
  14: 'Cultivated',
}

/**
 * Convert world ENU coordinates to screen pixel coordinates.
 * Canvas Y goes down, ENU northing goes up — hence the flip.
 */
export function worldToScreen(
  wx: number,
  wy: number,
  transform: ViewportTransform,
  canvasHeight: number,
): { sx: number; sy: number } {
  return {
    sx: (wx - transform.offsetX) * transform.scale,
    sy: canvasHeight - (wy - transform.offsetY) * transform.scale,
  }
}

/**
 * Convert screen pixel coordinates back to world ENU coordinates.
 */
export function screenToWorld(
  sx: number,
  sy: number,
  transform: ViewportTransform,
  canvasHeight: number,
): { wx: number; wy: number } {
  return {
    wx: sx / transform.scale + transform.offsetX,
    wy: (canvasHeight - sy) / transform.scale + transform.offsetY,
  }
}

/**
 * Compute the visible cell range for viewport culling.
 */
export function getVisibleCellRange(
  transform: ViewportTransform,
  canvasWidth: number,
  canvasHeight: number,
  terrain: TerrainData,
): { minRow: number; maxRow: number; minCol: number; maxCol: number } {
  const topLeft = screenToWorld(0, 0, transform, canvasHeight)
  const bottomRight = screenToWorld(canvasWidth, canvasHeight, transform, canvasHeight)

  const cs = terrain.cell_size
  const ox = terrain.origin_easting
  const oy = terrain.origin_northing

  // screenToWorld(0,0) gives top-left corner: min easting, max northing
  // screenToWorld(w,h) gives bottom-right corner: max easting, min northing
  const worldMinX = Math.min(topLeft.wx, bottomRight.wx)
  const worldMaxX = Math.max(topLeft.wx, bottomRight.wx)
  const worldMinY = Math.min(topLeft.wy, bottomRight.wy)
  const worldMaxY = Math.max(topLeft.wy, bottomRight.wy)

  const minCol = Math.max(0, Math.floor((worldMinX - ox) / cs))
  const maxCol = Math.min(terrain.width_cells - 1, Math.ceil((worldMaxX - ox) / cs))
  const minRow = Math.max(0, Math.floor((worldMinY - oy) / cs))
  const maxRow = Math.min(terrain.height_cells - 1, Math.ceil((worldMaxY - oy) / cs))

  return { minRow, maxRow, minCol, maxCol }
}
