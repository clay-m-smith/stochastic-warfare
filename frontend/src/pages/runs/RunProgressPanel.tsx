import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { ProgressBar } from '../../components/ProgressBar'
import { useRunProgress } from '../../hooks/useWebSocket'
import { formatSeconds } from '../../lib/format'

interface RunProgressPanelProps {
  runId: string
}

const CONNECTION_LABELS: Record<string, { text: string; dotClass: string; textClass: string }> = {
  connected: { text: 'Connected', dotClass: 'bg-green-500', textClass: 'text-green-600' },
  connecting: { text: 'Connecting...', dotClass: 'bg-yellow-400', textClass: 'text-yellow-600' },
  disconnected: { text: 'Reconnecting...', dotClass: 'bg-yellow-400', textClass: 'text-yellow-600' },
  failed: { text: 'Connection failed', dotClass: 'bg-red-500', textClass: 'text-red-600' },
}

export function RunProgressPanel({ runId }: RunProgressPanelProps) {
  const queryClient = useQueryClient()
  const { latestMessage, connectionState } = useRunProgress(runId)

  useEffect(() => {
    if (latestMessage?.type === 'complete') {
      void queryClient.invalidateQueries({ queryKey: ['runs', runId] })
    }
  }, [latestMessage?.type, runId, queryClient])

  // Poll fallback when WS fails
  useEffect(() => {
    if (connectionState !== 'failed') return
    const interval = setInterval(() => {
      void queryClient.invalidateQueries({ queryKey: ['runs', runId] })
    }, 5000)
    return () => clearInterval(interval)
  }, [connectionState, runId, queryClient])

  const tick = latestMessage?.tick ?? 0
  const maxTicks = latestMessage?.max_ticks ?? 0
  const elapsed = latestMessage?.elapsed_s ?? 0
  const activeUnits = latestMessage?.active_units
  const connInfo = CONNECTION_LABELS[connectionState] ?? CONNECTION_LABELS.connected!

  return (
    <div className="space-y-4 rounded-lg bg-white p-6 shadow">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-900">Live Progress</h2>
        <span className={`inline-flex items-center gap-1 text-xs ${connInfo!.textClass}`}>
          <span className={`inline-block h-2 w-2 rounded-full ${connInfo!.dotClass}`} />
          {connInfo!.text}
        </span>
      </div>

      <ProgressBar value={tick} max={maxTicks} label={`Tick ${tick} of ${maxTicks}`} />

      <div className="flex gap-6 text-sm text-gray-600">
        <span>Elapsed: {formatSeconds(elapsed)}</span>
      </div>

      {activeUnits != null && (
        <div>
          <h3 className="mb-2 text-sm font-medium text-gray-500">Active Units</h3>
          <div className="flex gap-4">
            {Object.entries(activeUnits).map(([side, count]) => (
              <div key={side} className="text-sm">
                <span className="font-medium text-gray-700">{side}:</span>{' '}
                <span className="text-gray-600">{count}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {latestMessage?.type === 'error' && (
        <div className="rounded-md bg-red-50 p-3 text-sm text-red-700">
          {latestMessage.message ?? 'An error occurred'}
        </div>
      )}
    </div>
  )
}
