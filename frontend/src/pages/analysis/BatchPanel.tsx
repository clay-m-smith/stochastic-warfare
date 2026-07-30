import { useState } from 'react'
import { ProgressBar } from '../../components/ProgressBar'
import { useScenarios } from '../../hooks/useScenarios'
import { useBatch } from '../../hooks/useBatch'
import { useSubmitBatch } from '../../hooks/useBatch'
import { useBatchProgress } from '../../hooks/useWebSocket'
import { Select } from '../../components/Select'
import { BatchResultsView } from './BatchResultsView'
import { validateBatchDetail } from '../../utils/analysisEvidence'
import type { BatchExpectation } from '../../utils/analysisEvidence'

export function BatchPanel() {
  const { data: scenarios } = useScenarios()
  const [scenario, setScenario] = useState('')
  const [numIterations, setNumIterations] = useState(10)
  const [baseSeed, setBaseSeed] = useState(42)
  const [maxTicks, setMaxTicks] = useState(10000)
  const [batchId, setBatchId] = useState<string | null>(null)
  const [submittedBatch, setSubmittedBatch] = useState<BatchExpectation | null>(null)

  const submit = useSubmitBatch()
  const { data: batchDetail } = useBatch(batchId)
  const { latestMessage } = useBatchProgress(
    batchId && batchDetail?.status !== 'completed' && batchDetail?.status !== 'failed'
      ? batchId
      : null,
  )

  const scenarioOptions = (scenarios ?? []).map((s) => ({ value: s.name, label: s.display_name }))
  const selectedScenario = scenarios?.find((candidate) => candidate.name === scenario)
  const orderedMetrics = selectedScenario?.sides.flatMap((side) => [
    `${side}_active`,
    `${side}_destroyed`,
  ]) ?? []

  const handleSubmit = () => {
    if (!scenario || orderedMetrics.length === 0) return
    const submittedMetrics = [...orderedMetrics]
    setSubmittedBatch({
      scenario,
      orderedMetrics: submittedMetrics,
      numIterations,
      baseSeed,
      maxTicks,
    })
    submit.mutate(
      {
        scenario,
        num_iterations: numIterations,
        base_seed: baseSeed,
        max_ticks: maxTicks,
        metrics: submittedMetrics,
      },
      {
        onSuccess: (resp) => {
          setSubmittedBatch((current) => (
            current ? { ...current, batchId: resp.batch_id } : current
          ))
          setBatchId(resp.batch_id)
        },
      },
    )
  }

  const isRunning = batchDetail?.status === 'pending' || batchDetail?.status === 'running'
  const isCompleted = batchDetail?.status === 'completed'
  const evidenceError = isCompleted && batchDetail
    ? validateBatchDetail(batchDetail, submittedBatch ?? undefined)
    : null

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
          disabled={orderedMetrics.length === 0 || submit.isPending || isRunning}
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

      {isCompleted && evidenceError && (
        <div
          className="rounded-md bg-red-50 p-4 text-sm text-red-700 dark:bg-red-900/30 dark:text-red-300"
          role="alert"
        >
          Completed batch rejected: {evidenceError}
        </div>
      )}

      {isCompleted
        && !evidenceError
        && batchDetail.metrics
        && batchDetail.raw_metrics
        && batchDetail.provenance
        && (
          <BatchResultsView
            metrics={batchDetail.metrics}
            orderedMetrics={batchDetail.ordered_metrics}
            rawMetrics={batchDetail.raw_metrics}
            provenance={batchDetail.provenance}
          />
        )}
    </div>
  )
}
