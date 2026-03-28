import type { MapUnitFrame, ViewportTransform } from '../types/map'
import { worldToScreen } from './terrain'
export { SIDE_COLORS } from './sideColors'
import { getSideColor } from './sideColors'

const UNIT_SIZE = 8

// --- Phase 94: overlay types and constants ---

export interface OverlayOptions {
  showMorale: boolean
  showHealth: boolean
  showPosture: boolean
  showSuppression: boolean
  showLogistics: boolean
}

export const MORALE_COLORS: Record<number, string | null> = {
  0: null,        // STEADY — use side color
  1: '#DDDD00',   // SHAKEN — yellow
  2: '#FF8800',   // BROKEN — orange
  3: '#FF2222',   // ROUTED — red
  4: '#999999',   // SURRENDERED — gray
}

const SUPPRESSION_OPACITY: Record<number, number> = {
  0: 1.0, 1: 0.85, 2: 0.65, 3: 0.45, 4: 0.30,
}

export const POSTURE_ABBREV: Record<string, string> = {
  MOVING: '', HALTED: 'H', DEFENSIVE: 'D', DUG_IN: 'F', FORTIFIED: 'F',
  ASSAULT: 'A', GROUNDED: 'G', INGRESSING: 'I', ON_STATION: 'S',
  RETURNING: 'R', ANCHORED: 'a', UNDERWAY: 'U', TRANSIT: 'T', BATTLE_STATIONS: 'B',
}

// --- Overlay drawing functions ---

export function drawHealthBar(
  ctx2d: CanvasRenderingContext2D,
  sx: number,
  sy: number,
  health: number,
): void {
  const barWidth = UNIT_SIZE * 2
  const barHeight = 2
  const barY = sy + UNIT_SIZE + 2

  // Background
  ctx2d.fillStyle = '#333333'
  ctx2d.fillRect(sx - UNIT_SIZE, barY, barWidth, barHeight)

  // Fill
  const fillWidth = health * barWidth
  if (health > 0.5) {
    ctx2d.fillStyle = '#22CC22'
  } else if (health > 0.2) {
    ctx2d.fillStyle = '#DDDD00'
  } else {
    ctx2d.fillStyle = '#FF2222'
  }
  ctx2d.fillRect(sx - UNIT_SIZE, barY, fillWidth, barHeight)
}

export function drawPostureIndicator(
  ctx2d: CanvasRenderingContext2D,
  sx: number,
  sy: number,
  posture: string,
): void {
  const abbrev = POSTURE_ABBREV[posture] ?? ''
  if (!abbrev) return

  ctx2d.font = 'bold 7px monospace'
  ctx2d.textAlign = 'left'
  // White outline for contrast on any terrain
  ctx2d.strokeStyle = '#FFFFFF'
  ctx2d.lineWidth = 2
  ctx2d.strokeText(abbrev, sx + UNIT_SIZE + 2, sy - UNIT_SIZE + 2)
  ctx2d.fillStyle = '#000000'
  ctx2d.fillText(abbrev, sx + UNIT_SIZE + 2, sy - UNIT_SIZE + 2)
}

export function drawLogisticsBars(
  ctx2d: CanvasRenderingContext2D,
  sx: number,
  sy: number,
  fuelPct: number,
  ammoPct: number,
): void {
  const barWidth = 2
  const maxHeight = UNIT_SIZE * 2
  const baseX = sx + UNIT_SIZE + 2
  const baseY = sy + UNIT_SIZE

  // Fuel bar (left)
  ctx2d.fillStyle = '#333333'
  ctx2d.fillRect(baseX, baseY - maxHeight, barWidth, maxHeight)
  const fuelHeight = fuelPct * maxHeight
  ctx2d.fillStyle = fuelPct < 0.2 ? '#FF2222' : '#4488FF'
  ctx2d.fillRect(baseX, baseY - fuelHeight, barWidth, fuelHeight)

  // Ammo bar (right)
  ctx2d.fillStyle = '#333333'
  ctx2d.fillRect(baseX + 3, baseY - maxHeight, barWidth, maxHeight)
  const ammoHeight = ammoPct * maxHeight
  ctx2d.fillStyle = ammoPct < 0.2 ? '#FF2222' : '#FF8800'
  ctx2d.fillRect(baseX + 3, baseY - ammoHeight, barWidth, ammoHeight)
}

export function drawEngagementFlash(
  ctx2d: CanvasRenderingContext2D,
  sx: number,
  sy: number,
): void {
  ctx2d.beginPath()
  ctx2d.arc(sx, sy, UNIT_SIZE + 4, 0, Math.PI * 2)
  ctx2d.strokeStyle = '#FFCC00'
  ctx2d.lineWidth = 2
  ctx2d.globalAlpha = 0.6
  ctx2d.stroke()
}

