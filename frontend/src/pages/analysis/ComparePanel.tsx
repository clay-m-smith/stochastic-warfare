import { useState } from 'react'
import { ComparisonCharts } from '../../components/charts/ComparisonCharts'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { Select } from '../../components/Select'
import { useScenarios } from '../../hooks/useScenarios'
import { useCompare } from '../../hooks/useAnalysis'
import type { CalibrationOverrides } from '../../types/api'
import { validateCompareResult } from '../../utils/analysisEvidence'
import type { CompareExpectation } from '../../utils/analysisEvidence'

const BASE_SEED = 42
const ALPHA = 0.05

export function ComparePanel() {
  const { data: scenarios } = useScenarios()
  const [scenario, setScenario] = useState('')
  const [labelA, setLabelA] = useState('Config A')
  const [labelB, setLabelB] = useState('Config B')
  const [overridesA, setOverridesA] = useState('{}')
  const [overridesB, setOverridesB] = useState('{}')
  const [numIterations, setNumIterations] = useState(10)
  const [maxTicks, setMaxTicks] = useState(10000)
  const [jsonError, setJsonError] = useState<string | null>(null)
  const [submittedCompare, setSubmittedCompare] = useState<CompareExpectation | null>(null)

  const compare = useCompare()

  const scenarioOptions = (scenarios ?? []).map((s) => ({ value: s.name, label: s.display_name }))
  const selectedScenario = (scenarios ?? []).find((candidate) => candidate.name === scenario)

  const handleSubmit = () => {
    if (!scenario || !selectedScenario) return
    compare.reset()
    setSubmittedCompare(null)
    setJsonError(null)
    let parsedA: CalibrationOverrides = {}
    let parsedB: CalibrationOverrides = {}
    try {
      parsedA = JSON.parse(overridesA) as CalibrationOverrides
    } catch (e) {
      setJsonError(`Overrides A: invalid JSON — ${e instanceof Error ? e.message : String(e)}`)
      return
    }
    try {
      parsedB = JSON.parse(overridesB) as CalibrationOverrides
    } catch (e) {
      setJsonError(`Overrides B: invalid JSON — ${e instanceof Error ? e.message : String(e)}`)
      return
    }
    const orderedMetrics = selectedScenario.sides.map(
      (side) => `${side}_destroyed`,
    )
    setSubmittedCompare({
      scenario,
      labelA,
      labelB,
      orderedMetrics,
      numIterations,
      baseSeed: BASE_SEED,
      maxTicks,
      alpha: ALPHA,
    })
    compare.mutate({
      scenario,
      overrides_a: parsedA,
      overrides_b: parsedB,
      label_a: labelA,
      label_b: labelB,
      metrics: orderedMetrics,
      num_iterations: numIterations,
      base_seed: BASE_SEED,
      max_ticks: maxTicks,
      alpha: ALPHA,
    })
  }

  const evidenceError = compare.data && submittedCompare
    ? validateCompareResult(compare.data, submittedCompare)
    : null
  const validatedResult = compare.data && !evidenceError ? compare.data : null

  return (
    <div className="space-y-6">
      <div className="rounded-lg bg-white dark:bg-gray-800 p-6 shadow">
        <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-gray-100">A/B Comparison</h2>
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
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Label A</label>
            <input
              type="text"
              value={labelA}
              onChange={(e) => setLabelA(e.target.value)}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Label B</label>
            <input
              type="text"
              value={labelB}
              onChange={(e) => setLabelB(e.target.value)}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Overrides A (JSON)</label>
            <textarea
              value={overridesA}
              onChange={(e) => setOverridesA(e.target.value)}
              rows={3}
              className="w-full rounded-md border border-gray-300 px-3 py-2 font-mono text-sm dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">Overrides B (JSON)</label>
            <textarea
              value={overridesB}
              onChange={(e) => setOverridesB(e.target.value)}
              rows={3}
              className="w-full rounded-md border border-gray-300 px-3 py-2 font-mono text-sm dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200"
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
          disabled={!scenario || compare.isPending}
          className="mt-4 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {compare.isPending ? 'Running...' : 'Run Comparison'}
        </button>
        {jsonError && (
          <p className="mt-2 text-sm text-red-600">{jsonError}</p>
        )}
        {compare.error && (
          <p className="mt-2 text-sm text-red-600">{compare.error.message}</p>
        )}
      </div>

      {compare.isPending && <LoadingSpinner />}

      {evidenceError && (
        <div
          className="rounded-md bg-red-50 p-4 text-sm text-red-700 dark:bg-red-900/30 dark:text-red-300"
          role="alert"
        >
          Comparison result rejected: {evidenceError}
        </div>
      )}

      {validatedResult && (
        <ComparisonCharts
          result={validatedResult}
          labelA={validatedResult.label_a}
          labelB={validatedResult.label_b}
        />
      )}
    </div>
  )
}
