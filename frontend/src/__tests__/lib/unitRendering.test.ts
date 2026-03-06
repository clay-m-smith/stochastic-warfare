import { describe, it, expect } from 'vitest'
import { hitTestUnit, SIDE_COLORS } from '../../lib/unitRendering'
import type { MapUnitFrame, ViewportTransform } from '../../types/map'

const IDENTITY: ViewportTransform = { offsetX: 0, offsetY: 0, scale: 1 }
const CANVAS_H = 600

function makeUnit(overrides: Partial<MapUnitFrame> = {}): MapUnitFrame {
  return {
    id: 'u1',
    side: 'blue',
    x: 100,
    y: 100,
    domain: 0,
    status: 0,
    heading: 0,
    type: 'infantry',
    ...overrides,
  }
}

describe('hitTestUnit', () => {
  it('returns true when clicking on the unit', () => {
    const unit = makeUnit({ x: 100, y: 100 })
    // worldToScreen(100, 100, identity, 600) => sx=100, sy=500
    const result = hitTestUnit(100, 500, unit, IDENTITY, CANVAS_H)
    expect(result).toBe(true)
  })

  it('returns false when clicking far from the unit', () => {
    const unit = makeUnit({ x: 100, y: 100 })
    const result = hitTestUnit(300, 300, unit, IDENTITY, CANVAS_H)
    expect(result).toBe(false)
  })

  it('respects custom hit radius', () => {
    const unit = makeUnit({ x: 100, y: 100 })
    // At (115, 500), distance = 15 from unit at (100, 500)
    expect(hitTestUnit(115, 500, unit, IDENTITY, CANVAS_H, 10)).toBe(false)
    expect(hitTestUnit(115, 500, unit, IDENTITY, CANVAS_H, 20)).toBe(true)
  })
})

describe('SIDE_COLORS', () => {
  it('has blue and red colors', () => {
    expect(SIDE_COLORS.blue).toBeDefined()
    expect(SIDE_COLORS.red).toBeDefined()
  })
})
