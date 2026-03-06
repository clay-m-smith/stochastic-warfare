import type { MetricStats } from '../../types/api'

interface StatisticsTableProps {
  metrics: Record<string, MetricStats>
  className?: string
}

export function StatisticsTable({ metrics, className }: StatisticsTableProps) {
  const entries = Object.entries(metrics)
  if (entries.length === 0) {
    return <div className="py-8 text-center text-sm text-gray-400">No metrics available</div>
  }

  return (
    <div className={`overflow-x-auto rounded-lg bg-white shadow ${className ?? ''}`}>
      <table className="min-w-full text-sm">
        <thead>
          <tr className="border-b border-gray-200 text-left text-gray-500">
            <th className="px-4 py-3 font-medium">Metric</th>
            <th className="px-4 py-3 font-medium text-right">Mean</th>
            <th className="px-4 py-3 font-medium text-right">Median</th>
            <th className="px-4 py-3 font-medium text-right">Std</th>
            <th className="px-4 py-3 font-medium text-right">Min</th>
            <th className="px-4 py-3 font-medium text-right">Max</th>
            <th className="px-4 py-3 font-medium text-right">P5</th>
            <th className="px-4 py-3 font-medium text-right">P95</th>
          </tr>
        </thead>
        <tbody>
          {entries.map(([name, s]) => (
            <tr key={name} className="border-b border-gray-100">
              <td className="px-4 py-3 font-medium text-gray-900">{name}</td>
              <td className="px-4 py-3 text-right text-gray-600">{s.mean.toFixed(2)}</td>
              <td className="px-4 py-3 text-right text-gray-600">{s.median.toFixed(2)}</td>
              <td className="px-4 py-3 text-right text-gray-600">{s.std.toFixed(2)}</td>
              <td className="px-4 py-3 text-right text-gray-600">{s.min.toFixed(2)}</td>
              <td className="px-4 py-3 text-right text-gray-600">{s.max.toFixed(2)}</td>
              <td className="px-4 py-3 text-right text-gray-600">{s.p5.toFixed(2)}</td>
              <td className="px-4 py-3 text-right text-gray-600">{s.p95.toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
