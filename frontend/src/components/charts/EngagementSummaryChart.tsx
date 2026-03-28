import type { EngagementAnalytics } from '../../types/analytics'
import { PlotlyChart } from './PlotlyChart'

interface EngagementSummaryChartProps {
  data: EngagementAnalytics
  className?: string
  layoutOverrides?: Partial<Plotly.Layout>
}

export function EngagementSummaryChart({ data, className, layoutOverrides }: EngagementSummaryChartProps) {
  if (data.total === 0) {
    return <div className="py-8 text-center text-sm text-gray-400">No engagements recorded</div>
  }

  const types = data.by_type.map((g) => g.type)
  const counts = data.by_type.map((g) => g.count)
  const hitRates = data.by_type.map((g) => `${(g.hit_rate * 100).toFixed(0)}% hit`)

  const traces: Plotly.Data[] = [
    {
      y: types,
      x: counts,
      type: 'bar' as const,
      orientation: 'h' as const,
      marker: { color: '#6366f1' },
      text: hitRates,
      textposition: 'outside' as const,
      hovertemplate: '%{y}: %{x} engagements<br>%{text}<extra></extra>',
    },
  ]

  const dataSummary = (
    <table className="min-w-full text-xs">
      <thead>
        <tr>
          <th scope="col" className="px-2 py-1 text-left">Type</th>
          <th scope="col" className="px-2 py-1 text-right">Count</th>
          <th scope="col" className="px-2 py-1 text-right">Hit Rate</th>
        </tr>
      </thead>
      <tbody>
        {data.by_type.map((g, i) => (
          <tr key={i}>
            <td className="px-2 py-1">{g.type}</td>
            <td className="px-2 py-1 text-right">{g.count}</td>
            <td className="px-2 py-1 text-right">{(g.hit_rate * 100).toFixed(1)}%</td>
          </tr>
        ))}
      </tbody>
    </table>
  )

  return (
    <PlotlyChart
      data={traces}
      layout={{
        title: { text: `Engagements by Type (${data.total} total)` },
        xaxis: { title: { text: 'Count' }, rangemode: 'tozero' },
        yaxis: { automargin: true },
        height: Math.max(200, 50 + types.length * 30),
        ...layoutOverrides,
      }}
      className={className}
      dataSummary={dataSummary}
    />
  )
}
