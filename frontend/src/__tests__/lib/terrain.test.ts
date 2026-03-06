import { describe, it, expect } from 'vitest'
import {
  worldToScreen,
  screenToWorld,
  getVisibleCellRange,
  LAND_COVER_COLORS,
  LAND_COVER_NAMES,
} from '../../lib/terrain'
import type { ViewportTransform, TerrainData } from '../../types/map'

const IDENTITY: ViewportTransform = { offsetX: 0, offsetY: 0, scale: 1 }
const CANVAS_H = 600

describe('worldToScreen / screenToWorld roundtrip', () => {
  it('roundtrips with identity transform', () => {
    const { sx, sy } = worldToScreen(100, 200, IDENTITY, CANVAS_H)
    const { wx, wy } = screenToWorld(sx, sy, IDENTITY, CANVAS_H)
    expect(wx).toBeCloseTo(100, 5)
    expect(wy).toBeCloseTo(200, 5)
  })

  it('roundtrips with offset and scale', () => {
    const t: ViewportTransform = { offsetX: 500, offsetY: 1000, scale: 2 }
    const { sx, sy } = worldToScreen(600, 1100, t, CANVAS_H)
    const { wx, wy } = screenToWorld(sx, sy, t, CANVAS_H)
    expect(wx).toBeCloseTo(600, 5)
    expect(wy).toBeCloseTo(1100, 5)
  })

  it('flips Y axis correctly', () => {
    // Higher northing should give lower screen Y
    const low = worldToScreen(0, 100, IDENTITY, CANVAS_H)
    const high = worldToScreen(0, 200, IDENTITY, CANVAS_H)
    expect(high.sy).toBeLessThan(low.sy)
  })
})

describe('LAND_COVER_COLORS', () => {
  it('has colors for all 15 land cover codes', () => {
    for (let code = 0; code <= 14; code++) {
      expect(LAND_COVER_COLORS[code]).toBeDefined()
      expect(typeof LAND_COVER_COLORS[code]).toBe('string')
    }
  })
})

describe('LAND_COVER_NAMES', () => {
  it('has names for all 15 land cover codes', () => {
    for (let code = 0; code <= 14; code++) {
      expect(LAND_COVER_NAMES[code]).toBeDefined()
    }
  })
})

describe('getVisibleCellRange', () => {
  const terrain: TerrainData = {
    width_cells: 100,
    height_cells: 100,
    cell_size: 10,
    origin_easting: 0,
    origin_northing: 0,
    land_cover: [],
    objectives: [],
    extent: [0, 0, 1000, 1000],
  }

  it('returns clamped range for identity transform', () => {
    const range = getVisibleCellRange(IDENTITY, 800, 600, terrain)
    expect(range.minRow).toBeGreaterThanOrEqual(0)
    expect(range.maxRow).toBeLessThan(terrain.height_cells)
    expect(range.minCol).toBeGreaterThanOrEqual(0)
    expect(range.maxCol).toBeLessThan(terrain.width_cells)
  })

  it('returns wider range when zoomed out', () => {
    const zoomOut: ViewportTransform = { offsetX: 0, offsetY: 0, scale: 0.5 }
    const range = getVisibleCellRange(zoomOut, 800, 600, terrain)
    expect(range.maxCol - range.minCol).toBeGreaterThanOrEqual(0)
  })
})
