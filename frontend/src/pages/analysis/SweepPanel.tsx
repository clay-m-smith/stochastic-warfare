import { useState } from 'react'
import { ErrorBarChart } from '../../components/charts/ErrorBarChart'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { Select } from '../../components/Select'
import { useScenarios } from '../../hooks/useScenarios'
import { useSweep } from '../../hooks/useAnalysis'

export function SweepPanel() {
  const { data: scenarios } = useScenarios()
  const [scenario, setScenario] = useState('')
  const [paramName, setParamName] = useState('')
  const [valuesStr, setValuesStr] = useState('')
  const [numIterations, setNumIterations] = useState(10)
  const [maxTicks, setMaxTicks] = useState(10000)

  const sweep = useSweep()

  const scenarioOptions = (scenarios ?? []).map((s) => ({ value: s.name, label: s.display_name }))

  const handleSubmit = () => {
    if (!scenario || !paramName || !valuesStr) return
    const values = valuesStr.split(',').map((v) => Number(v.trim())).filter((v) => !isNaN(v))
    if (values.length === 0) return
    sweep.mutate({
      scenario,
      parameter_name: paramName,
      values,
      num_iterations: numIterations,
      max_ticks: maxTicks,
    })
  }

  const sweepData = sweep.data
    ? Object.entries(sweep.data).map(([x, stats]) => {
        const s = stats as Record<string, number>
        return { x, mean: s.mean ?? 0, std: s.std ?? 0 }
      })
    : []

  return (
    <div className="space-y-6">
      <div className="rounded-lg bg-white p-6 shadow">
        <h2 className="mb-4 text-lg font-semibold text-gray-900">Sensitivity Sweep</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">Scenario</label>
            <Select
              value={scenario}
              onChange={setScenario}
              options={[{ value: '', label: 'Select scenario...' }, ...scenarioOptions]}
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">Parameter Name</label>
            <input
              type="text"
              value={paramName}
              onChange={(e) => setParamName(e.target.value)}
              placeholder="e.g. max_detection_range"
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">Values (comma-separated)</label>
            <input
              type="text"
              value={valuesStr}
              onChange={(e) => setValuesStr(e.target.value)}
              placeholder="e.g. 100, 500, 1000, 2000"
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">Iterations</label>
            <input
              type="number"
              value={numIterations}
              onChange={(e) => setNumIterations(Number(e.target.value))}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">Max Ticks</label>
            <input
              type="number"
              value={maxTicks}
              onChange={(e) => setMaxTicks(Number(e.target.value))}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
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
      </div>

      {sweep.isPending && <LoadingSpinner />}

      {sweepData.length > 0 && (
        <ErrorBarChart data={sweepData} title={`${paramName} Sensitivity`} xLabel={paramName} />
      )}
    </div>
  )
}