/**
 * Draw a unit on the canvas. Shape depends on domain:
 *  - 0 (ground): rectangle
 *  - 1 (air): triangle
 *  - 2 (naval/surface): diamond
 *  - 3+ (sub/other): circle
 */
export function drawUnit(
  ctx2d: CanvasRenderingContext2D,
  unit: MapUnitFrame,
  transform: ViewportTransform,
  canvasHeight: number,
  isSelected: boolean,
  showLabel: boolean,
  overlays?: OverlayOptions,
): void {
  const { sx, sy } = worldToScreen(unit.x, unit.y, transform, canvasHeight)
  let color = getSideColor(unit.side)
  const size = UNIT_SIZE
  const disabled = unit.status === 1 // UnitStatus.DISABLED = 1
  const destroyed = unit.status >= 2 // UnitStatus.DESTROYED = 2

  // Morale color override
  if (overlays?.showMorale && (unit.morale ?? 0) > 0) {
    const moraleColor = MORALE_COLORS[unit.morale!]
    if (moraleColor) color = moraleColor
  }

  ctx2d.save()

  // Base opacity (status-dependent)
  let alpha = destroyed ? 0.35 : disabled ? 0.55 : 1.0

  // Suppression opacity modifier
  if (overlays?.showSuppression && !destroyed) {
    alpha *= SUPPRESSION_OPACITY[unit.suppression ?? 0] ?? 1.0
  }

  ctx2d.globalAlpha = alpha
  ctx2d.fillStyle = color
  ctx2d.strokeStyle = isSelected ? '#FFD700' : '#000000'
  ctx2d.lineWidth = isSelected ? 2 : 1

  ctx2d.beginPath()
  switch (unit.domain) {
    case 1: // air — triangle
      ctx2d.moveTo(sx, sy - size)
      ctx2d.lineTo(sx - size, sy + size)
      ctx2d.lineTo(sx + size, sy + size)
      break
    case 2: // naval — diamond
      ctx2d.moveTo(sx, sy - size)
      ctx2d.lineTo(sx + size, sy)
      ctx2d.lineTo(sx, sy + size)
      ctx2d.lineTo(sx - size, sy)
      break
    case 0: // ground — rectangle
      ctx2d.rect(sx - size, sy - size, size * 2, size * 2)
      break
    default: // other — circle
      ctx2d.arc(sx, sy, size, 0, Math.PI * 2)
      break
  }
  ctx2d.closePath()
  ctx2d.fill()
  ctx2d.stroke()

  // Slash overlay for disabled units
  if (disabled) {
    ctx2d.globalAlpha = 0.8
    ctx2d.strokeStyle = '#FF8800'
    ctx2d.lineWidth = 2
    ctx2d.beginPath()
    ctx2d.moveTo(sx + size, sy - size)
    ctx2d.lineTo(sx - size, sy + size)
    ctx2d.stroke()
  }

  // X overlay for destroyed units
  if (destroyed) {
    ctx2d.strokeStyle = '#FF0000'
    ctx2d.lineWidth = 2
    ctx2d.beginPath()
    ctx2d.moveTo(sx - size, sy - size)
    ctx2d.lineTo(sx + size, sy + size)
    ctx2d.moveTo(sx + size, sy - size)
    ctx2d.lineTo(sx - size, sy + size)
    ctx2d.stroke()
  }

  // Label
  if (showLabel && !destroyed) {
    ctx2d.globalAlpha = 1.0
    ctx2d.fillStyle = '#000000'
    ctx2d.font = '10px monospace'
    ctx2d.textAlign = 'center'
    ctx2d.fillText(unit.type || unit.id, sx, sy - size - 3)
  }

  // Phase 94: overlays (health, posture, logistics)
  if (overlays && !destroyed) {
    ctx2d.globalAlpha = 1.0
    if (overlays.showHealth) drawHealthBar(ctx2d, sx, sy, unit.health ?? 1.0)
    if (overlays.showPosture) drawPostureIndicator(ctx2d, sx, sy, unit.posture ?? '')
    if (overlays.showLogistics) drawLogisticsBars(ctx2d, sx, sy, unit.fuel_pct ?? 1.0, unit.ammo_pct ?? 1.0)
  }

  // Engagement flash (always-on, no toggle)
  if (unit.engaged) {
    ctx2d.globalAlpha = 1.0
    drawEngagementFlash(ctx2d, sx, sy)
  }

  ctx2d.restore()
}

/**
 * Hit-test whether a screen click is close enough to a unit marker.
 */
export function hitTestUnit(
  screenX: number,
  screenY: number,
  unit: MapUnitFrame,
  transform: ViewportTransform,
  canvasHeight: number,
  hitRadius: number = 12,
): boolean {
  const { sx, sy } = worldToScreen(unit.x, unit.y, transform, canvasHeight)
  const dx = screenX - sx
  const dy = screenY - sy
  return dx * dx + dy * dy <= hitRadius * hitRadius
}
