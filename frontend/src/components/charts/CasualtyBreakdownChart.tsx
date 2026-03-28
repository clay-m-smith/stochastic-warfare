import type { CasualtyAnalytics } from '../../types/analytics'
import { getSideColor } from '../../lib/sideColors'
import { PlotlyChart } from './PlotlyChart'

interface CasualtyBreakdownChartProps {
  data: CasualtyAnalytics
  className?: string
  layoutOverrides?: Partial<Plotly.Layout>
  onClick?: (event: Plotly.PlotMouseEvent) => void
}

export function CasualtyBreakdownChart({ data, className, layoutOverrides, onClick }: CasualtyBreakdownChartProps) {
  if (data.total === 0) {
    return <div className="py-8 text-center text-sm text-gray-400">No casualties recorded</div>
  }

  // Group casualties by side for stacked bars
  const sideGroups: Record<string, { labels: string[]; counts: number[] }> = {}
  for (const g of data.groups) {
    const side = g.side || 'unknown'
    if (!sideGroups[side]) sideGroups[side] = { labels: [], counts: [] }
    sideGroups[side].labels.push(g.label)
    sideGroups[side].counts.push(g.count)
  }

  const traces: Plotly.Data[] = Object.entries(sideGroups).map(([side, { labels, counts }]) => ({
    x: labels,
    y: counts,
    name: side,
    type: 'bar' as const,
    marker: { color: getSideColor(side) },
  }))

  const dataSummary = (
    <table className="min-w-full text-xs">
      <thead>
        <tr>
          <th scope="col" className="px-2 py-1 text-left">Weapon/Cause</th>
          <th scope="col" className="px-2 py-1 text-right">Count</th>
          <th scope="col" className="px-2 py-1 text-right">Side</th>
        </tr>
      </thead>
      <tbody>
        {data.groups.slice(0, 15).map((g, i) => (
          <tr key={i}>
            <td className="px-2 py-1">{g.label}</td>
            <td className="px-2 py-1 text-right">{g.count}</td>
            <td className="px-2 py-1 text-right">{g.side}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )

  return (
    <PlotlyChart
      data={traces}
      layout={{
        title: { text: 'Casualties by Weapon' },
        xaxis: { title: { text: 'Weapon / Cause' } },
        yaxis: { title: { text: 'Casualties' }, rangemode: 'tozero' },
        barmode: 'stack',
        height: 350,
        ...layoutOverrides,
      }}
      className={className}
      onClick={onClick}
      dataSummary={dataSummary}
    />
  )
}
