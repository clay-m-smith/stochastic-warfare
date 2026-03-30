import { useState } from 'react'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { Select } from '../../components/Select'
import { useDoctrineCompare } from '../../hooks/useAnalysis'
import { useSchools } from '../../hooks/useMeta'
import { useScenarios } from '../../hooks/useScenarios'
import type { DoctrineCompareResult } from '../../types/analysis'

function ResultsTable({ data }: { data: DoctrineCompareResult }) {
  const sorted = [...data.results].sort((a, b) => b.win_rate - a.win_rate)
  return (
    <div className="overflow-x-auto rounded-lg bg-white shadow dark:bg-gray-800">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="border-b border-gray-200 text-left text-gray-500 dark:border-gray-700 dark:text-gray-400">
            <th className="px-4 py-3 font-medium" scope="col">School</th>
            <th className="px-4 py-3 font-medium" scope="col">Win Rate</th>
            <th className="px-4 py-3 font-medium" scope="col">Blue Casualties</th>
            <th className="px-4 py-3 font-medium" scope="col">Red Casualties</th>
            <th className="px-4 py-3 font-medium" scope="col">Duration (ticks)</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((r, i) => (
            <tr
              key={r.school_id}
              className={`border-b border-gray-100 dark:border-gray-700 ${i === 0 ? 'bg-green-50 dark:bg-green-900/10' : ''}`}
            >
              <td className="px-4 py-2 font-medium text-gray-900 dark:text-gray-100">
                {r.display_name || r.school_id}
              </td>
              <td className="px-4 py-2 font-mono">
                {(r.win_rate * 100).toFixed(0)}%
              </td>
              <td className="px-4 py-2 font-mono">
                {r.mean_blue_destroyed.toFixed(1)} +/- {r.std_blue_destroyed.toFixed(1)}
              </td>
              <td className="px-4 py-2 font-mono">
                {r.mean_red_destroyed.toFixed(1)} +/- {r.std_red_destroyed.toFixed(1)}
              </td>
              <td className="px-4 py-2 font-mono">
                {r.mean_duration_ticks.toFixed(0)} +/- {r.std_duration_ticks.toFixed(0)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function DoctrineComparePanel() {
  const { data: scenarios } = useScenarios()
  const { data: schools } = useSchools()
  const [scenario, setScenario] = useState('')
  const [sideToVary, setSideToVary] = useState('blue')
  const [selectedSchools, setSelectedSchools] = useState<Set<string>>(new Set())
  const [numIterations, setNumIterations] = useState(10)
  const [maxTicks, setMaxTicks] = useState(10000)

  const doctrineCompare = useDoctrineCompare()

  const scenarioOptions = (scenarios ?? []).map((s) => ({ value: s.name, label: s.display_name }))

  const toggleSchool = (id: string) => {
    setSelectedSchools((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const canSubmit = scenario && selectedSchools.size >= 2 && !doctrineCompare.isPending

  const handleSubmit = () => {
    if (!canSubmit) return
    doctrineCompare.mutate({
      scenario,
      side_to_vary: sideToVary,
      schools: Array.from(selectedSchools),
      num_iterations: numIterations,
      max_ticks: maxTicks,
    })
  }

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
            <Select value={scenario} onChange={setScenario} options={scenarioOptions} />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
              Side to Vary
            </label>
            <select
              value={sideToVary}
              onChange={(e) => setSideToVary(e.target.value)}
              aria-label="Side to vary"
              className="mt-1 block w-full rounded border-gray-300 text-sm shadow-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
            >
              <option value="blue">Blue</option>
              <option value="red">Red</option>
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
              min={1}
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

      {doctrineCompare.data && <ResultsTable data={doctrineCompare.data} />}
    </div>
  )
}
