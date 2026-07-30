import { useState } from 'react'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { Select } from '../../components/Select'
import { useDoctrineCompare } from '../../hooks/useAnalysis'
import { useSchools } from '../../hooks/useMeta'
import { useScenarios } from '../../hooks/useScenarios'
import type { DoctrineCompareResult } from '../../types/analysis'
import { validateDoctrineResult } from '../../utils/analysisEvidence'
import type { DoctrineExpectation } from '../../utils/analysisEvidence'

const BASE_SEED = 42

function ResultsTable({ data }: { data: DoctrineCompareResult }) {
  return (
    <div className="overflow-x-auto rounded-lg bg-white shadow dark:bg-gray-800">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="border-b border-gray-200 text-left text-gray-500 dark:border-gray-700 dark:text-gray-400">
            <th className="px-4 py-3 font-medium" scope="col">Policy</th>
            {data.ordered_metrics.map((metric) => (
              <th className="px-4 py-3 font-medium" scope="col" key={metric}>
                {metric.replace(/_/g, ' ')}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.results.map((result) => {
            const provenance = result.batch.runs[0]?.runtime_provenance
            return (
              <tr
                key={result.variant_id}
                className="border-b border-gray-100 dark:border-gray-700"
              >
              <td className="px-4 py-2 font-medium text-gray-900 dark:text-gray-100">
                <div>{result.variant_id}</div>
                <div className="text-xs font-normal text-gray-500">
                  {result.assignments
                    .map((assignment) => `${assignment.side}: ${assignment.school_id}`)
                    .join(', ')}
                </div>
                {provenance ? (
                  <details className="mt-1 text-xs font-normal text-gray-500">
                    <summary>Provenance</summary>
                    <div className="break-all">
                      Source: {result.batch.source_fingerprint}
                    </div>
                    <div className="break-all">
                      Config: {result.batch.config_fingerprint}
                    </div>
                    <div className="break-all">
                      Doctrine assignment: {provenance.doctrine_assignment_fingerprint}
                    </div>
                    <div className="break-all">
                      Loadout topology: {provenance.final_roster_loadout_fingerprint}
                    </div>
                  </details>
                ) : (
                  <div className="text-xs font-normal text-red-600">
                    Missing runtime provenance
                  </div>
                )}
              </td>
              {data.ordered_metrics.map((metricName) => {
                const metric = result.metrics.find((item) => item.metric === metricName)
                return (
                  <td className="px-4 py-2 font-mono" key={metricName}>
                    {metric
                      ? (
                        <>
                          <div>{metric.mean.toFixed(2)} +/- {metric.std.toFixed(2)}</div>
                          <div className="text-xs text-gray-500">
                            raw: {JSON.stringify(metric.values)}
                          </div>
                        </>
                      )
                      : 'Missing'}
                  </td>
                )
              })}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export function DoctrineComparePanel() {
  const { data: scenarios } = useScenarios()
  const { data: schools } = useSchools()
  const [scenario, setScenario] = useState('')
  const [sideToVary, setSideToVary] = useState('')
  const [selectedSchools, setSelectedSchools] = useState<Set<string>>(new Set())
  const [numIterations, setNumIterations] = useState(10)
  const [maxTicks, setMaxTicks] = useState(10000)
  const [submittedDoctrine, setSubmittedDoctrine] = useState<DoctrineExpectation | null>(null)

  const doctrineCompare = useDoctrineCompare()

  const scenarioOptions = (scenarios ?? []).map((s) => ({ value: s.name, label: s.display_name }))
  const selectedScenario = (scenarios ?? []).find((candidate) => candidate.name === scenario)

  const handleScenarioChange = (name: string) => {
    setScenario(name)
    const nextScenario = (scenarios ?? []).find((candidate) => candidate.name === name)
    setSideToVary(nextScenario?.sides[0] ?? '')
  }

  const toggleSchool = (id: string) => {
    setSelectedSchools((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const canSubmit = Boolean(
    scenario
    && sideToVary
    && selectedSchools.size >= 2
    && !doctrineCompare.isPending,
  )

  const handleSubmit = () => {
    if (!canSubmit || !selectedScenario) return
    doctrineCompare.reset()
    setSubmittedDoctrine(null)
    const variants = Array.from(selectedSchools).map((schoolId) => ({
      variant_id: schoolId,
      assignments: [{ side: sideToVary, school_id: schoolId }],
    }))
    const orderedMetrics = [
      `win_${sideToVary}`,
      ...selectedScenario.sides.map((side) => `${side}_destroyed`),
      'ticks_executed',
    ]
    setSubmittedDoctrine({
      scenario,
      variants,
      orderedMetrics,
      numIterations,
      baseSeed: BASE_SEED,
      maxTicks,
    })
    doctrineCompare.mutate({
      scenario,
      variants,
      metrics: orderedMetrics,
      num_iterations: numIterations,
      base_seed: BASE_SEED,
      max_ticks: maxTicks,
    })
  }

  const evidenceError = doctrineCompare.data && submittedDoctrine
    ? validateDoctrineResult(doctrineCompare.data, submittedDoctrine)
    : null
  const validatedResult = doctrineCompare.data && !evidenceError
    ? doctrineCompare.data
    : null

  return (
    <div className="space-y-6">
      <div className="rounded-lg bg-white p-6 shadow dark:bg-gray-800">
        <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-gray-100">
          Doctrine Comparison
        </h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
              Scenario
            </label>
            <Select
              value={scenario}
              onChange={handleScenarioChange}
              options={scenarioOptions}
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
              Side to Vary
            </label>
            <select
              value={sideToVary}
              onChange={(e) => setSideToVary(e.target.value)}
              aria-label="Side to vary"
              disabled={!selectedScenario}
              className="mt-1 block w-full rounded border-gray-300 text-sm shadow-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
            >
              {(selectedScenario?.sides ?? []).map((side) => (
                <option value={side} key={side}>
                  {side.replace(/_/g, ' ')}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
              Iterations per School
            </label>
            <input
              type="number"
              value={numIterations}
              onChange={(e) => setNumIterations(parseInt(e.target.value, 10) || 10)}
              min={2}
              max={500}
              className="mt-1 block w-full rounded border-gray-300 text-sm shadow-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
              Max Ticks
            </label>
            <input
              type="number"
              value={maxTicks}
              onChange={(e) => setMaxTicks(parseInt(e.target.value, 10) || 10000)}
              min={1}
              className="mt-1 block w-full rounded border-gray-300 text-sm shadow-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
            />
          </div>
        </div>

        {/* School selection */}
        <div className="mt-4">
          <label className="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300">
            Schools to Compare (select at least 2)
          </label>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {(schools ?? []).map((s) => (
              <label
                key={s.school_id}
                className="flex items-center gap-2 rounded border border-gray-200 p-2 text-sm dark:border-gray-700"
              >
                <input
                  type="checkbox"
                  checked={selectedSchools.has(s.school_id)}
                  onChange={() => toggleSchool(s.school_id)}
                />
                <span className="text-gray-800 dark:text-gray-200">
                  {s.display_name || s.school_id}
                </span>
              </label>
            ))}
          </div>
        </div>

        <div className="mt-4">
          <button
            onClick={handleSubmit}
            disabled={!canSubmit}
            className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {doctrineCompare.isPending ? 'Running...' : 'Run Comparison'}
          </button>
        </div>
      </div>

      {doctrineCompare.isPending && <LoadingSpinner />}

      {doctrineCompare.error && (
        <div className="rounded-md bg-red-50 p-4 text-sm text-red-700 dark:bg-red-900/30 dark:text-red-300" role="alert">
          {doctrineCompare.error.message}
        </div>
      )}

      {evidenceError && (
        <div
          className="rounded-md bg-red-50 p-4 text-sm text-red-700 dark:bg-red-900/30 dark:text-red-300"
          role="alert"
        >
          Doctrine result rejected: {evidenceError}
        </div>
      )}

      {validatedResult && <ResultsTable data={validatedResult} />}
    </div>
  )
}
