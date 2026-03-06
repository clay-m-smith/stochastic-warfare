import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { ProgressBar } from '../../components/ProgressBar'
import { useRunProgress } from '../../hooks/useWebSocket'
import { formatSeconds } from '../../lib/format'

interface RunProgressPanelProps {
  runId: string
}

export function RunProgressPanel({ runId }: RunProgressPanelProps) {
  const queryClient = useQueryClient()
  const { latestMessage, isConnected } = useRunProgress(runId)

  useEffect(() => {
    if (latestMessage?.type === 'complete') {
      void queryClient.invalidateQueries({ queryKey: ['runs', runId] })
    }
  }, [latestMessage?.type, runId, queryClient])

  const tick = latestMessage?.tick ?? 0
  const maxTicks = latestMessage?.max_ticks ?? 0
  const elapsed = latestMessage?.elapsed_s ?? 0
  const activeUnits = latestMessage?.active_units

  return (
    <div className="space-y-4 rounded-lg bg-white p-6 shadow">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-900">Live Progress</h2>
        <span
          className={`inline-flex items-center gap-1 text-xs ${
            isConnected ? 'text-green-600' : 'text-gray-400'
          }`}
        >
          <span
            className={`inline-block h-2 w-2 rounded-full ${
              isConnected ? 'bg-green-500' : 'bg-gray-300'
            }`}
          />
          {isConnected ? 'Connected' : 'Disconnected'}
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
