import { useCallback, useEffect, useRef, useState } from 'react'
import type { MapUnitFrame, ReplayFrame, TerrainData, EngagementArc } from '../../types/map'
import { useViewportControls } from './useViewportControls'
import { LAND_COVER_COLORS, worldToScreen, screenToWorld, getVisibleCellRange } from '../../lib/terrain'
import { drawUnit, hitTestUnit, SIDE_COLORS } from '../../lib/unitRendering'
import { MapControls } from './MapControls'
import { MapLegend } from './MapLegend'
import { PlaybackControls } from './PlaybackControls'
import { UnitDetailSidebar } from './UnitDetailSidebar'
import { usePlayback } from '../../hooks/usePlayback'

interface TacticalMapProps {
  terrain: TerrainData
  frames: ReplayFrame[]
  engagementArcs?: EngagementArc[]
  onTickChange?: (tick: number) => void
}

export function TacticalMap({ terrain, frames, engagementArcs = [], onTickChange }: TacticalMapProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const terrainCanvasRef = useRef<HTMLCanvasElement | null>(null)
  const containerRef = useRef<HTMLDivElement | null>(null)
  const [canvasSize, setCanvasSize] = useState({ width: 800, height: 600 })
  const [mouseWorld, setMouseWorld] = useState<{ x: number; y: number } | null>(null)
  const [selectedUnit, setSelectedUnit] = useState<MapUnitFrame | null>(null)
  const [showLabels, setShowLabels] = useState(false)
  const [showDestroyed, setShowDestroyed] = useState(true)
  const [showEngagements, setShowEngagements] = useState(true)
  const [showTrails, setShowTrails] = useState(false)
  const terrainVersionRef = useRef(0)
  const lastTerrainDrawRef = useRef<string>('')

  const {
    transform,
    onWheel,
    onMouseDown,
    onMouseMove: viewportMouseMove,
    onMouseUp,
    fitToExtent,
  } = useViewportControls()

  const {
    currentFrame,
    isPlaying,
    speed,
    play,
    pause,
    stepForward,
    stepBackward,
    seekTo,
    setSpeed,
    speedOptions,
  } = usePlayback(frames.length)

  const currentFrameData = frames[currentFrame] ?? null

  // Notify parent of tick changes
  useEffect(() => {
    if (currentFrameData && onTickChange) {
      onTickChange(currentFrameData.tick)
    }
  }, [currentFrameData, onTickChange])

  // ResizeObserver for responsive canvas
  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect
        if (width > 0 && height > 0) {
          setCanvasSize({ width: Math.floor(width), height: Math.floor(height) })
        }
      }
    })
    observer.observe(container)
    return () => observer.disconnect()
  }, [])

  // Auto-fit on first load
  const hasFitted = useRef(false)
  useEffect(() => {
    if (!hasFitted.current && terrain.extent.length >= 4 && canvasSize.width > 0) {
      fitToExtent(terrain.extent, canvasSize.width, canvasSize.height)
      hasFitted.current = true
    }
  }, [terrain.extent, canvasSize, fitToExtent])

  // Render terrain to off-screen canvas (only when zoom/pan changes)
  useEffect(() => {
    const key = `${transform.offsetX},${transform.offsetY},${transform.scale},${canvasSize.width},${canvasSize.height}`
    if (key === lastTerrainDrawRef.current) return
    lastTerrainDrawRef.current = key

    if (!terrainCanvasRef.current) {
      terrainCanvasRef.current = document.createElement('canvas')
    }
    const tc = terrainCanvasRef.current
    tc.width = canvasSize.width
    tc.height = canvasSize.height
    const tctx = tc.getContext('2d')
    if (!tctx) return

    tctx.clearRect(0, 0, tc.width, tc.height)

    if (terrain.land_cover.length > 0) {
      const { minRow, maxRow, minCol, maxCol } = getVisibleCellRange(
        transform, canvasSize.width, canvasSize.height, terrain,
      )
      const cs = terrain.cell_size
      const ox = terrain.origin_easting
      const oy = terrain.origin_northing

      for (let row = minRow; row <= maxRow; row++) {
        for (let col = minCol; col <= maxCol; col++) {
          const code = terrain.land_cover[row]?.[col] ?? 0
          const wx = ox + col * cs
          const wy = oy + row * cs
          const tl = worldToScreen(wx, wy + cs, transform, canvasSize.height)
          const br = worldToScreen(wx + cs, wy, transform, canvasSize.height)
          tctx.fillStyle = LAND_COVER_COLORS[code] ?? '#F5DEB3'
          tctx.fillRect(tl.sx, tl.sy, br.sx - tl.sx, br.sy - tl.sy)
        }
      }
    } else {
      // No terrain data — fill with neutral background
      tctx.fillStyle = '#E8E0D0'
      tctx.fillRect(0, 0, tc.width, tc.height)
    }

    terrainVersionRef.current++
  }, [transform, canvasSize, terrain])

  // Main render loop
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx2d = canvas.getContext('2d')
    if (!ctx2d) return

    ctx2d.clearRect(0, 0, canvas.width, canvas.height)

    // Blit terrain
    if (terrainCanvasRef.current) {
      ctx2d.drawImage(terrainCanvasRef.current, 0, 0)
    }

    // Draw objectives
    for (const obj of terrain.objectives) {
      const { sx, sy } = worldToScreen(obj.x, obj.y, transform, canvasSize.height)
      const radius = obj.radius * transform.scale
      ctx2d.beginPath()
      ctx2d.arc(sx, sy, radius, 0, Math.PI * 2)
      ctx2d.strokeStyle = '#FFD700'
      ctx2d.lineWidth = 2
      ctx2d.setLineDash([4, 4])
      ctx2d.stroke()
      ctx2d.setLineDash([])
    }

    // Draw movement trails
    if (showTrails && currentFrame > 0) {
      const trailLength = Math.min(currentFrame, 20)
      const startIdx = currentFrame - trailLength
      const unitTrails = new Map<string, { x: number; y: number }[]>()

      for (let i = startIdx; i <= currentFrame; i++) {
        const frame = frames[i]
        if (!frame) continue
        for (const u of frame.units) {
          if (!showDestroyed && u.status >= 3) continue
          const trail = unitTrails.get(u.id) ?? []
          trail.push({ x: u.x, y: u.y })
          unitTrails.set(u.id, trail)
        }
      }

      for (const [unitId, trail] of unitTrails) {
        if (trail.length < 2) continue
        const lastUnit = currentFrameData?.units.find((u) => u.id === unitId)
        const color = lastUnit ? (SIDE_COLORS[lastUnit.side] ?? '#999') : '#999'
        ctx2d.strokeStyle = color
        ctx2d.lineWidth = 1
        ctx2d.globalAlpha = 0.4
        ctx2d.beginPath()
        const start = worldToScreen(trail[0]!.x, trail[0]!.y, transform, canvasSize.height)
        ctx2d.moveTo(start.sx, start.sy)
        for (let j = 1; j < trail.length; j++) {
          const pt = worldToScreen(trail[j]!.x, trail[j]!.y, transform, canvasSize.height)
          ctx2d.lineTo(pt.sx, pt.sy)
        }
        ctx2d.stroke()
        ctx2d.globalAlpha = 1.0
      }
    }

    // Draw engagement arcs
    if (showEngagements && currentFrameData) {
      const tick = currentFrameData.tick
      const visibleArcs = engagementArcs.filter(
        (a) => Math.abs(a.tick - tick) <= 5,
      )
      for (const arc of visibleArcs) {
        const from = worldToScreen(arc.attackerX, arc.attackerY, transform, canvasSize.height)
        const to = worldToScreen(arc.targetX, arc.targetY, transform, canvasSize.height)
        ctx2d.beginPath()
        ctx2d.moveTo(from.sx, from.sy)
        ctx2d.lineTo(to.sx, to.sy)
        ctx2d.strokeStyle = arc.hit ? '#FF4444' : '#FFAA00'
        ctx2d.lineWidth = arc.hit ? 2 : 1
        ctx2d.setLineDash(arc.hit ? [] : [3, 3])
        ctx2d.stroke()
        ctx2d.setLineDash([])
      }
    }

    // Draw units
    if (currentFrameData) {
      for (const unit of currentFrameData.units) {
        if (!showDestroyed && unit.status >= 3) continue
        const isSelected = selectedUnit?.id === unit.id
        drawUnit(ctx2d, unit, transform, canvasSize.height, isSelected, showLabels)
      }
    }
  }, [
    currentFrame, currentFrameData, transform, canvasSize,
    showLabels, showDestroyed, showEngagements, showTrails,
    terrain.objectives, frames, engagementArcs, selectedUnit,
    // eslint-disable-next-line react-hooks/exhaustive-deps
    terrainVersionRef.current,
  ])

  // Click handler for unit selection
  const handleCanvasClick = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      if (!currentFrameData) return
      const rect = e.currentTarget.getBoundingClientRect()
      const sx = e.clientX - rect.left
      const sy = e.clientY - rect.top

      for (const unit of currentFrameData.units) {
        if (!showDestroyed && unit.status >= 3) continue
        if (hitTestUnit(sx, sy, unit, transform, canvasSize.height)) {
          setSelectedUnit(unit)
          return
        }
      }
      setSelectedUnit(null)
    },
    [currentFrameData, transform, canvasSize.height, showDestroyed],
  )

  // Track mouse world position
  const handleMouseMove = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      viewportMouseMove(e)
      const rect = e.currentTarget.getBoundingClientRect()
      const sx = e.clientX - rect.left
      const sy = e.clientY - rect.top
      const w = screenToWorld(sx, sy, transform, canvasSize.height)
      setMouseWorld({ x: w.wx, y: w.wy })
    },
    [viewportMouseMove, transform, canvasSize.height],
  )

  const handleZoomToFit = useCallback(() => {
    if (terrain.extent.length >= 4) {
      fitToExtent(terrain.extent, canvasSize.width, canvasSize.height)
    }
  }, [terrain.extent, canvasSize, fitToExtent])

  return (
    <div className="flex h-full flex-col gap-2">
      <MapControls
        showLabels={showLabels}
        onToggleLabels={() => setShowLabels((v) => !v)}
        showDestroyed={showDestroyed}
        onToggleDestroyed={() => setShowDestroyed((v) => !v)}
        showEngagements={showEngagements}
        onToggleEngagements={() => setShowEngagements((v) => !v)}
        showTrails={showTrails}
        onToggleTrails={() => setShowTrails((v) => !v)}
        onZoomToFit={handleZoomToFit}
        mouseWorldX={mouseWorld?.x ?? null}
        mouseWorldY={mouseWorld?.y ?? null}
      />

      <div className="relative flex-1" ref={containerRef}>
        <canvas
          ref={canvasRef}
          width={canvasSize.width}
          height={canvasSize.height}
          className="absolute inset-0 cursor-crosshair"
          onWheel={onWheel}
          onMouseDown={onMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={onMouseUp}
          onMouseLeave={onMouseUp}
          onClick={handleCanvasClick}
        />
        {/* Legend overlay */}
        <div className="pointer-events-none absolute bottom-2 left-2">
          <div className="pointer-events-auto">
            <MapLegend />
          </div>
        </div>
        {/* Unit detail sidebar */}
        {selectedUnit && (
          <div className="absolute right-2 top-2">
            <UnitDetailSidebar unit={selectedUnit} onClose={() => setSelectedUnit(null)} />
          </div>
        )}
      </div>

      <PlaybackControls
        currentFrame={currentFrame}
        totalFrames={frames.length}
        isPlaying={isPlaying}
        speed={speed}
        currentTick={currentFrameData?.tick ?? null}
        onPlay={play}
        onPause={pause}
        onStepForward={stepForward}
        onStepBackward={stepBackward}
        onSeek={seekTo}
        onSetSpeed={setSpeed}
        speedOptions={speedOptions}
      />
    </div>
  )
}
