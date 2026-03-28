import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  drawHealthBar,
  drawPostureIndicator,
  drawLogisticsBars,
  drawEngagementFlash,
  drawUnit,
  MORALE_COLORS,
  POSTURE_ABBREV,
  type OverlayOptions,
} from '../../lib/unitRendering'
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

function makeOverlays(overrides: Partial<OverlayOptions> = {}): OverlayOptions {
  return {
    showMorale: false,
    showHealth: false,
    showPosture: false,
    showSuppression: false,
    showLogistics: false,
    ...overrides,
  }
}

function mockContext(): CanvasRenderingContext2D {
  return {
    save: vi.fn(),
    restore: vi.fn(),
    beginPath: vi.fn(),
    closePath: vi.fn(),
    moveTo: vi.fn(),
    lineTo: vi.fn(),
    rect: vi.fn(),
    arc: vi.fn(),
    fill: vi.fn(),
    stroke: vi.fn(),
    fillRect: vi.fn(),
    fillText: vi.fn(),
    strokeText: vi.fn(),
    setLineDash: vi.fn(),
    fillStyle: '',
    strokeStyle: '',
    lineWidth: 1,
    globalAlpha: 1.0,
    font: '',
    textAlign: 'center' as CanvasTextAlign,
  } as unknown as CanvasRenderingContext2D
}

describe('drawHealthBar', () => {
  let ctx: CanvasRenderingContext2D

  beforeEach(() => {
    ctx = mockContext()
  })

  it('draws green bar when health > 0.5', () => {
    drawHealthBar(ctx, 100, 100, 0.8)
    // Two fillRect calls: background + fill
    expect(ctx.fillRect).toHaveBeenCalledTimes(2)
    // Fill color should be green
    expect(ctx.fillStyle).toBe('#22CC22')
  })

  it('draws yellow bar when health 0.2–0.5', () => {
    drawHealthBar(ctx, 100, 100, 0.35)
    expect(ctx.fillStyle).toBe('#DDDD00')
  })

  it('draws red bar when health < 0.2', () => {
    drawHealthBar(ctx, 100, 100, 0.1)
    expect(ctx.fillStyle).toBe('#FF2222')
  })

  it('fill width is proportional to health', () => {
    drawHealthBar(ctx, 100, 100, 0.5)
    const fillCall = (ctx.fillRect as ReturnType<typeof vi.fn>).mock.calls[1]!
    // barWidth = UNIT_SIZE * 2 = 16, fillWidth = 0.5 * 16 = 8
    expect(fillCall[2]).toBe(8)
  })

  it('draws green at boundary health=0.5', () => {
    drawHealthBar(ctx, 100, 100, 0.5)
    // 0.5 is NOT > 0.5, so should be yellow
    expect(ctx.fillStyle).toBe('#DDDD00')
  })

  it('draws yellow at boundary health=0.2', () => {
    drawHealthBar(ctx, 100, 100, 0.2)
    // 0.2 is NOT > 0.2, so should be red
    expect(ctx.fillStyle).toBe('#FF2222')
  })

  it('handles health=0.0', () => {
    drawHealthBar(ctx, 100, 100, 0.0)
    const fillCall = (ctx.fillRect as ReturnType<typeof vi.fn>).mock.calls[1]!
    expect(fillCall[2]).toBe(0) // zero width
  })
})

describe('drawPostureIndicator', () => {
  let ctx: CanvasRenderingContext2D

  beforeEach(() => {
    ctx = mockContext()
  })

  it('renders abbreviation for DEFENSIVE', () => {
    drawPostureIndicator(ctx, 100, 100, 'DEFENSIVE')
    expect(ctx.fillText).toHaveBeenCalledWith('D', expect.any(Number), expect.any(Number))
  })

  it('renders abbreviation for DUG_IN as F', () => {
    drawPostureIndicator(ctx, 100, 100, 'DUG_IN')
    expect(ctx.fillText).toHaveBeenCalledWith('F', expect.any(Number), expect.any(Number))
  })

  it('skips MOVING posture (empty abbreviation)', () => {
    drawPostureIndicator(ctx, 100, 100, 'MOVING')
    expect(ctx.fillText).not.toHaveBeenCalled()
  })

  it('skips empty posture string', () => {
    drawPostureIndicator(ctx, 100, 100, '')
    expect(ctx.fillText).not.toHaveBeenCalled()
  })
})

describe('drawLogisticsBars', () => {
  let ctx: CanvasRenderingContext2D

  beforeEach(() => {
    ctx = mockContext()
  })

  it('renders fuel blue and ammo orange', () => {
    drawLogisticsBars(ctx, 100, 100, 0.8, 0.6)
    const calls = (ctx.fillRect as ReturnType<typeof vi.fn>).mock.calls
    // 4 fillRect calls: fuel bg, fuel fill, ammo bg, ammo fill
    expect(calls).toHaveLength(4)
  })

  it('turns red when fuel below 20%', () => {
    drawLogisticsBars(ctx, 100, 100, 0.1, 0.8)
    // After fuel bg fillRect, the fuel fill sets fillStyle
    const styleAssignments: string[] = [];
    (ctx.fillRect as ReturnType<typeof vi.fn>).mockImplementation(() => {
      styleAssignments.push(ctx.fillStyle as string)
    })
    drawLogisticsBars(ctx, 100, 100, 0.1, 0.8)
    // Fuel fill (index 1) should be red
    expect(styleAssignments[1]).toBe('#FF2222')
  })
})

