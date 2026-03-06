import { useEffect, useRef } from 'react'
import { terrainTypeColor } from '../../lib/terrainTypeColors'

interface TerrainPreviewProps {
  config: Record<string, unknown>
}

export function TerrainPreview({ config }: TerrainPreviewProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const terrain = (config.terrain as Record<string, unknown>) ?? {}
  const width = (terrain.width_m as number) ?? 5000
  const height = (terrain.height_m as number) ?? 5000
  const terrainType = (terrain.terrain_type as string) ?? 'mixed'
  const objectives = (config.objectives as Record<string, unknown>[]) ?? []

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const cw = canvas.width
    const ch = canvas.height

    // Fill background with terrain color
    ctx.fillStyle = terrainTypeColor(terrainType)
    ctx.fillRect(0, 0, cw, ch)

    // Draw objectives
    const scaleX = cw / width
    const scaleY = ch / height
    const scale = Math.min(scaleX, scaleY)

    objectives.forEach((obj) => {
      const pos = obj.position as number[] | undefined
      if (!pos || pos.length < 2) return
      const ox = (pos[0] ?? 0) * scale
      const oy = ch - (pos[1] ?? 0) * scale // flip Y
      const radius = ((obj.radius_m as number) ?? 500) * scale
      ctx.beginPath()
      ctx.arc(ox, oy, Math.max(radius, 4), 0, Math.PI * 2)
      ctx.strokeStyle = '#FF4444'
      ctx.lineWidth = 2
      ctx.stroke()
      ctx.fillStyle = 'rgba(255, 68, 68, 0.15)'
      ctx.fill()
    })

    // Dimension labels
    ctx.fillStyle = '#333'
    ctx.font = '10px sans-serif'
    ctx.textAlign = 'center'
    ctx.fillText(`${width}m`, cw / 2, ch - 4)
    ctx.save()
    ctx.translate(12, ch / 2)
    ctx.rotate(-Math.PI / 2)
    ctx.fillText(`${height}m`, 0, 0)
    ctx.restore()
  }, [width, height, terrainType, objectives])

  return (
    <div className="rounded-lg border border-gray-200 bg-gray-50 p-3">
      <span className="mb-2 block text-xs font-medium text-gray-500">Terrain Preview</span>
      <canvas ref={canvasRef} width={300} height={200} className="w-full rounded" />
    </div>
  )
}
