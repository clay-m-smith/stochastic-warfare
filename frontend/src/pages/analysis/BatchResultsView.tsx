import { HistogramGrid } from '../../components/charts/HistogramGrid'
import { StatisticsTable } from '../../components/charts/StatisticsTable'
import type { MetricStats } from '../../types/api'

interface BatchResultsViewProps {
  metrics: Record<string, MetricStats>
}

export function BatchResultsView({ metrics }: BatchResultsViewProps) {
  return (
    <div className="space-y-6">
      <div>
        <h3 className="mb-3 text-lg font-semibold text-gray-900">Distribution</h3>
        <HistogramGrid metrics={metrics} />
      </div>
      <div>
        <h3 className="mb-3 text-lg font-semibold text-gray-900">Statistics</h3>
        <StatisticsTable metrics={metrics} />
      </div>
    </div>
  )
}
