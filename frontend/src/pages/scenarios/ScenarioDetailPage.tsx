import { useNavigate, useParams } from 'react-router-dom'
import { Badge } from '../../components/Badge'
import { ErrorMessage } from '../../components/ErrorMessage'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { PageHeader } from '../../components/PageHeader'
import { useScenario } from '../../hooks/useScenarios'
import { useExport } from '../../hooks/useExport'
import { eraBadgeColor, eraDisplayName } from '../../lib/era'
import { formatDuration } from '../../lib/format'
import type { ForceSummaryEntry } from '../../types/api'
import { ConfigBadges } from './ConfigBadges'
import { ForceTable } from './ForceTable'

export function ScenarioDetailPage() {
  const { name } = useParams<{ name: string }>()
  const navigate = useNavigate()
  const { data: scenario, isLoading, error, refetch } = useScenario(name ?? '')
  const { downloadYAML } = useExport()

  if (isLoading) return <LoadingSpinner />
  if (error) return <ErrorMessage message={error.message} onRetry={() => refetch()} />
  if (!scenario) return <ErrorMessage message="Scenario not found." />

  const config = scenario.config
  const terrain = config.terrain as Record<string, unknown> | undefined
  const weather = config.weather_conditions as Record<string, unknown> | undefined
  const durationHours = (config.duration_hours as number) ?? 0
  const era = (config.era as string) ?? 'modern'
  const displayName = (config.name as string) ?? scenario.name
  const documentedOutcomes = config.documented_outcomes as
    | Record<string, unknown>[]
    | undefined

  return (
    <div>
      <PageHeader title={displayName}>
        <button
          onClick={() => downloadYAML(scenario.config as Record<string, unknown>, `${scenario.name}.yaml`)}
          className="rounded-md border border-gray-300 dark:border-gray-600 px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
        >
          Download YAML
        </button>
        <button
          onClick={() => navigate(`/scenarios/${encodeURIComponent(scenario.name)}/edit`)}
          className="rounded-md border border-gray-300 dark:border-gray-600 px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
        >
          Clone &amp; Tweak
        </button>
        <button
          onClick={() => navigate(`/runs/new?scenario=${encodeURIComponent(scenario.name)}`)}
          className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          Run This Scenario
        </button>
      </PageHeader>

      <div className="mb-6 flex flex-wrap items-center gap-3">
        <Badge className={eraBadgeColor(era)}>{eraDisplayName(era)}</Badge>
        {durationHours > 0 && (
          <span className="text-sm text-gray-500 dark:text-gray-400">{formatDuration(durationHours)}</span>
        )}
      </div>

      <ConfigBadges config={config} />

      {/* Terrain info */}
      {terrain && (
        <section className="mt-6">
          <h2 className="mb-2 text-lg font-semibold text-gray-800 dark:text-gray-200">Terrain</h2>
          <div className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
            {terrain.terrain_type != null && (
              <div>
                <span className="text-gray-500 dark:text-gray-400">Type: </span>
                <span className="font-medium">{String(terrain.terrain_type)}</span>
              </div>
            )}
            {terrain.width_m != null && (
              <div>
                <span className="text-gray-500 dark:text-gray-400">Width: </span>
                <span className="font-medium">{String(terrain.width_m)}m</span>
              </div>
            )}
            {terrain.height_m != null && (
              <div>
                <span className="text-gray-500 dark:text-gray-400">Height: </span>
                <span className="font-medium">{String(terrain.height_m)}m</span>
              </div>
            )}
            {terrain.base_elevation != null && (
              <div>
                <span className="text-gray-500 dark:text-gray-400">Elevation: </span>
                <span className="font-medium">{String(terrain.base_elevation)}m</span>
              </div>
            )}
          </div>
        </section>
      )}

      {/* Weather info */}
      {weather && (
        <section className="mt-6">
          <h2 className="mb-2 text-lg font-semibold text-gray-800 dark:text-gray-200">Weather</h2>
          <div className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
            {weather.visibility_km != null && (
              <div>
                <span className="text-gray-500 dark:text-gray-400">Visibility: </span>
                <span className="font-medium">{String(weather.visibility_km)} km</span>
              </div>
            )}
            {weather.wind_speed_mps != null && (
              <div>
                <span className="text-gray-500 dark:text-gray-400">Wind: </span>
                <span className="font-medium">{String(weather.wind_speed_mps)} m/s</span>
              </div>
            )}
          </div>
        </section>
      )}

      {/* Forces */}
      <section className="mt-6">
        <h2 className="mb-2 text-lg font-semibold text-gray-800 dark:text-gray-200">Order of Battle</h2>
        <ForceTable forceSummary={scenario.force_summary as Record<string, ForceSummaryEntry>} />
      </section>

      {/* Documented Outcomes */}
      {documentedOutcomes && documentedOutcomes.length > 0 && (
        <section className="mt-6">
          <h2 className="mb-2 text-lg font-semibold text-gray-800 dark:text-gray-200">Documented Outcomes</h2>
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200 dark:border-gray-700 text-left text-gray-500 dark:text-gray-400">
                  <th className="pb-2 pr-4 font-medium">Metric</th>
                  <th className="pb-2 pr-4 font-medium">Value</th>
                  <th className="pb-2 font-medium">Source</th>
                </tr>
              </thead>
              <tbody>
                {documentedOutcomes.map((outcome, i) => (
                  <tr key={i} className="border-b border-gray-100 dark:border-gray-700">
                    <td className="py-2 pr-4 text-gray-900 dark:text-gray-100">{String(outcome.metric ?? '')}</td>
                    <td className="py-2 pr-4 text-gray-700 dark:text-gray-300">{String(outcome.value ?? '')}</td>
                    <td className="py-2 text-gray-600 dark:text-gray-400">{String(outcome.source ?? '')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  )
}
