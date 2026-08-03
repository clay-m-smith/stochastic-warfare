import { useNavigate, useParams } from 'react-router-dom'
import { Badge } from '../../components/Badge'
import { ErrorMessage } from '../../components/ErrorMessage'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { PageHeader } from '../../components/PageHeader'
import { useScenario } from '../../hooks/useScenarios'
import { useExport } from '../../hooks/useExport'
import { eraBadgeColor, eraDisplayName } from '../../lib/era'
import { formatDuration } from '../../lib/format'
import type { ForceSummaryEntry, HistoricalClaimDisposition } from '../../types/api'
import { ConfigBadges } from './ConfigBadges'
import { ForceTable } from './ForceTable'

const HISTORICAL_DISPOSITION_LABELS: Record<HistoricalClaimDisposition, string> = {
  production_validated: 'Production Validated',
  current_engine_regression_only: 'Current-Engine Regression Only',
  unsupported: 'Unsupported',
}

const HISTORICAL_DISPOSITION_COLORS: Record<HistoricalClaimDisposition, string> = {
  production_validated: 'bg-green-100 text-green-800',
  current_engine_regression_only: 'bg-blue-100 text-blue-800',
  unsupported: 'bg-amber-100 text-amber-800',
}

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
  const historicalValidation = scenario.historical_validation

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

      <section className="mt-6" aria-labelledby="historical-validation-heading">
        <h2
          id="historical-validation-heading"
          className="mb-2 text-lg font-semibold text-gray-800 dark:text-gray-200"
        >
          Historical Validation
        </h2>
        <div className="flex flex-wrap items-center gap-2">
          <Badge
            className={HISTORICAL_DISPOSITION_COLORS[historicalValidation.aggregate_disposition]}
          >
            {HISTORICAL_DISPOSITION_LABELS[historicalValidation.aggregate_disposition]}
          </Badge>
          {historicalValidation.current_engine_regression_evidence && (
            <span className="text-sm text-gray-600 dark:text-gray-400">
              Current-engine regression evidence exists, but it is not historical validation or
              predictive calibration.
            </span>
          )}
        </div>
        {historicalValidation.accepted_claim_ids.length > 0 ? (
          <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
            Only the accepted claim scopes listed below are validated; other claims may remain
            unsupported, and no broader predictive claim is made.
          </p>
        ) : (
          <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
            No accepted production, source-backed held-out study validates a historical outcome
            claim for this scenario.
          </p>
        )}
        {historicalValidation.claims.length > 0 && (
          <div className="mt-3 space-y-3">
            {historicalValidation.claims.map((claim) => (
              <div
                key={claim.claim_id}
                className="rounded-md border border-gray-200 p-3 text-sm dark:border-gray-700"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="font-medium text-gray-900 dark:text-gray-100">{claim.claim_id}</h3>
                  <Badge className={HISTORICAL_DISPOSITION_COLORS[claim.disposition]}>
                    {HISTORICAL_DISPOSITION_LABELS[claim.disposition]}
                  </Badge>
                </div>
                <dl className="mt-2 grid gap-1 text-gray-600 dark:text-gray-400 sm:grid-cols-2">
                  <div>
                    <dt className="inline font-medium">Intended use: </dt>
                    <dd className="inline">{claim.intended_use}</dd>
                  </div>
                  <div>
                    <dt className="inline font-medium">Event scope: </dt>
                    <dd className="inline">{claim.event_scope}</dd>
                  </div>
                  <div>
                    <dt className="inline font-medium">Metric scope: </dt>
                    <dd className="inline">{claim.metric_scope.join(', ') || 'none declared'}</dd>
                  </div>
                  <div>
                    <dt className="inline font-medium">Reason codes: </dt>
                    <dd className="inline">{claim.reason_codes.join(', ') || 'none'}</dd>
                  </div>
                  <div>
                    <dt className="inline font-medium">Current-engine regression evidence: </dt>
                    <dd
                      className="inline"
                      aria-label={`Current-engine regression evidence for ${claim.claim_id}`}
                    >
                      {claim.current_engine_regression_evidence ? 'Present' : 'None recorded'}
                    </dd>
                  </div>
                  <div className="sm:col-span-2">
                    <dt className="inline font-medium">Limitation: </dt>
                    <dd className="inline">{claim.limitation}</dd>
                  </div>
                </dl>
                {(claim.accepted_study_id || claim.accepted_artifact_path) && (
                  <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                    Accepted evidence: {claim.accepted_study_id ?? 'study not recorded'}
                    {claim.accepted_artifact_path ? ` — ${claim.accepted_artifact_path}` : ''}
                  </p>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

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
            {terrain.base_elevation_m != null && (
              <div>
                <span className="text-gray-500 dark:text-gray-400">Elevation: </span>
                <span className="font-medium">{String(terrain.base_elevation_m)}m</span>
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
            {weather.visibility_m != null && (
              <div>
                <span className="text-gray-500 dark:text-gray-400">Visibility: </span>
                <span className="font-medium">{String(weather.visibility_m)} m</span>
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

    </div>
  )
}
