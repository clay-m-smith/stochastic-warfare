import { describe, it, expect } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useViewportControls } from '../../components/map/useViewportControls'

describe('useViewportControls', () => {
  it('uses provided initial transform values', () => {
    const { result } = renderHook(() =>
      useViewportControls({ offsetX: 10, offsetY: 20, scale: 2 }),
    )
    expect(result.current.transform).toEqual({ offsetX: 10, offsetY: 20, scale: 2 })
  })

  it('defaults to zero offset and scale 1', () => {
    const { result } = renderHook(() => useViewportControls())
    expect(result.current.transform).toEqual({ offsetX: 0, offsetY: 0, scale: 1 })
  })

  it('onWheel zooms in and out', () => {
    const { result } = renderHook(() => useViewportControls())
    const initialScale = result.current.transform.scale

    const makeWheelEvent = (deltaY: number) =>
      ({
        preventDefault: () => {},
        deltaY,
        clientX: 200,
        clientY: 200,
        currentTarget: {
          getBoundingClientRect: () => ({ left: 0, top: 0 }),
          height: 400,
        },
      }) as unknown as React.WheelEvent<HTMLCanvasElement>

    // Zoom in (negative deltaY)
    act(() => {
      result.current.onWheel(makeWheelEvent(-100))
    })
    expect(result.current.transform.scale).toBeGreaterThan(initialScale)

    const zoomedIn = result.current.transform.scale

    // Zoom out (positive deltaY)
    act(() => {
      result.current.onWheel(makeWheelEvent(100))
    })
    expect(result.current.transform.scale).toBeLessThan(zoomedIn)
  })

  it('fitToExtent computes correct scale and offset', () => {
    const { result } = renderHook(() => useViewportControls())

    act(() => {
      result.current.fitToExtent([0, 0, 1000, 1000], 800, 600)
    })

    // Scale should fit 1000x1000 world into 800x600 canvas (with 5% padding)
    // scaleX = 800 / (1000 * 1.1) ≈ 0.727, scaleY = 600 / (1000 * 1.1) ≈ 0.545
    // scale = min(0.727, 0.545) ≈ 0.545
    expect(result.current.transform.scale).toBeCloseTo(600 / 1100, 2)
    // Offset should center the view
    expect(result.current.transform.offsetX).toBeDefined()
    expect(result.current.transform.offsetY).toBeDefined()
  })
})
