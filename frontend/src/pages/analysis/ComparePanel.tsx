import { useState } from 'react'
import { ComparisonCharts } from '../../components/charts/ComparisonCharts'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { Select } from '../../components/Select'
import { useScenarios } from '../../hooks/useScenarios'
import { useCompare } from '../../hooks/useAnalysis'

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

  const compare = useCompare()

  const scenarioOptions = (scenarios ?? []).map((s) => ({ value: s.name, label: s.display_name }))

  const handleSubmit = () => {
    if (!scenario) return
    setJsonError(null)
    let parsedA: Record<string, unknown> = {}
    let parsedB: Record<string, unknown> = {}
    try {
      parsedA = JSON.parse(overridesA) as Record<string, unknown>
    } catch (e) {
      setJsonError(`Overrides A: invalid JSON — ${e instanceof Error ? e.message : String(e)}`)
      return
    }
    try {
      parsedB = JSON.parse(overridesB) as Record<string, unknown>
    } catch (e) {
      setJsonError(`Overrides B: invalid JSON — ${e instanceof Error ? e.message : String(e)}`)
      return
    }
    compare.mutate({
      scenario,
      overrides_a: parsedA,
      overrides_b: parsedB,
      label_a: labelA,
      label_b: labelB,
      num_iterations: numIterations,
      max_ticks: maxTicks,
    })
  }

  return (
    <div className="space-y-6">
      <div className="rounded-lg bg-white p-6 shadow">
        <h2 className="mb-4 text-lg font-semibold text-gray-900">A/B Comparison</h2>
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
            <label className="mb-1 block text-sm font-medium text-gray-700">Iterations</label>
            <input
              type="number"
              value={numIterations}
              onChange={(e) => setNumIterations(Number(e.target.value))}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">Label A</label>
            <input
              type="text"
              value={labelA}
              onChange={(e) => setLabelA(e.target.value)}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">Label B</label>
            <input
              type="text"
              value={labelB}
              onChange={(e) => setLabelB(e.target.value)}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">Overrides A (JSON)</label>
            <textarea
              value={overridesA}
              onChange={(e) => setOverridesA(e.target.value)}
              rows={3}
              className="w-full rounded-md border border-gray-300 px-3 py-2 font-mono text-sm"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">Overrides B (JSON)</label>
            <textarea
              value={overridesB}
              onChange={(e) => setOverridesB(e.target.value)}
              rows={3}
              className="w-full rounded-md border border-gray-300 px-3 py-2 font-mono text-sm"
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

      {compare.data && (
        <ComparisonCharts result={compare.data} labelA={labelA} labelB={labelB} />
      )}
    </div>
  )
}
