import { PlotlyChart } from './PlotlyChart'

interface ComparisonChartsProps {
  result: Record<string, unknown>
  labelA: string
  labelB: string
  className?: string
}

export function ComparisonCharts({ result, labelA, labelB, className }: ComparisonChartsProps) {
  const metricsA = (result.a as Record<string, unknown>) ?? {}
  const metricsB = (result.b as Record<string, unknown>) ?? {}
  const allKeys = [...new Set([...Object.keys(metricsA), ...Object.keys(metricsB)])]

  if (allKeys.length === 0) {
    return <div className="py-8 text-center text-sm text-gray-400">No comparison data available</div>
  }

  const numericKeys = allKeys.filter(
    (k) => typeof metricsA[k] === 'number' || typeof metricsB[k] === 'number',
  )

  if (numericKeys.length === 0) {
    return (
      <div className={`overflow-x-auto rounded-lg bg-white shadow ${className ?? ''}`}>
        <table className="min-w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 text-left text-gray-500">
              <th className="px-4 py-3 font-medium">Key</th>
              <th className="px-4 py-3 font-medium">{labelA}</th>
              <th className="px-4 py-3 font-medium">{labelB}</th>
            </tr>
          </thead>
          <tbody>
            {allKeys.map((k) => (
              <tr key={k} className="border-b border-gray-100">
                <td className="px-4 py-3 font-medium text-gray-900">{k}</td>
                <td className="px-4 py-3 text-gray-600">{JSON.stringify(metricsA[k])}</td>
                <td className="px-4 py-3 text-gray-600">{JSON.stringify(metricsB[k])}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }

  return (
    <PlotlyChart
      data={[
        {
          x: numericKeys,
          y: numericKeys.map((k) => (metricsA[k] as number) ?? 0),
          name: labelA,
          type: 'bar' as const,
          marker: { color: '#3b82f6' },
        },
        {
          x: numericKeys,
          y: numericKeys.map((k) => (metricsB[k] as number) ?? 0),
          name: labelB,
          type: 'bar' as const,
          marker: { color: '#ef4444' },
        },
      ]}
      layout={{
        title: { text: `${labelA} vs ${labelB}` },
        barmode: 'group',
        height: 400,
      }}
      className={className}
    />
  )
}
