import { StatCard } from '../../../components/StatCard'
import { formatSeconds } from '../../../lib/format'
import type { RunDetail, RunResult } from '../../../types/api'
import { RunSummaryCard } from '../RunSummaryCard'

interface ResultsTabProps {
  run: RunDetail
  result: RunResult | null
}

export function ResultsTab({ run, result }: ResultsTabProps) {
  if (!result) {
    return <div className="py-8 text-center text-sm text-gray-400 dark:text-gray-500">No result data available</div>
  }

  return (
    <div className="space-y-6">
      <RunSummaryCard result={result} />

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard label="Ticks Executed" value={result.ticks_executed ?? 0} />
        <StatCard label="Duration" value={formatSeconds(result.duration_s ?? 0)} />
        <StatCard label="Seed" value={run.seed} />
        <StatCard label="Max Ticks" value={run.max_ticks} />
      </div>
    </div>
  )
}
