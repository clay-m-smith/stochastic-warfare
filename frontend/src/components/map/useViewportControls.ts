import { useState, useCallback, useRef } from 'react'
import type { ViewportTransform } from '../../types/map'

const MIN_SCALE = 0.05
const MAX_SCALE = 50
const ZOOM_FACTOR = 1.15

export function useViewportControls(initialTransform?: Partial<ViewportTransform>) {
  const [transform, setTransform] = useState<ViewportTransform>({
    offsetX: initialTransform?.offsetX ?? 0,
    offsetY: initialTransform?.offsetY ?? 0,
    scale: initialTransform?.scale ?? 1,
  })

  const isPanning = useRef(false)
  const lastMouse = useRef({ x: 0, y: 0 })

  const onWheel = useCallback(
    (e: React.WheelEvent<HTMLCanvasElement>) => {
      e.preventDefault()
      const rect = e.currentTarget.getBoundingClientRect()
      const mouseX = e.clientX - rect.left
      const mouseY = e.clientY - rect.top
      const canvasHeight = e.currentTarget.height

      setTransform((prev) => {
        const zoomIn = e.deltaY < 0
        const factor = zoomIn ? ZOOM_FACTOR : 1 / ZOOM_FACTOR
        const newScale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, prev.scale * factor))

        // Zoom toward cursor position
        const worldX = mouseX / prev.scale + prev.offsetX
        const worldY = (canvasHeight - mouseY) / prev.scale + prev.offsetY

        return {
          offsetX: worldX - mouseX / newScale,
          offsetY: worldY - (canvasHeight - mouseY) / newScale,
          scale: newScale,
        }
      })
    },
    [],
  )

  const onMouseDown = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    if (e.button === 0) {
      isPanning.current = true
      lastMouse.current = { x: e.clientX, y: e.clientY }
    }
  }, [])

  const onMouseMove = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      if (!isPanning.current) return
      const dx = e.clientX - lastMouse.current.x
      const dy = e.clientY - lastMouse.current.y
      lastMouse.current = { x: e.clientX, y: e.clientY }

      setTransform((prev) => ({
        ...prev,
        offsetX: prev.offsetX - dx / prev.scale,
        offsetY: prev.offsetY + dy / prev.scale, // Y flip
      }))
    },
    [],
  )

  const onMouseUp = useCallback(() => {
    isPanning.current = false
  }, [])

  const fitToExtent = useCallback(
    (extent: number[], canvasWidth: number, canvasHeight: number) => {
      if (extent.length < 4 || canvasWidth === 0 || canvasHeight === 0) return
      const minX = extent[0]!
      const minY = extent[1]!
      const maxX = extent[2]!
      const maxY = extent[3]!
      const worldW = maxX - minX
      const worldH = maxY - minY
      if (worldW === 0 || worldH === 0) return

      const padding = 0.05
      const scaleX = canvasWidth / (worldW * (1 + padding * 2))
      const scaleY = canvasHeight / (worldH * (1 + padding * 2))
      const scale = Math.min(scaleX, scaleY)

      setTransform({
        offsetX: minX - (canvasWidth / scale - worldW) / 2,
        offsetY: minY - (canvasHeight / scale - worldH) / 2,
        scale,
      })
    },
    [],
  )

  return {
    transform,
    onWheel,
    onMouseDown,
    onMouseMove,
    onMouseUp,
    fitToExtent,
  }
}
