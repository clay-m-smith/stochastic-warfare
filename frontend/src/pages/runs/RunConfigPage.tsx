import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Badge } from '../../components/Badge'
import { ErrorMessage } from '../../components/ErrorMessage'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { PageHeader } from '../../components/PageHeader'
import { useScenario } from '../../hooks/useScenarios'
import { useSubmitRun } from '../../hooks/useRuns'
import { eraBadgeColor, eraDisplayName } from '../../lib/era'

export function RunConfigPage() {
  const [searchParams] = useSearchParams()
  const scenarioName = searchParams.get('scenario') ?? ''
  const navigate = useNavigate()
  const { data: scenario, isLoading } = useScenario(scenarioName)
  const submitRun = useSubmitRun()

  const [seed, setSeed] = useState(42)
  const [maxTicks, setMaxTicks] = useState(10000)

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!scenarioName) return
    submitRun.mutate(
      { scenario: scenarioName, seed, max_ticks: maxTicks },
      { onSuccess: (result) => navigate(`/runs?highlight=${result.run_id}`) },
    )
  }

  if (!scenarioName) {
    return <ErrorMessage message="No scenario specified. Go to Scenarios and click 'Run This Scenario'." />
  }

  if (isLoading) return <LoadingSpinner />

  const era = (scenario?.config?.era as string) ?? 'modern'
  const displayName = (scenario?.config?.name as string) ?? scenarioName

  return (
    <div className="mx-auto max-w-xl">
      <PageHeader title="Configure Run" />

      <div className="mb-6 rounded-lg bg-white dark:bg-gray-800 p-4 shadow">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">{displayName}</h2>
          <Badge className={eraBadgeColor(era)}>{eraDisplayName(era)}</Badge>
        </div>
        <p className="text-sm text-gray-500 dark:text-gray-400">Scenario: {scenarioName}</p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4 rounded-lg bg-white dark:bg-gray-800 p-4 shadow">
        <div>
          <label htmlFor="seed" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            Random Seed
          </label>
          <input
            id="seed"
            type="number"
            value={seed}
            onChange={(e) => setSeed(Number(e.target.value))}
            required
            aria-required="true"
            className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200"
          />
        </div>
        <div>
          <label htmlFor="maxTicks" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            Max Ticks
          </label>
          <input
            id="maxTicks"
            type="number"
            value={maxTicks}
            onChange={(e) => setMaxTicks(Number(e.target.value))}
            min={1}
            required
            aria-required="true"
            className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200"
          />
        </div>

        {submitRun.isError && (
          <ErrorMessage message={submitRun.error.message} />
        )}

        <button
          type="submit"
          disabled={submitRun.isPending}
          className="w-full rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {submitRun.isPending ? 'Starting...' : 'Start Run'}
        </button>
      </form>
    </div>
  )
}
