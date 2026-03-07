import type { CompareResult } from '../../types/analysis'
import { PlotlyChart } from './PlotlyChart'

interface ComparisonChartsProps {
  result: CompareResult
  labelA: string
  labelB: string
  className?: string
}

export function ComparisonCharts({ result, labelA, labelB, className }: ComparisonChartsProps) {
  const metrics = result.metrics ?? []

  if (metrics.length === 0) {
    return <div className="py-8 text-center text-sm text-gray-400 dark:text-gray-500">No comparison data available</div>
  }

  const metricNames = metrics.map((m) => m.metric)
  const meansA = metrics.map((m) => m.mean_a)
  const meansB = metrics.map((m) => m.mean_b)

  return (
    <div className={className}>
      <PlotlyChart
        data={[
          {
            x: metricNames,
            y: meansA,
            name: labelA,
            type: 'bar' as const,
            marker: { color: '#3b82f6' },
            error_y: { type: 'data' as const, array: metrics.map((m) => m.std_a), visible: true },
          },
          {
            x: metricNames,
            y: meansB,
            name: labelB,
            type: 'bar' as const,
            marker: { color: '#ef4444' },
            error_y: { type: 'data' as const, array: metrics.map((m) => m.std_b), visible: true },
          },
        ]}
        layout={{
          title: { text: `${labelA} vs ${labelB}` },
          barmode: 'group',
          height: 400,
        }}
      />

      <div className="mt-4 overflow-x-auto rounded-lg bg-white dark:bg-gray-800 shadow">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 dark:border-gray-700 text-left text-gray-500 dark:text-gray-400">
              <th className="px-4 py-3 font-medium">Metric</th>
              <th className="px-4 py-3 font-medium">{labelA} (mean +/- std)</th>
              <th className="px-4 py-3 font-medium">{labelB} (mean +/- std)</th>
              <th className="px-4 py-3 font-medium">p-value</th>
              <th className="px-4 py-3 font-medium">Effect Size</th>
            </tr>
          </thead>
          <tbody>
            {metrics.map((m) => (
              <tr key={m.metric} className="border-b border-gray-100 dark:border-gray-700">
                <td className="px-4 py-3 font-medium text-gray-900 dark:text-gray-100">{m.metric}</td>
                <td className="px-4 py-3 text-gray-600 dark:text-gray-400">{m.mean_a.toFixed(2)} +/- {m.std_a.toFixed(2)}</td>
                <td className="px-4 py-3 text-gray-600 dark:text-gray-400">{m.mean_b.toFixed(2)} +/- {m.std_b.toFixed(2)}</td>
                <td className={`px-4 py-3 ${m.significant ? 'font-semibold text-green-600 dark:text-green-400' : 'text-gray-500 dark:text-gray-400'}`}>
                  {m.p_value.toFixed(4)}
                </td>
                <td className="px-4 py-3 text-gray-600 dark:text-gray-400">{m.effect_size.toFixed(3)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
