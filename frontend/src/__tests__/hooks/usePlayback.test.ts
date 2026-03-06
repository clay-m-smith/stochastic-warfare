import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { usePlayback } from '../../hooks/usePlayback'

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('usePlayback', () => {
  it('starts at frame 0 and not playing', () => {
    const { result } = renderHook(() => usePlayback(100))
    expect(result.current.currentFrame).toBe(0)
    expect(result.current.isPlaying).toBe(false)
    expect(result.current.speed).toBe(1)
  })

  it('seekTo changes frame', () => {
    const { result } = renderHook(() => usePlayback(100))
    act(() => result.current.seekTo(50))
    expect(result.current.currentFrame).toBe(50)
  })

  it('seekTo clamps to valid range', () => {
    const { result } = renderHook(() => usePlayback(10))
    act(() => result.current.seekTo(20))
    expect(result.current.currentFrame).toBe(9) // max = totalFrames - 1
    act(() => result.current.seekTo(-5))
    expect(result.current.currentFrame).toBe(0)
  })

  it('stepForward increments frame and pauses', () => {
    const { result } = renderHook(() => usePlayback(10))
    act(() => result.current.stepForward())
    expect(result.current.currentFrame).toBe(1)
    expect(result.current.isPlaying).toBe(false)
  })

  it('stepBackward decrements frame', () => {
    const { result } = renderHook(() => usePlayback(10))
    act(() => result.current.seekTo(5))
    act(() => result.current.stepBackward())
    expect(result.current.currentFrame).toBe(4)
  })

  it('stepBackward does not go below 0', () => {
    const { result } = renderHook(() => usePlayback(10))
    act(() => result.current.stepBackward())
    expect(result.current.currentFrame).toBe(0)
  })

  it('stepForward does not exceed max', () => {
    const { result } = renderHook(() => usePlayback(3))
    act(() => result.current.seekTo(2))
    act(() => result.current.stepForward())
    expect(result.current.currentFrame).toBe(2) // stays at max
  })

  it('play sets isPlaying to true', () => {
    const { result } = renderHook(() => usePlayback(100))
    act(() => result.current.play())
    expect(result.current.isPlaying).toBe(true)
  })

  it('pause sets isPlaying to false', () => {
    const { result } = renderHook(() => usePlayback(100))
    act(() => result.current.play())
    act(() => result.current.pause())
    expect(result.current.isPlaying).toBe(false)
  })

  it('setSpeed changes playback speed', () => {
    const { result } = renderHook(() => usePlayback(100))
    act(() => result.current.setSpeed(5))
    expect(result.current.speed).toBe(5)
  })

  it('does not play with 0 or 1 frames', () => {
    const { result } = renderHook(() => usePlayback(1))
    act(() => result.current.play())
    expect(result.current.isPlaying).toBe(false)
  })
})
