import type { MetricStats } from '../../types/api'
import { PlotlyChart } from './PlotlyChart'

interface HistogramGridProps {
  metrics: Record<string, MetricStats>
  orderedMetrics: string[]
  rawMetrics: Record<string, number[]>
  className?: string
}

export function HistogramGrid({
  metrics,
  orderedMetrics,
  rawMetrics,
  className,
}: HistogramGridProps) {
  if (orderedMetrics.length === 0) {
    return <div className="py-8 text-center text-sm text-gray-400">No metrics available</div>
  }

  return (
    <div className={`grid grid-cols-1 gap-4 md:grid-cols-2 ${className ?? ''}`}>
      {orderedMetrics.map((name) => {
        const stats = metrics[name]!
        const values = rawMetrics[name]!
        return (
          <div key={name} className="rounded-lg bg-white p-3 shadow">
            <h3 className="mb-2 text-sm font-medium text-gray-700">{name}</h3>
            <PlotlyChart
              data={[
                {
                  x: values,
                  type: 'histogram' as const,
                  name,
                  marker: { color: '#6366f1' },
                },
              ]}
              layout={{ height: 150, margin: { l: 30, r: 20, t: 10, b: 20 }, showlegend: false }}
            />
            <div className="mt-1 text-xs text-gray-500">
              mean: {stats.mean.toFixed(1)} | std: {stats.std.toFixed(1)} | n={stats.n}
            </div>
            <div className="mt-1 break-all text-xs text-gray-500">
              raw: {JSON.stringify(values)}
            </div>
          </div>
        )
      })}
    </div>
  )
}
