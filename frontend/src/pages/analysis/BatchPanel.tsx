import { useState } from 'react'
import { ProgressBar } from '../../components/ProgressBar'
import { useScenarios } from '../../hooks/useScenarios'
import { useBatch } from '../../hooks/useBatch'
import { useSubmitBatch } from '../../hooks/useBatch'
import { useBatchProgress } from '../../hooks/useWebSocket'
import { Select } from '../../components/Select'
import { BatchResultsView } from './BatchResultsView'

export function BatchPanel() {
  const { data: scenarios } = useScenarios()
  const [scenario, setScenario] = useState('')
  const [numIterations, setNumIterations] = useState(10)
  const [baseSeed, setBaseSeed] = useState(42)
  const [maxTicks, setMaxTicks] = useState(10000)
  const [batchId, setBatchId] = useState<string | null>(null)

  const submit = useSubmitBatch()
  const { data: batchDetail } = useBatch(batchId)
  const { latestMessage } = useBatchProgress(
    batchId && batchDetail?.status !== 'completed' && batchDetail?.status !== 'failed'
      ? batchId
      : null,
  )

  const scenarioOptions = (scenarios ?? []).map((s) => ({ value: s.name, label: s.display_name }))

  const handleSubmit = () => {
    if (!scenario) return
    submit.mutate(
      { scenario, num_iterations: numIterations, base_seed: baseSeed, max_ticks: maxTicks },
      { onSuccess: (resp) => setBatchId(resp.batch_id) },
    )
  }

  const isRunning = batchDetail?.status === 'pending' || batchDetail?.status === 'running'
  const isCompleted = batchDetail?.status === 'completed'

  return (
    <div className="space-y-6">
      <div className="rounded-lg bg-white dark:bg-gray-800 p-6 shadow">
        <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-gray-100">Monte Carlo Batch</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Scenario</label>
            <Select
              value={scenario}
              onChange={setScenario}
              options={[{ value: '', label: 'Select scenario...' }, ...scenarioOptions]}
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Iterations</label>
            <input
              type="number"
              value={numIterations}
              onChange={(e) => setNumIterations(Number(e.target.value))}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Base Seed</label>
            <input
              type="number"
              value={baseSeed}
              onChange={(e) => setBaseSeed(Number(e.target.value))}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Max Ticks</label>
            <input
              type="number"
              value={maxTicks}
              onChange={(e) => setMaxTicks(Number(e.target.value))}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200"
            />
          </div>
        </div>
        <button
          onClick={handleSubmit}
          disabled={!scenario || submit.isPending || isRunning}
          className="mt-4 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {submit.isPending ? 'Submitting...' : isRunning ? 'Running...' : 'Run Batch'}
        </button>
        {submit.error && (
          <p className="mt-2 text-sm text-red-600">{submit.error.message}</p>
        )}
      </div>

      {isRunning && (
        <div className="rounded-lg bg-white dark:bg-gray-800 p-6 shadow">
          <ProgressBar
            value={latestMessage?.iteration ?? batchDetail?.completed_iterations ?? 0}
            max={latestMessage?.total ?? batchDetail?.num_iterations ?? 0}
            label="Batch Progress"
          />
        </div>
      )}

      {isCompleted && batchDetail?.metrics && (
        <BatchResultsView metrics={batchDetail.metrics} />
      )}
    </div>
  )
}
