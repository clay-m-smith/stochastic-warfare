import type { MetricStats } from '../../types/api'
import { PlotlyChart } from './PlotlyChart'

interface HistogramGridProps {
  metrics: Record<string, MetricStats>
  className?: string
}

export function HistogramGrid({ metrics, className }: HistogramGridProps) {
  const entries = Object.entries(metrics)
  if (entries.length === 0) {
    return <div className="py-8 text-center text-sm text-gray-400">No metrics available</div>
  }

  return (
    <div className={`grid grid-cols-1 gap-4 md:grid-cols-2 ${className ?? ''}`}>
      {entries.map(([name, stats]) => (
        <div key={name} className="rounded-lg bg-white p-3 shadow">
          <h3 className="mb-2 text-sm font-medium text-gray-700">{name}</h3>
          <PlotlyChart
            data={[
              {
                x: [stats.min, stats.p5, stats.mean, stats.p95, stats.max],
                type: 'box' as const,
                name,
                boxpoints: false,
                marker: { color: '#6366f1' },
              },
            ]}
            layout={{ height: 150, margin: { l: 30, r: 20, t: 10, b: 20 }, showlegend: false }}
          />
          <div className="mt-1 text-xs text-gray-500">
            mean: {stats.mean.toFixed(1)} | std: {stats.std.toFixed(1)} | n={stats.n}
          </div>
        </div>
      ))}
    </div>
  )
}
