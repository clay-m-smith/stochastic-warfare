import { useState } from 'react'
import { ErrorBarChart } from '../../components/charts/ErrorBarChart'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { Select } from '../../components/Select'
import { useScenarios } from '../../hooks/useScenarios'
import { useSweep } from '../../hooks/useAnalysis'
import { validateSweepResult } from '../../utils/analysisEvidence'

interface SubmittedSweep {
  scenario: string
  parameterName: string
  values: number[]
  orderedMetrics: string[]
  numIterations: number
  baseSeed: number
  maxTicks: number
}

const BASE_SEED = 42

export function SweepPanel() {
  const { data: scenarios } = useScenarios()
  const [scenario, setScenario] = useState('')
  const [paramName, setParamName] = useState('')
  const [valuesStr, setValuesStr] = useState('')
  const [numIterations, setNumIterations] = useState(10)
  const [maxTicks, setMaxTicks] = useState(10000)
  const [inputError, setInputError] = useState<string | null>(null)
  const [submittedSweep, setSubmittedSweep] = useState<SubmittedSweep | null>(null)

  const sweep = useSweep()

  const scenarioOptions = (scenarios ?? []).map((s) => ({ value: s.name, label: s.display_name }))
  const selectedScenario = (scenarios ?? []).find((candidate) => candidate.name === scenario)

  const handleSubmit = () => {
    if (!scenario || !selectedScenario || !paramName || !valuesStr) return
    sweep.reset()
    setSubmittedSweep(null)
    setInputError(null)
    const tokens = valuesStr.split(',')
    if (tokens.some((token) => token.trim() === '')) {
      setInputError('Every sweep value must be a non-empty finite number.')
      return
    }
    const values = tokens.map((token) => Number(token.trim()))
    if (values.some((value) => !Number.isFinite(value))) {
      setInputError('Every sweep value must be a non-empty finite number.')
      return
    }
    if (new Set(values).size !== values.length) {
      setInputError('Sweep values must be duplicate-free.')
      return
    }
    if (
      !Number.isInteger(numIterations)
      || numIterations < 2
      || !Number.isInteger(maxTicks)
      || maxTicks < 1
    ) {
      setInputError('Iterations and max ticks must be valid positive integers.')
      return
    }
    const submitted = {
      scenario,
      parameterName: paramName,
      values,
      orderedMetrics: selectedScenario.sides.map(
        (side) => `${side}_destroyed`,
      ),
      numIterations,
      baseSeed: BASE_SEED,
      maxTicks,
    }
    setSubmittedSweep(submitted)
    sweep.mutate({
      scenario,
      parameter_name: paramName,
      values,
      metrics: submitted.orderedMetrics,
      num_iterations: numIterations,
      base_seed: BASE_SEED,
      max_ticks: maxTicks,
    })
  }

  const evidenceError = sweep.data && submittedSweep
    ? validateSweepResult(sweep.data, submittedSweep)
    : null
  const validatedResult = sweep.data && !evidenceError ? sweep.data : null

  return (
    <div className="space-y-6">
      <div className="rounded-lg bg-white dark:bg-gray-800 p-6 shadow">
        <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-gray-100">Sensitivity Sweep</h2>
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
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Parameter Name</label>
            <input
              type="text"
              value={paramName}
              onChange={(e) => setParamName(e.target.value)}
              placeholder="e.g. hit_probability_modifier"
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Values (comma-separated)</label>
            <input
              type="text"
              value={valuesStr}
              onChange={(e) => setValuesStr(e.target.value)}
              placeholder="e.g. 100, 500, 1000, 2000"
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200"
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
          disabled={!scenario || !paramName || !valuesStr || sweep.isPending}
          className="mt-4 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {sweep.isPending ? 'Running...' : 'Run Sweep'}
        </button>
        {sweep.error && (
          <p className="mt-2 text-sm text-red-600">{sweep.error.message}</p>
        )}
        {inputError && (
          <p className="mt-2 text-sm text-red-600" role="alert">{inputError}</p>
        )}
      </div>

      {sweep.isPending && <LoadingSpinner />}

      {evidenceError && (
        <div
          className="rounded-md bg-red-50 p-4 text-sm text-red-700 dark:bg-red-900/30 dark:text-red-300"
          role="alert"
        >
          Sweep result rejected: {evidenceError}
        </div>
      )}

      {validatedResult?.ordered_metrics.map((metricName) => (
        <ErrorBarChart
          key={metricName}
          data={validatedResult.points.map((point) => {
            const metric = point.metric_results.find(
              (candidate) => candidate.metric === metricName,
            )!
            return {
              x: String(point.parameter_value),
              mean: metric.mean,
              std: metric.std,
            }
          })}
          title={`${validatedResult.parameter_name} Sensitivity: ${metricName}`}
          xLabel={validatedResult.parameter_name}
          yLabel={metricName}
        />
      ))}

      {validatedResult && (
        <div
          aria-label="Sweep raw vectors and provenance"
          className="rounded-lg bg-white p-4 shadow dark:bg-gray-800"
        >
          <h3 className="font-semibold text-gray-900 dark:text-gray-100">
            Raw vectors and provenance
          </h3>
          <dl className="mt-2 grid gap-1 break-all text-xs text-gray-600 dark:text-gray-400">
            <div>
              <dt className="inline font-medium">Seeds: </dt>
              <dd className="inline">{validatedResult.seeds.join(', ')}</dd>
            </div>
            <div>
              <dt className="inline font-medium">Source SHA-256: </dt>
              <dd className="inline">{validatedResult.source_fingerprint}</dd>
            </div>
            <div>
              <dt className="inline font-medium">Data root: </dt>
              <dd className="inline">{validatedResult.data_root}</dd>
            </div>
          </dl>
          <div className="mt-3 grid gap-3">
            {validatedResult.points.map((point) => (
              <div
                className="rounded border border-gray-200 p-3 text-xs dark:border-gray-700"
                key={point.parameter_value}
              >
                <div className="font-medium text-gray-800 dark:text-gray-200">
                  {validatedResult.parameter_name} = {point.parameter_value}
                </div>
                {point.metric_results.map((metric) => (
                  <div className="mt-1 text-gray-600 dark:text-gray-400" key={metric.metric}>
                    {metric.metric} raw: {JSON.stringify(metric.values)}
                  </div>
                ))}
                <div className="mt-2 break-all text-gray-500">
                  Config SHA-256: {point.batch.config_fingerprint}
                </div>
                <div className="break-all text-gray-500">
                  Code revision: {point.batch.code_revision.commit}
                  {point.batch.code_revision.dirty ? ' (dirty)' : ' (clean)'}
                </div>
                <div className="break-all text-gray-500">
                  Worktree SHA-256: {point.batch.code_revision.worktree_fingerprint}
                </div>
                <div className="break-all text-gray-500">
                  Catalog SHA-256: {point.batch.catalog_revision}
                </div>
                <div className="break-all text-gray-500">
                  Loadout SHA-256: {point.batch.loaded_roster_loadout_fingerprint}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
