import { HistogramGrid } from '../../components/charts/HistogramGrid'
import { StatisticsTable } from '../../components/charts/StatisticsTable'
import type { AnalysisBatchProvenance } from '../../types/analysis'
import type { MetricStats } from '../../types/api'

interface BatchResultsViewProps {
  metrics: Record<string, MetricStats>
  orderedMetrics: string[]
  rawMetrics: Record<string, number[]>
  provenance: AnalysisBatchProvenance
}

export function BatchResultsView({
  metrics,
  orderedMetrics,
  rawMetrics,
  provenance,
}: BatchResultsViewProps) {
  const firstRuntime = provenance.runs[0]!.runtime_provenance
  return (
    <div className="space-y-6">
      <div>
        <h3 className="mb-3 text-lg font-semibold text-gray-900 dark:text-gray-100">Distribution</h3>
        <HistogramGrid
          metrics={metrics}
          orderedMetrics={orderedMetrics}
          rawMetrics={rawMetrics}
        />
      </div>
      <div>
        <h3 className="mb-3 text-lg font-semibold text-gray-900 dark:text-gray-100">Statistics</h3>
        <StatisticsTable metrics={metrics} />
      </div>
      <div
        aria-label="Batch provenance"
        className="rounded-lg bg-white p-4 shadow dark:bg-gray-800"
      >
        <h3 className="font-semibold text-gray-900 dark:text-gray-100">
          Reproduction evidence
        </h3>
        <dl className="mt-2 grid gap-1 break-all text-xs text-gray-600 dark:text-gray-400">
          <div><dt className="inline font-medium">Seeds: </dt><dd className="inline">{provenance.seeds.join(', ')}</dd></div>
          <div><dt className="inline font-medium">Code revision: </dt><dd className="inline">{provenance.code_revision.commit}{provenance.code_revision.dirty ? ' (dirty)' : ' (clean)'}</dd></div>
          <div><dt className="inline font-medium">Worktree SHA-256: </dt><dd className="inline">{provenance.code_revision.worktree_fingerprint}</dd></div>
          <div><dt className="inline font-medium">Source SHA-256: </dt><dd className="inline">{provenance.source_fingerprint}</dd></div>
          <div><dt className="inline font-medium">Config SHA-256: </dt><dd className="inline">{provenance.config_fingerprint}</dd></div>
          <div><dt className="inline font-medium">Data revision: </dt><dd className="inline">{provenance.data_revision}</dd></div>
          <div><dt className="inline font-medium">Catalog revision: </dt><dd className="inline">{provenance.catalog_revision}</dd></div>
          <div><dt className="inline font-medium">Doctrine catalog: </dt><dd className="inline">{provenance.doctrine_catalog_fingerprint}</dd></div>
          <div><dt className="inline font-medium">Initial loadout topology: </dt><dd className="inline">{provenance.loaded_roster_loadout_fingerprint}</dd></div>
          <div><dt className="inline font-medium">Doctrine assignment: </dt><dd className="inline">{firstRuntime.doctrine_assignment_fingerprint}</dd></div>
          <div><dt className="inline font-medium">Final loadout topology: </dt><dd className="inline">{firstRuntime.final_roster_loadout_fingerprint}</dd></div>
        </dl>
      </div>
    </div>
  )
}