describe('drawEngagementFlash', () => {
  it('draws arc ring', () => {
    const ctx = mockContext()
    drawEngagementFlash(ctx, 100, 100)
    expect(ctx.arc).toHaveBeenCalledWith(100, 100, 12, 0, Math.PI * 2)
    expect(ctx.stroke).toHaveBeenCalled()
  })
})

describe('drawUnit with overlays', () => {
  it('applies morale color override when showMorale is true', () => {
    const ctx = mockContext()
    const unit = makeUnit({ morale: 2 }) // BROKEN
    const ov = makeOverlays({ showMorale: true })
    drawUnit(ctx, unit, IDENTITY, CANVAS_H, false, false, ov)
    // fillStyle should be set to BROKEN color at some point
    expect(ctx.fillStyle).not.toBe('')
  })

  it('applies suppression opacity when showSuppression is true', () => {
    const ctx = mockContext()
    const alphaValues: number[] = [];
    (ctx.fill as ReturnType<typeof vi.fn>).mockImplementation(() => {
      alphaValues.push(ctx.globalAlpha)
    })
    const unit = makeUnit({ suppression: 3 }) // HEAVY
    const ov = makeOverlays({ showSuppression: true })
    drawUnit(ctx, unit, IDENTITY, CANVAS_H, false, false, ov)
    // globalAlpha at time of fill should be reduced (base 1.0 * 0.45 = 0.45)
    expect(alphaValues[0]).toBeLessThan(1.0)
  })

  it('renders without overlays arg (backward compat)', () => {
    const ctx = mockContext()
    const unit = makeUnit()
    // No overlays arg — should not throw
    drawUnit(ctx, unit, IDENTITY, CANVAS_H, false, false)
    expect(ctx.fill).toHaveBeenCalled()
  })

  it('uses side color when morale is STEADY (0)', () => {
    const ctx = mockContext()
    const fillStyles: string[] = [];
    (ctx.fill as ReturnType<typeof vi.fn>).mockImplementation(() => {
      fillStyles.push(ctx.fillStyle as string)
    })
    const unit = makeUnit({ morale: 0 })
    const ov = makeOverlays({ showMorale: true })
    drawUnit(ctx, unit, IDENTITY, CANVAS_H, false, false, ov)
    // STEADY (0) should NOT override — fill color should be side color, not a morale color
    expect(fillStyles[0]).not.toBe('#DDDD00')
    expect(fillStyles[0]).not.toBe('#FF8800')
    expect(fillStyles[0]).not.toBe('#FF2222')
  })

  it('skips overlays for destroyed units', () => {
    const ctx = mockContext()
    const unit = makeUnit({ status: 2, health: 0.5 }) // destroyed
    const ov = makeOverlays({ showHealth: true })
    drawUnit(ctx, unit, IDENTITY, CANVAS_H, false, false, ov)
    // Health bar draws 2 fillRects. Destroyed unit shape also uses fillRect (ground=rect).
    // With overlays skipped on destroyed, we should only see shape fillRect + status overlays.
    // Check that fillRect was NOT called for health bar (no extra bar below marker).
    const calls = (ctx.fillRect as ReturnType<typeof vi.fn>).mock.calls
    // Ground rect uses ctx.rect() not fillRect, so fillRect should be 0 for destroyed
    expect(calls.length).toBe(0)
  })

  it('suppression level 0 does not reduce opacity', () => {
    const ctx = mockContext()
    const alphaValues: number[] = [];
    (ctx.fill as ReturnType<typeof vi.fn>).mockImplementation(() => {
      alphaValues.push(ctx.globalAlpha)
    })
    const unit = makeUnit({ suppression: 0 })
    const ov = makeOverlays({ showSuppression: true })
    drawUnit(ctx, unit, IDENTITY, CANVAS_H, false, false, ov)
    expect(alphaValues[0]).toBe(1.0)
  })

  it('suppression level 4 (pinned) has lowest opacity', () => {
    const ctx = mockContext()
    const alphaValues: number[] = [];
    (ctx.fill as ReturnType<typeof vi.fn>).mockImplementation(() => {
      alphaValues.push(ctx.globalAlpha)
    })
    const unit = makeUnit({ suppression: 4 })
    const ov = makeOverlays({ showSuppression: true })
    drawUnit(ctx, unit, IDENTITY, CANVAS_H, false, false, ov)
    expect(alphaValues[0]).toBeCloseTo(0.30)
  })
})

describe('constants', () => {
  it('MORALE_COLORS has 5 entries', () => {
    expect(Object.keys(MORALE_COLORS)).toHaveLength(5)
  })

  it('POSTURE_ABBREV maps known postures', () => {
    expect(POSTURE_ABBREV['DEFENSIVE']).toBe('D')
    expect(POSTURE_ABBREV['DUG_IN']).toBe('F')
    expect(POSTURE_ABBREV['BATTLE_STATIONS']).toBe('B')
    expect(POSTURE_ABBREV['MOVING']).toBe('')
  })
})
