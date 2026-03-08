import type { MapUnitFrame, ViewportTransform } from '../types/map'
import { worldToScreen } from './terrain'

export const SIDE_COLORS: Record<string, string> = {
  blue: '#4477AA',
  red: '#CC6677',
  green: '#228B22',
  neutral: '#999999',
}

const UNIT_SIZE = 8

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
): void {
  const { sx, sy } = worldToScreen(unit.x, unit.y, transform, canvasHeight)
  const color = SIDE_COLORS[unit.side] ?? SIDE_COLORS.neutral ?? '#999999'
  const size = UNIT_SIZE
  const destroyed = unit.status >= 2 // UnitStatus.DESTROYED = 2

  ctx2d.save()
  ctx2d.globalAlpha = destroyed ? 0.35 : 1.0
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
