import { StatCard } from '../../../components/StatCard'
import { LoadingSpinner } from '../../../components/LoadingSpinner'
import { useAnalyticsSummary } from '../../../hooks/useAnalytics'
import { formatSeconds } from '../../../lib/format'
import type { RunDetail, RunResult } from '../../../types/api'
import { RunSummaryCard } from '../RunSummaryCard'

interface ResultsTabProps {
  run: RunDetail
  result: RunResult | null
}

export function ResultsTab({ run, result }: ResultsTabProps) {
  const runId = run.run_id
  const isCompleted = run.status === 'completed'
  const { data: analytics, isLoading: analyticsLoading } = useAnalyticsSummary(
    isCompleted ? runId : '',
  )

  if (!result) {
    return <div className="py-8 text-center text-sm text-gray-400 dark:text-gray-500">No result data available</div>
  }

  const topHitRate = analytics?.engagements.by_type[0]?.hit_rate
  const dominantWeapon = analytics?.casualties.groups[0]?.label

  return (
    <div className="space-y-6">
      <RunSummaryCard result={result} />

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard label="Ticks Executed" value={result.ticks_executed ?? 0} />
        <StatCard label="Duration" value={formatSeconds(result.duration_s ?? 0)} />
        <StatCard label="Seed" value={run.seed} />
        <StatCard label="Max Ticks" value={run.max_ticks} />
      </div>

      {/* Phase 93: Analytics summary */}
      {analyticsLoading && <LoadingSpinner />}
      {analytics && (
        <>
          <h3 className="text-sm font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
            Battle Analytics
          </h3>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
            <StatCard label="Total Engagements" value={analytics.engagements.total} />
            <StatCard label="Hit Rate" value={topHitRate != null ? `${(topHitRate * 100).toFixed(0)}%` : 'N/A'} />
            <StatCard label="Total Casualties" value={analytics.casualties.total} />
            <StatCard label="Dominant Weapon" value={dominantWeapon ?? 'N/A'} />
            <StatCard label="Peak Suppressed" value={analytics.suppression.peak_suppressed} />
            <StatCard label="Rout Cascades" value={analytics.suppression.rout_cascades} />
          </div>
        </>
      )}
    </div>
  )
}
