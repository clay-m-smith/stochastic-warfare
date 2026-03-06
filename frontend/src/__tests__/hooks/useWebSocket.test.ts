import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useRunProgress } from '../../hooks/useWebSocket'

class MockWebSocket {
  static instances: MockWebSocket[] = []
  onopen: (() => void) | null = null
  onmessage: ((ev: { data: string }) => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null
  readyState = 0
  url: string

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
  }

  close() {
    this.readyState = 3
  }

  simulateOpen() {
    this.readyState = 1
    this.onopen?.()
  }

  simulateMessage(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) })
  }

  simulateClose() {
    this.readyState = 3
    this.onclose?.()
  }

  simulateError() {
    this.onerror?.()
  }
}

beforeEach(() => {
  MockWebSocket.instances = []
  vi.stubGlobal('WebSocket', MockWebSocket)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('useRunProgress', () => {
  it('does not connect when runId is null', () => {
    renderHook(() => useRunProgress(null))
    expect(MockWebSocket.instances).toHaveLength(0)
  })

  it('connects and reports isConnected on open', () => {
    const { result } = renderHook(() => useRunProgress('r1'))
    expect(MockWebSocket.instances).toHaveLength(1)
    expect(result.current.isConnected).toBe(false)

    act(() => {
      MockWebSocket.instances[0]!.simulateOpen()
    })
    expect(result.current.isConnected).toBe(true)
  })

  it('accumulates force history from tick messages', () => {
    const { result } = renderHook(() => useRunProgress('r1'))
    const ws = MockWebSocket.instances[0]!
    act(() => ws.simulateOpen())

    act(() => {
      ws.simulateMessage({ type: 'tick', tick: 1, max_ticks: 100, active_units: { blue: 10, red: 8 } })
    })
    expect(result.current.latestMessage?.tick).toBe(1)
    expect(result.current.forceHistory).toHaveLength(1)
    expect(result.current.forceHistory[0]).toEqual({ tick: 1, units: { blue: 10, red: 8 } })

    act(() => {
      ws.simulateMessage({ type: 'tick', tick: 5, max_ticks: 100, active_units: { blue: 9, red: 7 } })
    })
    expect(result.current.forceHistory).toHaveLength(2)
  })

  it('handles close event', () => {
    const { result } = renderHook(() => useRunProgress('r1'))
    const ws = MockWebSocket.instances[0]!
    act(() => ws.simulateOpen())
    expect(result.current.isConnected).toBe(true)

    act(() => ws.simulateClose())
    expect(result.current.isConnected).toBe(false)
  })

  it('cleans up on unmount', () => {
    const { unmount } = renderHook(() => useRunProgress('r1'))
    const ws = MockWebSocket.instances[0]!
    const closeSpy = vi.spyOn(ws, 'close')
    unmount()
    expect(closeSpy).toHaveBeenCalled()
  })
})
