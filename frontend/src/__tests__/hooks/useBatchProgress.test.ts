import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useBatchProgress } from '../../hooks/useWebSocket'

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
}

beforeEach(() => {
  MockWebSocket.instances = []
  vi.stubGlobal('WebSocket', MockWebSocket)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('useBatchProgress', () => {
  it('does not connect when batchId is null', () => {
    renderHook(() => useBatchProgress(null))
    expect(MockWebSocket.instances).toHaveLength(0)
  })

  it('connects and reports isConnected on open', () => {
    const { result } = renderHook(() => useBatchProgress('b1'))
    expect(MockWebSocket.instances).toHaveLength(1)
    expect(result.current.isConnected).toBe(false)

    act(() => {
      MockWebSocket.instances[0]!.simulateOpen()
    })
    expect(result.current.isConnected).toBe(true)
  })

  it('parses batch progress messages', () => {
    const { result } = renderHook(() => useBatchProgress('b1'))
    const ws = MockWebSocket.instances[0]!
    act(() => ws.simulateOpen())

    act(() => {
      ws.simulateMessage({ type: 'iteration', iteration: 3, total: 20, seed: 45 })
    })
    expect(result.current.latestMessage?.type).toBe('iteration')
    expect(result.current.latestMessage?.iteration).toBe(3)
  })

  it('cleans up on unmount', () => {
    const { unmount } = renderHook(() => useBatchProgress('b1'))
    const ws = MockWebSocket.instances[0]!
    const closeSpy = vi.spyOn(ws, 'close')
    unmount()
    expect(closeSpy).toHaveBeenCalled()
  })
})
