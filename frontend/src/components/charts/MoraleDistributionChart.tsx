import type { MoraleAnalytics } from '../../types/analytics'
import { PlotlyChart } from './PlotlyChart'

interface MoraleDistributionChartProps {
  data: MoraleAnalytics
  dt: number
  className?: string
  layoutOverrides?: Partial<Plotly.Layout>
  onClick?: (event: Plotly.PlotMouseEvent) => void
}

const MORALE_STATES = [
  { key: 'steady' as const, label: 'Steady', color: '#22c55e' },
  { key: 'shaken' as const, label: 'Shaken', color: '#eab308' },
  { key: 'broken' as const, label: 'Broken', color: '#f97316' },
  { key: 'routed' as const, label: 'Routed', color: '#ef4444' },
  { key: 'surrendered' as const, label: 'Surrendered', color: '#6b7280' },
]

export function MoraleDistributionChart({ data, dt, className, layoutOverrides, onClick }: MoraleDistributionChartProps) {
  if (data.timeline.length === 0) {
    return <div className="py-8 text-center text-sm text-gray-400">No morale transitions recorded</div>
  }

  const xs = data.timeline.map((p) => p.tick * dt)

  const traces: Plotly.Data[] = MORALE_STATES.map((state) => ({
    x: xs,
    y: data.timeline.map((p) => p[state.key]),
    name: state.label,
    type: 'scatter' as const,
    mode: 'lines' as const,
    stackgroup: 'morale',
    line: { color: state.color, width: 0 },
    fillcolor: state.color + '80', // 50% opacity
    hovertemplate: `%{y} ${state.label.toLowerCase()}<extra></extra>`,
  }))

  const dataSummary = (
    <table className="min-w-full text-xs">
      <thead>
        <tr>
          <th scope="col" className="px-2 py-1 text-left">Time (s)</th>
          {MORALE_STATES.map(s => <th key={s.key} scope="col" className="px-2 py-1 text-right">{s.label}</th>)}
        </tr>
      </thead>
      <tbody>
        {data.timeline.filter((_, i) => i % Math.max(1, Math.floor(data.timeline.length / 10)) === 0).map((p, i) => (
          <tr key={i}>
            <td className="px-2 py-1">{(p.tick * dt).toFixed(0)}</td>
            {MORALE_STATES.map(s => <td key={s.key} className="px-2 py-1 text-right">{p[s.key]}</td>)}
          </tr>
        ))}
      </tbody>
    </table>
  )

  return (
    <PlotlyChart
      data={traces}
      layout={{
        title: { text: 'Morale State Distribution' },
        xaxis: { title: { text: 'Elapsed Time (s)' } },
        yaxis: { title: { text: 'Unit Count' }, rangemode: 'tozero' },
        height: 350,
        ...layoutOverrides,
      }}
      className={className}
      onClick={onClick}
      dataSummary={dataSummary}
    />
  )
}
