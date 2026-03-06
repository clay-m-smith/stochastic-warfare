import { useCallback, useEffect, useRef, useState } from 'react'
import type { BatchProgressMessage, RunProgressMessage } from '../types/api'

interface ForceSnapshot {
  tick: number
  units: Record<string, number>
}

export type ConnectionState = 'connecting' | 'connected' | 'disconnected' | 'failed'

interface RunProgressState {
  latestMessage: RunProgressMessage | null
  forceHistory: ForceSnapshot[]
  isConnected: boolean
  connectionState: ConnectionState
}

function getWsUrl(path: string): string {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${window.location.host}${path}`
}

const MAX_RECONNECT_ATTEMPTS = 3
const BACKOFF_BASE_MS = 1000

export function useRunProgress(runId: string | null): RunProgressState {
  const [state, setState] = useState<RunProgressState>({
    latestMessage: null,
    forceHistory: [],
    isConnected: false,
    connectionState: 'disconnected',
  })
  const wsRef = useRef<WebSocket | null>(null)
  const attemptRef = useRef(0)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const completedRef = useRef(false)

  const connect = useCallback(() => {
    if (!runId || completedRef.current) return

    setState((prev) => ({ ...prev, connectionState: 'connecting' }))
    const ws = new WebSocket(getWsUrl(`/api/runs/${runId}/progress`))
    wsRef.current = ws

    ws.onopen = () => {
      attemptRef.current = 0
      setState((prev) => ({ ...prev, isConnected: true, connectionState: 'connected' }))
    }

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data as string) as RunProgressMessage
        if (msg.type === 'complete') {
          completedRef.current = true
        }
        setState((prev) => {
          const next: RunProgressState = {
            ...prev,
            latestMessage: msg,
            connectionState: 'connected',
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
      wsRef.current = null

      // Only reconnect if not completed and under max attempts
      if (!completedRef.current && attemptRef.current < MAX_RECONNECT_ATTEMPTS) {
        const delay = BACKOFF_BASE_MS * Math.pow(2, attemptRef.current)
        attemptRef.current++
        setState((prev) => ({ ...prev, connectionState: 'disconnected' }))
        timerRef.current = setTimeout(connect, delay)
      } else if (!completedRef.current) {
        setState((prev) => ({ ...prev, connectionState: 'failed' }))
      }
    }

    ws.onerror = () => {
      // onclose will fire after onerror, which handles reconnect
    }
  }, [runId])

  useEffect(() => {
    completedRef.current = false
    attemptRef.current = 0
    connect()

    return () => {
      completedRef.current = true
      if (timerRef.current) clearTimeout(timerRef.current)
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [connect])

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
