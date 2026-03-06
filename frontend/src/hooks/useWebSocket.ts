import { useCallback, useEffect, useRef, useState } from 'react'
import type { BatchProgressMessage, RunProgressMessage } from '../types/api'

interface ForceSnapshot {
  tick: number
  units: Record<string, number>
}

interface RunProgressState {
  latestMessage: RunProgressMessage | null
  forceHistory: ForceSnapshot[]
  isConnected: boolean
}

function getWsUrl(path: string): string {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${window.location.host}${path}`
}

export function useRunProgress(runId: string | null): RunProgressState {
  const [state, setState] = useState<RunProgressState>({
    latestMessage: null,
    forceHistory: [],
    isConnected: false,
  })
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    if (!runId) return

    const ws = new WebSocket(getWsUrl(`/api/runs/${runId}/progress`))
    wsRef.current = ws

    ws.onopen = () => {
      setState((prev) => ({ ...prev, isConnected: true }))
    }

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data as string) as RunProgressMessage
        setState((prev) => {
          const next: RunProgressState = {
            ...prev,
            latestMessage: msg,
          }
          if (msg.active_units != null && msg.tick != null) {
            next.forceHistory = [...prev.forceHistory, { tick: msg.tick, units: msg.active_units }]
          }
          return next
        })
      } catch {
        // Ignore malformed WS messages
      }
    }

    ws.onclose = () => {
      setState((prev) => ({ ...prev, isConnected: false }))
    }

    ws.onerror = () => {
      setState((prev) => ({ ...prev, isConnected: false }))
    }

    return () => {
      ws.close()
      wsRef.current = null
    }
  }, [runId])

  return state
}

interface BatchProgressState {
  latestMessage: BatchProgressMessage | null
  isConnected: boolean
}

export function useBatchProgress(batchId: string | null): BatchProgressState {
  const [state, setState] = useState<BatchProgressState>({
    latestMessage: null,
    isConnected: false,
  })
  const wsRef = useRef<WebSocket | null>(null)

  const cleanup = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
  }, [])

  useEffect(() => {
    if (!batchId) return

    cleanup()
    const ws = new WebSocket(getWsUrl(`/api/runs/batch/${batchId}/progress`))
    wsRef.current = ws

    ws.onopen = () => {
      setState((prev) => ({ ...prev, isConnected: true }))
    }

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data as string) as BatchProgressMessage
        setState((prev) => ({ ...prev, latestMessage: msg }))
      } catch {
        // Ignore malformed WS messages
      }
    }

    ws.onclose = () => {
      setState((prev) => ({ ...prev, isConnected: false }))
    }

    ws.onerror = () => {
      setState((prev) => ({ ...prev, isConnected: false }))
    }

    return cleanup
  }, [batchId, cleanup])

  return state
}
